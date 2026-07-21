"""
Kullanıcı sorusunu bir görev listesine (to-do list) dönüştürüp sırayla çalıştıran orkestratör.
Ayrıca tek-adımlık GENERAL/SEARCH sorularında kullanılan genel sohbet ve internet arama yardımcılarını içerir.
"""
import re

from pydantic import BaseModel, Field

from core.state import state
from core.llm import llm_invoke_tracked, extract_text
from services.text_to_sql import sql_uret_ve_calistir, db_sonuc_formatla

GECERLI_ARACLAR = ['DB_QUERY', 'RAG', 'SEARCH', 'META', 'GENERAL']


class DB_QUERY(BaseModel):
    """Akademik veritabanindaki ogrenci/ders/not/hoca/bolum/proje/danisman/akts/ortalama/harfnotu bilgisi icin kullanilir."""
    soru: str = Field(description='Veritabanina yoneltilecek dogal dil alt-sorusu')


class RAG(BaseModel):
    """Yuklu dosyalardan/belgelerden cevaplanmasi gereken sorular icin kullanilir."""
    soru: str = Field(description='Belgelere yoneltilecek dogal dil alt-sorusu')


class SEARCH(BaseModel):
    """Internette aranmasi gereken guncel veya genel bir bilgi icin kullanilir."""
    soru: str = Field(description='Internette aranacak dogal dil sorusu')


class META(BaseModel):
    """Chatbotun kendi durumu hakkinda soru icin kullanilir (yuklu belge, aktif model vb.)."""
    soru: str = Field(description='Chatbotun durumu hakkindaki soru')


class GENERAL(BaseModel):
    """Genel sohbet, selamlasma, tavsiye veya fikir sorma icin kullanilir."""
    soru: str = Field(description='Genel sohbet mesaji')


_ARAC_SEMALARI = {'DB_QUERY': DB_QUERY, 'RAG': RAG, 'SEARCH': SEARCH, 'META': META, 'GENERAL': GENERAL}


def genel_cevap_uret(soru: str, gecmis: str, llm=None) -> str:
    llm = llm or state.llm_default
    return extract_text(llm_invoke_tracked(llm,
        f'Sen yardımcı bir Türkçe asistansın.\n\n'
        f'Önceki konuşma: {gecmis or "Yok"}\nKullanıcı: {soru}\nAsistan:'
    ))


def internet_arama_yap(soru: str, llm=None) -> str:
    llm = llm or state.llm_default
    if not state.SEARCH_OK: return genel_cevap_uret(soru, '', llm)
    try:
        sonuc = state.search_tool.run(soru)
        return extract_text(llm_invoke_tracked(llm,
            f'Arama sonuçlarına dayanarak Türkçe cevap ver.\nSoru: {soru}\nSonuçlar: {sonuc}\nCevap:'
        ))
    except Exception as e:
        return f'İnternet araması yapılamadı: {e}'


