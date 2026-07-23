"""Sohbet turunu koordine eden ana akış: bağlamlaştırma → orkestratör → yanıt üretimi."""
import logging

from core.state import state
from core.llm import _get_llm, llm_invoke_tracked, extract_text
from core.lazy_imports import ensure_imports
from core import conversation_store as depo
from services.orchestrator import gorev_plani_olustur, adim_calistir, sonuclari_birlestir, genel_cevap_uret
from services.gap_analysis import cevap_eksik_mi, boslugu_kapat
from services.guardrails import girdi_guvenli_mi, cikti_guvenli_mi, gunluk_butce_asildi_mi, gunluk_maliyete_ekle
from services.reflection import yansit

logger = logging.getLogger(__name__)

YANSITILACAK_ARACLAR = {'DB_QUERY', 'RAG', 'SEARCH'}


def soruyu_baglamla_guncelle(soru: str, gecmis: str, llm=None) -> str:
    """
    Konuşma geçmişini kullanarak kullanıcının son sorusunu bağlamlaştırır.
    Zamirleri (o, onun, onlar, bu, vb.) veya atıfları geçmişteki gerçek isimlerle/konularla değiştirir.
    Eğer geçmiş yoksa veya son soru bağımsızsa orijinal soruyu aynen döndürür.
    """
    if not gecmis:
        return soru
    llm = llm or state.llm_default
    has_docs = bool(state.rag_manager and state.rag_manager.documents)
    doc_names = list(state.rag_manager.documents.keys()) if has_docs else []
    doc_info = f"(Yuklu Dosyalar: {doc_names})" if has_docs else "(Dosya yok)"

    prompt = f"""Bir sohbet asistanısın. Konuşma geçmişini kullanarak kullanıcının son sorusunu analiz et.
Eğer son soruda "bu", "o", "onun", "onlar", "bu dersler", "o hoca", "bahsedilen bölüm" gibi geçmişe atıfta bulunan (zamir veya işaret sıfatı barındıran) ifadeler varsa, bu ifadeleri geçmişte geçen gerçek isimler, ders adları veya akademik varlıklarla değiştirerek soruyu bağımsız (kendi kendine yeten) tek bir cümle olarak yeniden yaz.

Önemli Kurallar:
1. Son sorudaki kapalı/atıfta bulunan ifadeleri geçmişteki net karşılıklarıyla (örneğin "bu dersler" yerine geçmişte geçen "Yapay Zeka ve Veritabanı Yönetim Sistemleri dersleri") kesinlikle değiştir.
2. Eğer son soru zaten bağımsızsa ve geçmişe atıfta bulunmuyorsa, orijinal soruyu aynen döndür.
3. SADECE yeniden yazılmış soruyu döndür. Giriş, açıklama veya yorum yazma. Tırnak işaretleri kullanma.
4. Eğer son soruda veya geçmişte geçen "adaylar", "özgeçmişler", "başvurular" veya yüklenmiş dosya isimleriyle {doc_info} ilişkili kavramlar varsa, bunları geçmişteki veritabanı varlıklarıyla (ders, hoca vb.) karıştırmayın; adaylar doğrudan yüklenen dosyalara/adaylara aittir.
5. Eğer önceki konuşmada yüklenen dosyalar/adaylar hakkında konuşuluyorsa ve son soruda yeni bir nesne belirtilmeden eylem devam ediyorsa ("puanla", "listele", "özetle", "karşılaştır" vb.), bu eylemin halen o adaylar/dosyalar üzerinde yapıldığını varsayın ve yeniden yazılan cümleye "adaylar" veya "dosyalar" öznesini (örneğin "adayları yapay zeka bilgilerine göre puanla") mutlaka ekleyin.

Önceki konuşma geçmişi:
{gecmis}

Kullanıcının son sorusu: "{soru}"

Yeniden yazılmış soru:"""
    try:
        yeni_soru = extract_text(llm_invoke_tracked(llm, prompt)).strip()
        if yeni_soru:
            import re
            yeni_soru = re.sub(r'^["\']|["\']$', '', yeni_soru).strip()
            return yeni_soru
    except Exception as e:
        logger.warning(f"⚠️ Soruyu bağlamlaştırma hatası: {e}")
    return soru


