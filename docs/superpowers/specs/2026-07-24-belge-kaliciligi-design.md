# Açılışta Belge Kalıcılığını Geri Yükleme

**Context:** Uygulama her `python app.py` ile yeniden başladığında, önceden yüklenmiş belgeler diskte (`uploads/`, `chroma_db/`) duruyor ama `services/rag.py::RagManager.documents` sözlüğüne geri yüklenmiyor. Sonuç: RAG aracı sunulmuyor (`has_docs=False`), sistem yerine DB_QUERY/SEARCH'e savruluyor. Canlı bir örnekte bu durum, orkestratörün üç kez boş DB_QUERY denemesine ve ardından ciddi bir halüsinasyona (ayrı bir spec'te ele alınıyor) yol açtı.

**Goal:** İlk API isteğinde (`ensure_imports()`), daha önce yüklenmiş her belgeyi — yeniden embed etmeden, mevcut Chroma persist dizinine bağlanarak — `RagManager.documents`'a geri yükle.

**Architecture:** `RagManager`'a yeni bir metod: `diskten_yukle()`. Kaynak: `uploads/` klasöründeki gerçek dosya adları (orijinal isim burada bozulmadan duruyor; `chroma_db/` klasör adları sanitize edildiği için tersine çevrilemez, bu yüzden kaynak olarak kullanılmıyor). Her desteklenen dosya için karşılık gelen `chroma_db/<güvenli_isim>/` klasörü varsa `_Chroma(persist_directory=..., embedding_function=self.embeddings)` ile bağlanılır (embed edilmez). `document_store` (kapsam/özel-global) bu akışa hiç dahil değil — kapsam zaten sorgu anında ayrıca okunuyor.

**Tech Stack:** Mevcut `_Chroma` (builtins injection ile zaten yüklü), yeni bağımlılık yok.

## Global Constraints

- Senkron: ilk istek, tüm belgeler yüklenene kadar bekler (ekstra thread/queue yok).
- Bir belgenin yüklenmesi başarısız olursa (bozuk Chroma dizini vb.) sadece o belge atlanır, `logger.warning(...)` ile loglanır, diğer belgeler etkilenmez.
- Desteklenmeyen uzantılar (`.gitkeep` dahil) sessizce atlanır — sadece `.pdf/.xlsx/.xls/.txt`.
- `RagManager.__init__`'e `upload_dir='uploads'` parametresi eklenir (mevcut `cache_dir='./chroma_db'` ile aynı desende), testte geçici bir klasör verilebilsin diye.
- `document_store`'a (kapsam kayıtları) dokunulmaz — silme/güncelleme yok.
- Yeni bağımlılık eklenmez.

---

## Çağrı Noktası

`core/lazy_imports.py::ensure_imports()`, mevcut:

```python
state.rag_manager = RagManager()
state.rag_manager.db = state.db
```

satırlarının hemen ardına tek satır eklenir:

```python
state.rag_manager.diskten_yukle()
```

## `services/rag.py::RagManager` Değişiklikleri

```python
def __init__(self, cache_dir='./chroma_db', upload_dir='uploads'):
    self.cache_dir = cache_dir
    self.upload_dir = upload_dir
    self.documents = {}
    self.db = None
```

```python
DESTEKLENEN_UZANTILAR = ('pdf', 'xlsx', 'xls', 'txt')

def diskten_yukle(self):
    """
    uploads/ klasorundeki her desteklenen dosya icin, karsilik gelen
    chroma_db/<guvenli_isim>/ klasoru varsa (daha once embed edilmis ve
    silinmemis) yeniden embed etmeden baglanip self.documents'a ekler.
    Klasor yoksa ya da baglanti basarisiz olursa o belge atlanir, loglanir.
    """
    if not os.path.isdir(self.upload_dir):
        return
    for dosya_adi in os.listdir(self.upload_dir):
        ext = dosya_adi.rsplit('.', 1)[-1].lower() if '.' in dosya_adi else ''
        if ext not in DESTEKLENEN_UZANTILAR:
            continue
        if dosya_adi in self.documents:
            continue
        safe = dosya_adi.replace('.', '_').replace(' ', '_')
        doc_persist_dir = os.path.join(self.cache_dir, safe)
        if not os.path.isdir(doc_persist_dir):
            continue
        try:
            vs = _Chroma(persist_directory=doc_persist_dir, embedding_function=self.embeddings)
            self.documents[dosya_adi] = {'vector_store': vs}
        except Exception:
            logger.warning(f'⚠️ {dosya_adi} diskten geri yuklenemedi, atlaniyor', exc_info=True)
```

(`services/rag.py`'ye `import logging` ve `logger = logging.getLogger(__name__)` eklenir — şu an dosyada yok.)

## Test Planı

`tests/unit/test_rag_diskten_yukle.py`, `builtins._Chroma`'yı sahte bir sınıfla değiştirerek (gerçek embedding/Chroma kullanılmaz), `tmp_path` ile geçici `uploads/`/`chroma_db/` klasörleri kurarak:

1. `uploads/belge.txt` + `chroma_db/belge_txt/` (boş klasör yeterli, sadece varlığı kontrol ediliyor) varsa → `self.documents['belge.txt']` dolar, sahte `_Chroma`'ya doğru `persist_directory` ile çağrıldığı doğrulanır.
2. `uploads/belge.txt` var ama `chroma_db/belge_txt/` yoksa → `self.documents` boş kalır, hata fırlatılmaz.
3. `chroma_db/belge_txt/` var ama sahte `_Chroma` exception fırlatıyorsa → `self.documents` boş kalır, hata dışarı sızmaz.
4. `uploads/.gitkeep` ve `uploads/belge.docx` (desteklenmeyen) → ikisi de atlanır.
5. `uploads/` klasörü hiç yoksa → `diskten_yukle()` sessizce döner, hata fırlatmaz.

## Kapsam Dışı

- `document_store` (kapsam) kayıtlarının senkronizasyonu/temizliği
- Arka planda/asenkron yükleme
- `uploads/` klasöründe olup `chroma_db/`'de karşılığı olmayan (hiç embed edilmemiş) dosyaların otomatik embed edilmesi — kullanıcı isterse tekrar yükler

## Başarı Kriteri

`pytest` sıfır hatayla geçer (yeni testler dahil). Uygulama yeniden başlatıldığında, daha önce yüklenmiş bir belge hakkında soru sorulduğunda RAG aracı devreye girer (DB_QUERY/SEARCH'e savrulmaz).
