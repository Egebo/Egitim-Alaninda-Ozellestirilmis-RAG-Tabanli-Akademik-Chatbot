"""Sohbet turunu koordine eden ana akış: bağlamlaştırma → orkestratör → yanıt üretimi."""
from core.state import state
from core.llm import _get_llm, llm_invoke_tracked, extract_text
from core.lazy_imports import ensure_imports
from services.orchestrator import gorev_plani_olustur, adim_calistir, sonuclari_birlestir, genel_cevap_uret
from services.gap_analysis import cevap_eksik_mi, boslugu_kapat
from services.guardrails import girdi_guvenli_mi, cikti_guvenli_mi


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
        print(f"⚠️ Soruyu bağlamlaştırma hatası: {e}")
    return soru


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
        yield {
            'type': 'final',
            'cevap': red_mesaji, 'cevap_norag': None, 'kaynak': 'Güvenlik', 'niyet': 'GUARDRAIL',
            'tokens': conv['tokens'], 'cost': f'${conv["cost"]:.5f}',
            'msg_tokens': 0, 'msg_cost': '$0.00000'
        }
        return

    gecmis = '\n'.join(
        f"Kullanıcı: {h['user']}\nBot: {h['cevap']}"
        for h in conv['history'][-5:]
    )

    llm = _get_llm(model_name)

    soru_baglamli = soruyu_baglamla_guncelle(soru, gecmis, llm)

    adimlar = gorev_plani_olustur(soru_baglamli, llm, gecmis)
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
            sonuc = adim_calistir(adim, gecmis, llm, model_name)
            sonuclar.append(sonuc)
            yield {'type': 'adim_bitti', 'tool': sonuc['tool'], 'kaynak': sonuc['kaynak']}

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
        import traceback; traceback.print_exc()
        cevap = f'Hata oluştu: {e}'
        kaynak = 'Sistem'

    # Guardrail: kullanıcıya dönmeden önce cevapta API key/sır sızıntısı var mı kontrol et.
    cevap, sizinti_var = cikti_guvenli_mi(cevap)
    if sizinti_var:
        print(f'⚠️ Çıktıda gizli bilgi tespit edilip kaldırıldı (conv_id={conv_id})')

    cevap_norag = None
    if karsilastir:
        if niyet in ('GENERAL', 'META'):
            cevap_norag = cevap
        else:
            try:
                cevap_norag = genel_cevap_uret(soru_baglamli, gecmis, llm)
            except Exception as e:
                cevap_norag = f"RAG'sız yanıt üretilemedi: {e}"

    msg_tokens = state.global_tokens - tokens_before
    msg_cost = state.global_cost_usd - cost_before

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

    yield {
        'type': 'final',
        'cevap': cevap,
        'cevap_norag': cevap_norag,
        'kaynak': kaynak,
        'niyet': niyet,
        'tokens': conv['tokens'],
        'cost': f'${conv["cost"]:.5f}',
        'msg_tokens': msg_tokens,
        'msg_cost': f'${msg_cost:.5f}'
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