def _sohbet_basligi_uret(soru: str, llm=None) -> str:
    """
    Bir sohbetin ilk mesajından ChatGPT/Claude/Gemini tarzı kısa bir başlık
    üretir. LLM çağrısı başarısız olursa sorunun kendisinden kırpılmış bir
    başlığa düşer (asla boş dönmez).
    """
    llm = llm or state.llm_default
    try:
        ham = extract_text(llm_invoke_tracked(llm,
            'Aşağıdaki kullanıcı mesajı için en fazla 5 kelimelik, kısa ve açıklayıcı bir '
            'Türkçe sohbet başlığı üret. SADECE başlığı döndür, tırnak işareti veya '
            f'noktalama fazlalığı kullanma.\n\nMesaj: {soru}'
        )).strip().strip('"\'.,;:، \n')
        if ham:
            return ham[:60]
    except Exception as e:
        logger.warning(f"⚠️ Sohbet başlığı üretme hatası: {e}")
    return soru[:60]


def _norag_gecmis_olustur(history: list) -> str:
    """
    Karşılaştırma modundaki 'RAG'sız' kontrol yanıtı için temizlenmiş bir
    konuşma geçmişi üretir. Ham `gecmis` (soruyu_baglamla_guncelle ve
    gorev_plani_olustur'un kullandığı) önceki turların botun ürettiği tam
    metnini içerir — bu metin DB_QUERY/RAG/SEARCH kaynaklıysa, 'RAG'sız'
    yanıt onu konuşma geçmişi üzerinden arka kapıdan görür ve karşılaştırma
    sahte bir şekilde iyi çıkar. Bu fonksiyon retrieval kaynaklı turların
    cevap metnini gizler, sadece GENERAL/META (saf sohbet) turlarının
    metnini olduğu gibi bırakır.
    """
    satirlar = []
    for h in history[-5:]:
        niyet = h.get('niyet') or ''
        retrieval_kaynakli = any(arac in niyet for arac in ('DB_QUERY', 'RAG', 'SEARCH'))
        if retrieval_kaynakli:
            satirlar.append(f"Kullanıcı: {h['user']}\nBot: (bir kaynaktan yanıt verildi, içerik burada gösterilmiyor)")
        else:
            satirlar.append(f"Kullanıcı: {h['user']}\nBot: {h['cevap']}")
    return '\n'.join(satirlar)


