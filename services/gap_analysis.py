"""
Görev adımları çalıştıktan sonra sonucun soruyu gerçekten cevaplayıp cevaplamadığını
kontrol eden (gap analysis) ve gerekirse tek seferlik bir tamamlayıcı adım ekleyen katman.
"""
from services.orchestrator import adim_calistir

EKSIK_BILGI_IFADELERI = [
    'aradığınız kriterlere uygun kayıt bulunamadı',
    'kayıt bulunamadı',
    'yüklü belgelerde bu soruya yanıt bulunamadı',
    'veritabanı bağlantısı yok',
    'bu soruyu işleyemedim',
    'araması yapılamadı',
    'yeterli bilgi bulunmamaktadır', 'kapsamamaktadır',
    'bilgi içermiyor', 'bilgi yok', 'bilgi bulunmuyor',
    'bilgi bulunmamaktadır', 'ulaşılamamaktadır',
]

# Sadece bu araçlar "bilgi bulamadı" dediğinde boşluk var sayılır;
# GENERAL/META zaten en iyi çabayla (best-effort) cevap üretir, "eksik" sayılmaz.
BILGI_ARAYAN_ARACLAR = {'DB_QUERY', 'RAG'}


def cevap_eksik_mi(sonuclar: list) -> bool:
    """Birincil bilgi kaynaklarından (DB/RAG) hiçbir sonuç alınamadıysa True döner."""
    for s in sonuclar:
        if s['tool'] not in BILGI_ARAYAN_ARACLAR:
            continue
        if s['kaynak'] == 'Hata':
            return True
        cevap_lower = (s['cevap'] or '').lower()
        if any(ifade in cevap_lower for ifade in EKSIK_BILGI_IFADELERI):
            return True
    return False


def boslugu_kapat(soru: str, sonuclar: list, gecmis: str, llm, model_name: str) -> list:
    """
    Birincil araçlar sonuçsuz kaldığında, daha önce denenmediyse tek seferlik bir
    SEARCH adımı ekler. Sonsuz döngüyü önlemek için en fazla bir kez çalışır.
    """
    if any(s['tool'] == 'SEARCH' for s in sonuclar):
        return sonuclar
    arama_sonucu = adim_calistir({'tool': 'SEARCH', 'soru': soru}, gecmis, llm, model_name)
    return sonuclar + [arama_sonucu]


def tum_sonuclar_eksik_mi(sonuclar: list) -> bool:
    """
    Coklu adimli bir planda TUM adimlarin sonucu bilgi icermiyorsa True doner.
    cevap_eksik_mi'den farki: sadece DB_QUERY/RAG degil, TUM araclarin (SEARCH
    dahil) sonucuna bakar — birlestirme adiminin bos/ilgisiz parcalardan hikaye
    uydurmasini (halusinasyon) onlemek icin kullanilir.
    """
    if not sonuclar:
        return False
    for s in sonuclar:
        cevap_lower = (s['cevap'] or '').lower()
        if not any(ifade in cevap_lower for ifade in EKSIK_BILGI_IFADELERI):
            return False
    return True
