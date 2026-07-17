# Academic Chatbot — CLAUDE.md

Bitirme projesi: Üniversite akademik danışman chatbotu. LLM + RAG + Text-to-SQL mimarisi üzerine inşa edilmiştir. Tüm arayüz ve prompt'lar Türkçe'dir.

## Proje Özeti

- **Backend:** `app.py` (~1100 satır) — tek dosya Flask uygulaması
- **Frontend:** `templates/index.html` (~800 satır) — vanilla JS, koyu tema, 3 sütun layout
- **Veritabanı:** `demo_okul.db` — SQLite, 7 tablo, demo akademik veri
- **Vektör DB:** `chroma_db/` — Chroma, kalıcı, belgeler klasöründen besleniyor
- **Yüklenen Belgeler:** `uploads/` — PDF, TXT, Excel

## Çalıştırmak

```powershell
# Sanal ortamı aktifleştir
.\venv\Scripts\Activate.ps1

# Bağımlılıkları yükle (ilk kez)
pip install -r requirements.txt

# Uygulamayı başlat
python app.py
# → http://localhost:5000
```

İlk başlatmada ~2-3 dakika sürer (HuggingFace embedding modeli ~1.5GB indirilir). Sonraki başlatmalar hızlıdır.

## Mimari

### Intent Yönlendirme (`niyet_siniflandir`)
5 kanal: `DB_QUERY` → SQL | `RAG` → belge | `SEARCH` → DuckDuckGo | `META` → chatbot hakkında | `GENERAL` → sohbet

Önce keyword eşleştirme (hızlı, API masrafsız), başarısız olursa LLM ile sınıflandırma.

### Text-to-SQL (`sql_uret_ve_calistir`)
- 12 elle yazılmış örnek sorgu + semantik benzerlik seçimi (few-shot)
- LLM hatalı SQL üretirse otomatik düzeltme döngüsü (self-correction)
- Desteklenen tablolar: `kullanicilar`, `bolumler`, `akademisyenler`, `ogrenciler`, `dersler`, `notlar`, `projeler`

### Belge RAG (`RagManager`)
- Embedding: `intfloat/multilingual-e5-small` (HuggingFace, yerel)
- Chunk: 1000 token, 200 token overlap
- Eşik: benzerlik=0.45, fallback=0.1, max_chunks=20
- Çok belgeli sorgularda k orantısal dağıtılır

### Web Crawler (`website_to_rag`)
- robots.txt'e saygılı
- Maksimum 30 sayfa, 0.3s gecikme
- HTML → temiz metin → RAG'a ekle

### LLM Desteği
- **ChatGPT:** `gpt-4o-mini` ($0.30/1M token)
- **Gemini:** `gemini-flash-latest` ($0.075/1M token)
- Çalışma anında model değiştirilebilir
- Per-konuşma token & maliyet takibi

## Önemli Tasarım Kararları

- **Lazy loading:** ML kütüphaneleri ilk API isteğine kadar yüklenmez → hızlı başlangıç
- **builtins injection:** Büyük modüller Python builtins'e kaydedilir, iç içe fonksiyonlarda tekrar import olmaz
- **Monolitik backend:** Modüler değil, tek `app.py` — öğrenci projesi için kasıtlı basitlik
- **Bağlam penceresi:** Son 5 konuşma turu prompt'a eklenir

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| POST | `/api/init` | Sistemi başlat (modeller + DB) |
| POST | `/api/chat` | Mesaj gönder, yanıt al |
| GET/POST/DELETE | `/api/conversations/*` | Konuşma yönetimi |
| GET/POST/DELETE | `/api/documents/*` | Belge yönetimi |
| POST | `/api/crawl` | Web sitesi tara ve RAG'a ekle |
| GET | `/api/stats` | Global token/maliyet istatistikleri |

## Ortam Değişkenleri (`.env`)

```
OPENAI_API_KEY=...    # ChatGPT için
GOOGLE_API_KEY=...    # Gemini için
```

## Mevcut Durum (2026-06-10)

### Tamamlanan
- Intent tabanlı yönlendirme (5 kanal)
- Doğal dil → SQL dönüşümü + otomatik hata düzeltme
- PDF/Excel/TXT belge yükleme ve RAG sorgusu
- Web sitesi tarama ve RAG'a ekleme
- Çoklu konuşma yönetimi (sidebar)
- ChatGPT & Gemini çift model desteği
- Token & maliyet takibi (per-mesaj ve kümülatif)
- Modern dark-theme web arayüzü
- Demo akademik veritabanı (5 bölüm, 10 akademisyen, 25 öğrenci)

### Eksik / Kısmi
- Konuşmalar sunucu yeniden başlatınca sıfırlanır (kalıcı depolama yok)
- Kullanıcı şeması var ama login akışı yok
- Test suite yok (sadece `scratch/` altında 2 manuel test)
- Multi-kullanıcı / veri izolasyonu yok

## Dosya Yapısı

```
academic_chatbot/
├── app.py                    # Ana backend (Flask + tüm AI mantığı)
├── requirements.txt          # Python bağımlılıkları
├── .env                      # API anahtarları (git'e ekleme!)
├── demo_okul.db              # SQLite DB (otomatik oluşturulur)
├── templates/index.html      # Web arayüzü
├── uploads/                  # Yüklenen belgeler
├── chroma_db/                # Kalıcı vektör veritabanı
├── scratch/                  # Geliştirme testleri
└── venv/                     # Sanal ortam
```
