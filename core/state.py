"""
Uygulama genelinde paylaşılan, değişebilir (mutable) durumu tek bir nesnede toplar.
Modüller arası `global` anahtar kelimesi yerine bu nesnenin attribute'ları kullanılır.
"""


class AppState:
    def __init__(self):
        self.imports_done = False       # Kütüphanelerin yüklenip yüklenmediğini tutan bayrak
        self.embedding_model = None      # Metin vektörleştirme modeli (SentenceEmbeddings)
        self.llm_default = None          # Varsayılan Büyük Dil Modeli (ChatGPT veya Gemini)
        self.db = None                   # SQLAlchemy tabanlı SQLite veritabanı arayüzü
        self.CACHED_SCHEMA = ''          # SQLite veritabanı şema bilgisi (Text-to-SQL için context sağlar)
        self.rag_manager = None          # Vektör veritabanı (Chroma DB) ve belge sorgulama yöneticisi
        self.search_tool = None          # DuckDuckGo arama motoru aracı
        self.SEARCH_OK = False           # İnternet arama modülünün aktif olup olmadığını tutar
        self.example_selector = None     # Benzer SQL örneklerini seçen anlamsal eşleştirici (Few-Shot için)
        self.example_prompt = None       # Örnek SQL şablon yapısı
        self.global_tokens = 0           # Sunucu genelinde harcanan toplam token sayısı
        self.global_cost_usd = 0.0       # Sunucu genelinde oluşan toplam API maliyeti (USD)
        self.gunluk_maliyet_usd = 0.0    # Bugün oluşan API maliyeti (USD), gün değişince sıfırlanır
        self.gunluk_maliyet_tarihi = None  # gunluk_maliyet_usd'nin ait olduğu tarih (date)
        self.conversations = {}          # Tüm sohbetler: {conv_id: {...}}
        self.active_conv_id = None       # Aktif sohbet id'si
        self.conv_counter = 0            # Sohbet id üretici sayaç


state = AppState()
