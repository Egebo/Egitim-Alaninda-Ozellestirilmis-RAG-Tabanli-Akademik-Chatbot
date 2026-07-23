# Academic Chatbot CLAUDE.md

Bitirme projesi: Üniversite akademik danışman chatbotu. LLM + RAG + Text-to-SQL mimarisi üzerine inşa edilmiştir. Tüm arayüz ve prompt'lar Türkçe'dir.

## Proje Özeti

- **Backend:** `app.py` (Flask app + Blueprint kaydı) + `core/` (çekirdek altyapı: state, LLM, lazy-loading, DB kurulumu) + `services/` (RAG, Text-to-SQL, orkestratör, sohbet, konuşma, crawler) + `routes/` (Blueprint'ler)
- **Frontend:** `templates/index.html` (~800 satır): vanilla JS, koyu tema, 3 sütun layout
- **Veritabanı:** `demo_okul.db`: SQLite, 7 tablo, demo akademik veri
- **Vektör DB:** `chroma_db/`: Chroma, kalıcı, belgeler klasöründen besleniyor
- **Yüklenen Belgeler:** `uploads/`: PDF, TXT, Excel

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

Giriş ekranı karşılar (demo hesaplar: `admin@admin.com`/`123456`, `ogretmen@uni.com`/`pass123`). Sohbetler `conversations.db`'ye kalıcı yazılır, sunucu yeniden başlasa da kaybolmaz.

## Mimari

### Orkestratör (`services/orchestrator.py`)
5 araç: `DB_QUERY` → SQL | `RAG` → belge | `SEARCH` → DuckDuckGo | `META` → chatbot hakkında | `GENERAL` → sohbet

`gorev_plani_olustur` kullanıcı sorusunu bir görev listesine (`[{tool, soru}, ...]`) çevirir. Önce keyword eşleştirme (`niyet_kurala_gore`, hızlı, API masrafsız) denenir; başarısız olursa LLM'den 1-3 adımlık JSON plan istenir. Adımlar `adimlari_calistir` ile sırayla çalıştırılır; birden fazla adım varsa sonuçlar `sonuclari_birlestir` ile tek yanıtta birleştirilir.

Adımlar çalıştıktan sonra `services/gap_analysis.py::cevap_eksik_mi` birincil araçların (DB_QUERY/RAG) sonuçsuz kalıp kalmadığını kontrol eder; kaldıysa ve SEARCH henüz denenmediyse `boslugu_kapat` tek seferlik bir SEARCH adımı ekler.

### Guardrails (`services/guardrails.py`)
Kural tabanlı, LLM'siz üç kontrol: `girdi_guvenli_mi` orkestratöre gitmeden önce prompt injection kalıplarını ve aşırı uzun mesajları reddeder (niyet=`GUARDRAIL`, sıfır maliyet); `gunluk_butce_asildi_mi` herkese açık demo dağıtımında (bkz. DEPLOY.md) günlük `DAILY_BUDGET_USD` harcama tavanı aşıldıysa orkestratöre hiç girmeden reddeder; `cikti_guvenli_mi` cevap kullanıcıya dönmeden önce API key/sır sızıntısı desenlerini redakte eder.

### Text-to-SQL (`sql_uret_ve_calistir`)
- 12 elle yazılmış örnek sorgu + semantik benzerlik seçimi (few-shot)
- LLM hatalı SQL üretirse otomatik düzeltme döngüsü (self-correction)
- Desteklenen tablolar: `kullanicilar`, `bolumler`, `akademisyenler`, `ogrenciler`, `dersler`, `notlar`, `projeler`

### Belge RAG (`RagManager`)
- Embedding: `intfloat/multilingual-e5-small` (HuggingFace, yerel)
- Chunk: embedding modelinin kendi tokenizer'ıyla ölçülen 400 token, 80 token overlap (önceden karakter sayısıyla ölçülüyordu, model limitini aşma riski taşıyordu)
- Eşik: benzerlik=0.45, fallback=0.1, max_chunks=20
- Çok belgeli sorgularda k orantısal dağıtılır

### Web Crawler (`website_to_rag`)
- `FIRECRAWL_API_KEY` tanımlıysa Firecrawl API'si kullanılır (JS render, temiz markdown çıktısı); tanımlı değilse veya çağrı başarısız olursa otomatik olarak klasik tarayıcıya düşülür
- Klasik tarayıcı: robots.txt'e saygılı, maksimum 30 sayfa, 0.3s gecikme, HTML → temiz metin
- Her iki yol da sonucu aynı şekilde `RagManager.add_document`'a besler

### LLM Desteği
- **ChatGPT:** `gpt-4o-mini` ($0.30/1M token)
- **Gemini:** `gemini-flash-latest` ($0.075/1M token)
- Çalışma anında model değiştirilebilir
- Per-konuşma token & maliyet takibi

## Önemli Tasarım Kararları

- **Lazy loading:** ML kütüphaneleri ilk API isteğine kadar yüklenmez → hızlı başlangıç
- **builtins injection:** Büyük modüller Python builtins'e kaydedilir, iç içe fonksiyonlarda tekrar import olmaz
- **Katmanlı backend:** `core/` (altyapı) → `services/` (iş mantığı) → `routes/` (Flask Blueprint'leri); paylaşılan durum `core/state.py::AppState` üzerinden tek noktadan yönetilir
- **Bağlam penceresi:** Son 5 konuşma turu prompt'a eklenir
- **Event-based streaming:** `services/chat.py::_chat_akisi` sohbet üretiminin tek kaynağı — ilerleme olayları (`plan`, `adim_basladi`, `adim_bitti`, `birlestiriliyor`, `final`) yield eden bir generator. `chat_yanit_uret` (senkron, `/api/chat`) bunu tüketip sadece `final`'i döner; `chat_yanit_uret_stream` (`/api/chat/stream`, SSE) tüm olayları frontend'e canlı iletir

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| POST | `/api/init` | Sistemi başlat (modeller + DB) |
| POST | `/api/chat` | Mesaj gönder, yanıt al (senkron, tek JSON) |
| POST | `/api/chat/stream` | Aynı işi yapar, Server-Sent Events ile orkestratör adımlarını canlı yayınlar |
| GET/POST/DELETE | `/api/conversations/*` | Konuşma yönetimi |
| GET/POST/DELETE | `/api/documents/*` | Belge yönetimi |
| POST | `/api/crawl` | Web sitesi tara ve RAG'a ekle |
| GET | `/api/stats` | Global token/maliyet istatistikleri |

## Ortam Değişkenleri (`.env`)

```
OPENAI_API_KEY=...      # ChatGPT için
GOOGLE_API_KEY=...      # Gemini için
FIRECRAWL_API_KEY=...   # Web taraması için (opsiyonel, yoksa klasik tarayıcı kullanılır)
SECRET_KEY=...          # Flask oturum imzalama anahtarı (prod'da sabit değer şart)
DAILY_BUDGET_USD=3.0    # Herkese açık demo'da günlük LLM harcama tavanı (bkz. DEPLOY.md)
FLASK_DEBUG=0           # 1 sadece yerel geliştirmede; prod'da asla (uzaktan kod çalıştırma riski)
```

## Dağıtım

`DEPLOY.md`: DigitalOcean Droplet + gunicorn + nginx + Let's Encrypt ile herkese
açık demo dağıtımı rehberi (`deploy/` altında systemd/nginx config'leri).

## Dosya Yapısı

```
academic_chatbot/
├── app.py                    # Flask app + Blueprint kaydı + giriş noktası
├── core/                     # Çekirdek altyapı (state, LLM, lazy-loading, DB kurulumu)
├── services/                 # İş mantığı (RAG, Text-to-SQL, orkestratör, sohbet, konuşma, crawler)
├── routes/                   # Flask Blueprint'leri
├── requirements.txt          # Python bağımlılıkları (yerel + prod ortak)
├── requirements-deploy.txt   # Sadece prod (gunicorn, Linux)
├── deploy/                   # systemd servis + nginx reverse proxy config'leri
├── DEPLOY.md                 # DigitalOcean dağıtım rehberi
├── .env                      # API anahtarları (git'e ekleme!)
├── demo_okul.db               # SQLite DB (otomatik oluşturulur)
├── templates/index.html      # Web arayüzü
├── uploads/                  # Yüklenen belgeler
├── chroma_db/                # Kalıcı vektör veritabanı
├── scratch/                  # Geliştirme testleri
└── venv/                     # Sanal ortam
```