def niyet_kurala_gore(soru: str, conv_id: str = None) -> str | None:
    """
    Kural tabanlı (LLM çağırmadan) hızlı niyet tespiti. Eşleşme yoksa None döner.
    `conv_id` verilirse RAG ile ilgili kontroller sadece o sohbetin erişebildiği
    belgelere (özel + global) bakar; verilmezse (testler, programatik kullanım)
    eski davranış gibi state.rag_manager.documents'ın tamamına bakar.
    """
    s_lower = soru.lower()

    selamlama = ['selam', 'merhaba', 'hey', 'nasılsın', 'naber',
                 'günaydın', 'iyi akşamlar', 'iyi geceler', 'hi ', 'hello']
    if any(k in s_lower for k in selamlama):
        return 'GENERAL'

    meta_kelimeleri = [
        'seçili model', 'model seçili', 'aktif model', 'model aktif',
        'seçili llm', 'llm seçili', 'aktif llm', 'llm aktif',
        'hangi modeli kullan', 'yüklü belge', 'belgeler yüklü',
        'yüklü dosya', 'dosyalar yüklü'
    ]
    if any(k in s_lower for k in meta_kelimeleri):
        return 'META'

    izinli_belgeler = state.rag_manager.erisilebilir_belgeler(conv_id) if state.rag_manager else {}

    rag_keywords = ['aday', 'cv', 'özgeçmiş', 'ozgecmis', 'belge', 'dosya',
                    'başvuru', 'basvuru', 'sertifika', 'deneyim', 'yetenek',
                    'beceri', 'mezun', 'diploma', 'işe al', 'ise al']
    if izinli_belgeler and any(k in s_lower for k in rag_keywords):
        return 'RAG'

    # Soru, yüklü bir belgenin adında geçen kişi/konu isimlerine atıfta bulunuyorsa
    # (örn. "CV_-_Egemen_Bozca.pdf" belgesi yüklüyken "Egemen Bozca" sorulması),
    # DB anahtar kelimesi (örn. "hoca") eşleşse bile hızlı yoldan çıkma — LLM'in
    # çok adımlı plan kurmasına (RAG + gerekirse DB_QUERY) izin ver.
    if izinli_belgeler:
        stopwords = {'pdf', 'txt', 'xlsx', 'xls', 'doc', 'docx', 'cv', 'ozgecmis', 'özgeçmiş'}
        for doc_name in izinli_belgeler.keys():
            base = doc_name.rsplit('.', 1)[0]
            tokens = [t for t in re.split(r'[^a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+', base.lower())
                      if len(t) > 2 and t not in stopwords]
            if tokens and any(t in s_lower for t in tokens):
                return None

    db_keywords = ['öğrenci', 'ogrenci', 'ders', 'not', 'vize', 'final',
                   'hoca', 'akademisyen', 'bölüm', 'bolum', 'proje', 'tez',
                   'danışman', 'danisman', 'akts', 'ortalama', 'harf', 'eposta', 'e-posta']
    if any(k in s_lower for k in db_keywords):
        return 'DB_QUERY'

    return None


def gorev_plani_olustur(soru: str, llm=None, gecmis: str = '', conv_id: str = None) -> list:
    """
    Kullanicinin sorusunu bir veya daha fazla {'tool','soru'} adimindan olusan
    bir gorev listesine (to-do list) donusturur. Cogu soru tek adimlik cikar;
    LLM sadece kural tabanli tespit basarisiz oldugunda ve gerektiginde birden
    fazla adim onerir. Plan, modelin native tool-calling mekanizmasi (bind_tools +
    response.tool_calls) ile cikartilir; araclar gercekte cagrilmaz, sadece
    structured cikti semasi olarak kullanilir.
    """
    llm = llm or state.llm_default

    kural_sonucu = niyet_kurala_gore(soru, conv_id)
    if kural_sonucu:
        return [{'tool': kural_sonucu, 'soru': soru}]

    izinli_belgeler = state.rag_manager.erisilebilir_belgeler(conv_id) if state.rag_manager else {}
    has_docs = bool(izinli_belgeler)
    doc_names = list(izinli_belgeler.keys())
    doc_info = f"(Yuklu Dosyalar: {doc_names})" if has_docs else "(Dosya yok)"

    arac_isimleri = [ad for ad in GECERLI_ARACLAR if ad != 'RAG' or has_docs]
    semalar = [_ARAC_SEMALARI[ad] for ad in arac_isimleri]

    prompt = f"""Asagidaki soruyu cevaplamak icin uygun arac(lar)i cagir (en fazla 3).
Sorularin buyuk cogunlugu TEK bir aracla cevaplanir, o yuzden varsayilan olarak
tek bir arac cagir. Sadece soru acikca birden fazla FARKLI kaynaktan bilgi
istiyorsa (ornek: hem bir ogrencinin notunu hem de yuklu bir belgedeki proje
ornegini istemek) birden fazla arac cagir.

{doc_info}

ONEMLI: Soru "isimleri", "adlari", "onlar", "bunlar", "kac tane", "detaylari",
"o kisi", "ayni" gibi onceki konusmaya atifta bulunan ifadeler iceriyorsa,
onceki konusmanin baglamini kullan.

Onceki konusma (baglam icin kullan):
{gecmis or 'Yok'}

Soru: "{soru}\""""

    try:
        yanit = llm.bind_tools(semalar).invoke(prompt)
        tool_calls = list(getattr(yanit, 'tool_calls', None) or [])

        gecerli_adimlar = []
        for cagri in tool_calls[:3]:
            tool = str(cagri.get('name', '')).upper()
            args = cagri.get('args') or {}
            alt_soru = str(args.get('soru') or soru)
            if tool not in arac_isimleri:
                continue
            gecerli_adimlar.append({'tool': tool, 'soru': alt_soru})

        if gecerli_adimlar:
            return gecerli_adimlar
    except Exception:
        pass

    return [{'tool': 'GENERAL', 'soru': soru}]