def _chat_akisi(soru: str, conv_id: str, model_name: str = 'chatgpt', karsilastir: bool = False):
    """
    Sohbet üretim akışının tek kaynağı. Her önemli aşamada bir ilerleme olayı
    ({'type': 'plan'|'adim_basladi'|'adim_bitti'|'birlestiriliyor'}) yield eder,
    en sonunda tam yanıtı içeren {'type': 'final', ...} olayını yield eder.
    `chat_yanit_uret` (senkron) ve `chat_yanit_uret_stream` (SSE) bu tek akışı tüketir.
    """
    ensure_imports()

    if conv_id not in state.conversations:
        yield {'type': 'final', 'error': 'Geçersiz sohbet ID'}
        return

    conv = state.conversations[conv_id]

    # Guardrail: orkestratöre hiç gitmeden, prompt injection/aşırı uzun girdi tespitinde
    # sıfır LLM maliyetiyle erken reddet.
    guvenli, red_mesaji = girdi_guvenli_mi(soru)
    if not guvenli:
        conv['history'].append({
            'user': soru, 'cevap': red_mesaji, 'cevap_norag': None,
            'kaynak': 'Güvenlik', 'tokens': 0, 'cost': 0.0, 'niyet': 'GUARDRAIL'
        })
        depo.mesaj_ekle(conv_id, conv['history'][-1], len(conv['history']), conv['tokens'], conv['cost'])
        yield {
            'type': 'final',
            'cevap': red_mesaji, 'cevap_norag': None, 'kaynak': 'Güvenlik', 'niyet': 'GUARDRAIL',
            'tokens': conv['tokens'], 'cost': f'${conv["cost"]:.5f}',
            'msg_tokens': 0, 'msg_cost': '$0.00000', 'sohbet_ismi': None
        }
        return

    # Guardrail: herkese açık demo dağıtımında günlük harcama tavanı aşıldıysa
    # orkestratöre hiç girmeden, sıfır ek maliyetle reddet (bkz. DEPLOY.md).
    butce_asildi, butce_mesaji = gunluk_butce_asildi_mi()
    if butce_asildi:
        conv['history'].append({
            'user': soru, 'cevap': butce_mesaji, 'cevap_norag': None,
            'kaynak': 'Güvenlik', 'tokens': 0, 'cost': 0.0, 'niyet': 'GUARDRAIL'
        })
        depo.mesaj_ekle(conv_id, conv['history'][-1], len(conv['history']), conv['tokens'], conv['cost'])
        yield {
            'type': 'final',
            'cevap': butce_mesaji, 'cevap_norag': None, 'kaynak': 'Güvenlik', 'niyet': 'GUARDRAIL',
            'tokens': conv['tokens'], 'cost': f'${conv["cost"]:.5f}',
            'msg_tokens': 0, 'msg_cost': '$0.00000', 'sohbet_ismi': None
        }
        return

    ilk_mesaj_mi = len(conv['history']) == 0

    gecmis = '\n'.join(
        f"Kullanıcı: {h['user']}\nBot: {h['cevap']}"
        for h in conv['history'][-5:]
    )

    llm = _get_llm(model_name)

    soru_baglamli = soruyu_baglamla_guncelle(soru, gecmis, llm)

    adimlar = gorev_plani_olustur(soru_baglamli, llm, gecmis, conv_id)
    niyet = '+'.join(dict.fromkeys(a['tool'] for a in adimlar))
    cevap = None
    kaynak = 'Bilinmeyen'

    tokens_before = state.global_tokens
    cost_before = state.global_cost_usd

    yield {'type': 'plan', 'adimlar': [a['tool'] for a in adimlar]}

    try:
        sonuclar = []
        for i, adim in enumerate(adimlar, start=1):
            yield {'type': 'adim_basladi', 'tool': adim['tool'], 'index': i, 'toplam': len(adimlar)}
            sonuc = adim_calistir(adim, gecmis, llm, model_name, conv_id)
            yield {'type': 'adim_bitti', 'tool': sonuc['tool'], 'kaynak': sonuc['kaynak']}

            if adim['tool'] in YANSITILACAK_ARACLAR:
                yield {'type': 'degerlendiriliyor', 'tool': sonuc['tool']}
                yansima = yansit(adim['soru'], sonuc['cevap'], sonuc['kaynak'], llm)
                if not yansima['yeterli'] and yansima['rafine_soru']:
                    yield {'type': 'yeniden_deneniyor', 'tool': sonuc['tool']}
                    rafine_adim = {'tool': adim['tool'], 'soru': yansima['rafine_soru']}
                    sonuc = adim_calistir(rafine_adim, gecmis, llm, model_name, conv_id)
                    yield {'type': 'adim_bitti', 'tool': sonuc['tool'], 'kaynak': sonuc['kaynak']}

            sonuclar.append(sonuc)

        # Boşluk analizi: birincil araçlar (DB_QUERY/RAG) sonuçsuz kaldıysa,
        # daha önce denenmediyse tek seferlik bir SEARCH adımıyla tamamlamayı dene.
        if cevap_eksik_mi(sonuclar):
            yield {'type': 'adim_basladi', 'tool': 'SEARCH', 'index': len(adimlar) + 1, 'toplam': len(adimlar) + 1, 'ek': True}
            sonuclar = boslugu_kapat(soru_baglamli, sonuclar, gecmis, llm, model_name)
            yield {'type': 'adim_bitti', 'tool': 'SEARCH', 'kaynak': sonuclar[-1]['kaynak']}

        niyet = '+'.join(dict.fromkeys(s['tool'] for s in sonuclar))
        if len(sonuclar) == 1:
            cevap = sonuclar[0]['cevap']
            kaynak = sonuclar[0]['kaynak']
        else:
            yield {'type': 'birlestiriliyor'}
            cevap = sonuclari_birlestir(soru_baglamli, sonuclar, llm)
            kaynak = '+'.join(dict.fromkeys(s['kaynak'] for s in sonuclar))
    except Exception as e:
        logger.exception('Sohbet akışında beklenmeyen hata')
        cevap = f'Hata oluştu: {e}'
        kaynak = 'Sistem'

    # Guardrail: kullanıcıya dönmeden önce cevapta API key/sır sızıntısı var mı kontrol et.
    cevap, sizinti_var = cikti_guvenli_mi(cevap)
    if sizinti_var:
        logger.warning(f'⚠️ Çıktıda gizli bilgi tespit edilip kaldırıldı (conv_id={conv_id})')

    cevap_norag = None
    if karsilastir:
        if niyet in ('GENERAL', 'META'):
            cevap_norag = cevap
        else:
            try:
                gecmis_norag = _norag_gecmis_olustur(conv['history'])
                cevap_norag = genel_cevap_uret(soru_baglamli, gecmis_norag, llm)
            except Exception as e:
                cevap_norag = f"RAG'sız yanıt üretilemedi: {e}"

    msg_tokens = state.global_tokens - tokens_before
    msg_cost = state.global_cost_usd - cost_before
    gunluk_maliyete_ekle(msg_cost)

    conv['history'].append({
        'user': soru,
        'cevap': cevap,
        'cevap_norag': cevap_norag,
        'kaynak': kaynak,
        'tokens': msg_tokens,
        'cost': msg_cost,
        'niyet': niyet
    })
    conv['tokens'] += msg_tokens
    conv['cost'] += msg_cost
    depo.mesaj_ekle(conv_id, conv['history'][-1], len(conv['history']), conv['tokens'], conv['cost'])

    yeni_baslik = None
    if ilk_mesaj_mi:
        yeni_baslik = _sohbet_basligi_uret(soru, llm)
        conv['name'] = yeni_baslik
        depo.sohbet_ismini_guncelle(conv_id, yeni_baslik)

    yield {
        'type': 'final',
        'cevap': cevap,
        'cevap_norag': cevap_norag,
        'kaynak': kaynak,
        'niyet': niyet,
        'tokens': conv['tokens'],
        'cost': f'${conv["cost"]:.5f}',
        'msg_tokens': msg_tokens,
        'msg_cost': f'${msg_cost:.5f}',
        'sohbet_ismi': yeni_baslik
    }


def chat_yanit_uret(soru: str, conv_id: str, model_name: str = 'chatgpt', karsilastir: bool = False):
    """
    Kullanıcı sorusuna yanıt üretir (senkron arayüz — `/api/chat` bunu kullanır).
    `_chat_akisi`'ni tüketir, sadece son ('final') olayı döner.
    """
    for olay in _chat_akisi(soru, conv_id, model_name, karsilastir):
        if olay['type'] == 'final':
            sonuc = dict(olay)
            sonuc.pop('type')
            return sonuc


def chat_yanit_uret_stream(soru: str, conv_id: str, model_name: str = 'chatgpt', karsilastir: bool = False):
    """SSE endpoint'i (`/api/chat/stream`) için: akıştaki tüm ilerleme olaylarını olduğu gibi ileri iletir."""
    yield from _chat_akisi(soru, conv_id, model_name, karsilastir)