def adim_calistir(adim: dict, gecmis: str, llm, model_name: str, conv_id: str = None) -> dict:
    """
    Tek bir görev adımını (tool + soru) çalıştırır ve {'tool','soru','cevap','kaynak'} döndürür.
    GENERAL adımlarında önce belgelerde (RAG) örtük bir yanıt olup olmadığına bakılır,
    ardından Genel Sohbet'e düşülür (eski niyet kaskad mantığıyla aynı). `conv_id`,
    RAG/META adımlarının hangi belgelere erişebileceğini (özel + global) belirler.
    """
    tool = adim['tool']
    soru = adim['soru']
    cevap = None
    kaynak = 'Bilinmeyen'
    izinli_belgeler = state.rag_manager.erisilebilir_belgeler(conv_id) if state.rag_manager else {}

    if tool == 'DB_QUERY':
        if not state.db:
            cevap = 'Veritabanı bağlantısı yok.'
            kaynak = 'Hata'
        else:
            try:
                sql, raw = sql_uret_ve_calistir(soru, gecmis, llm)
                cevap = db_sonuc_formatla(soru, raw)
                kaynak = 'Veritabanı'
            except Exception as e:
                cevap = f'Bu soruyu işleyemedim: {e}'
                kaynak = 'Hata'
    elif tool == 'RAG':
        if izinli_belgeler:
            result = state.rag_manager.ask_all(soru, llm, conv_id=conv_id)
            if result:
                cevap, kaynak = result
        if cevap is None:
            cevap = 'Yüklü belgelerde bu soruya yanıt bulunamadı.'
            kaynak = 'Belgeler'
    elif tool == 'META':
        docs = list(izinli_belgeler.keys())
        cevap = extract_text(llm_invoke_tracked(llm, [
            ('system', 'Sen bir sistem asistanısın. Türkçe cevap ver.'),
            ('human', f'Senin adın Akademik Chatbot. Model: {model_name}. Yüklü belgeler: {docs or "Yok"}. Soru: {soru}')
        ]))
        kaynak = 'Sistem'
    elif tool == 'SEARCH':
        cevap = internet_arama_yap(soru, llm)
        kaynak = 'İnternet'
    else:  # GENERAL
        if izinli_belgeler:
            result = state.rag_manager.ask_all(soru, llm, conv_id=conv_id)
            if result:
                cevap, kaynak = result
                red_kelimeleri = ['yeterli bilgi bulunmamaktadır', 'kapsamamaktadır',
                                  'bilgi içermiyor', 'bilgi yok', 'bilgi bulunmuyor',
                                  'bilgi bulunmamaktadır', 'ulaşılamamaktadır']
                if any(k in cevap.lower() for k in red_kelimeleri):
                    cevap = None
        if cevap is None:
            cevap = genel_cevap_uret(soru, gecmis, llm)
            kaynak = 'Sohbet'

    return {'tool': tool, 'soru': soru, 'cevap': cevap, 'kaynak': kaynak}


def adimlari_calistir(adimlar: list, gecmis: str, llm, model_name: str, conv_id: str = None) -> list:
    """Görev listesindeki adımları sırayla çalıştırır ve sonuç listesini döndürür."""
    return [adim_calistir(adim, gecmis, llm, model_name, conv_id) for adim in adimlar]


def sonuclari_birlestir(soru: str, sonuclar: list, llm) -> str:
    """
    Birden fazla adımdan gelen cevapları tek, tutarlı bir Türkçe yanıtta birleştirir.
    Sadece 2+ adım çalıştığında çağrılır.
    """
    parcalar = '\n\n'.join(
        f"[{s['kaynak']}] {s['soru']}\nYanıt: {s['cevap']}" for s in sonuclar
    )
    prompt = f"""Kullanicinin sorusu birden fazla kaynaktan toplanan bilgiyle cevaplandi. Asagidaki parcalari
tek, akici ve tutarli bir Turkce yanitta birlestir. Kaynaklari yanitin icinde dogal bir sekilde belirt,
gereksiz tekrar yapma.

Kullanicinin orijinal sorusu: "{soru}"

Toplanan bilgiler:
{parcalar}

Birlesik yanit:"""
    return extract_text(llm_invoke_tracked(llm, prompt))
