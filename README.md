# Akademik RAG & Agentic Chatbot

Gradio yerine modern web arayüzüyle çalışan yerel Flask uygulaması.

## Özellikler

- **Intent Routing** — DB_QUERY / SEARCH / META / GENERAL otomatik yönlendirme
- **Text-SQL (Few-Shot RAG)** — Akademik veritabanına doğal dil sorguları
- **Belge RAG** — PDF/XLSX yükleyip üzerinden soru sorma
- **Web Crawler** — Herhangi bir siteyi tarayıp RAG'e ekleme
- **Multi-conversation** — Birden fazla sohbet yönetimi
- **Token & Maliyet takibi** — GPT-4o-mini ve Gemini Flash desteği

## Kurulum

### 1. Sanal ortam oluşturun
```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
```

### 2. Bağımlılıkları yükleyin
```bash
pip install -r requirements.txt
```

### 3. API anahtarlarınızı ayarlayın
```bash
# Linux/Mac
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="AIza..."

# Windows (PowerShell)
$env:OPENAI_API_KEY="sk-..."
$env:GOOGLE_API_KEY="AIza..."
```

Ya da proje kökünde `.env` dosyası oluşturun:
```
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
```
ve `app.py`'ye şunu ekleyin (en üste):
```python
from dotenv import load_dotenv
load_dotenv()
```
(önce `pip install python-dotenv`)

### 4. Uygulamayı başlatın
```bash
python app.py
```

### 5. Tarayıcıda açın
```
http://localhost:5000
```

## Proje Yapısı

```
academic_chatbot/
├── app.py              ← Flask backend (tüm AI mantığı)
├── requirements.txt    ← Python bağımlılıkları
├── README.md
├── templates/
│   └── index.html      ← Modern web arayüzü
├── uploads/            ← Yüklenen belgeler (otomatik oluşur)
├── chroma_db/          ← Vektör veritabanı (otomatik oluşur)
└── demo_okul.db        ← Demo SQLite DB (otomatik oluşur)
```

## Demo Veritabanı

Uygulama ilk çalıştırıldığında otomatik oluşturulur (veya hazır gelen `demo_okul.db` okunur):
- 5 Bölüm, 10 Akademisyen, 25 Öğrenci, 12 Ders, 55+ Not Kaydı ve 8 Bitirme Projesi

Örnek sorgular:
- "Bilgisayar Mühendisliği'nde kaç öğrenci var?"
- "Ali Kaya'nın ders notlarını ve ortalamalarını getir."
- "Yapay Zeka dersini kim veriyor?"
- "Ahmet Yılmaz hocanın danışmanlığındaki öğrenciler kimlerdir?"
- "Yapay Zeka veya NLP alanındaki bitirme projeleri hangileridir?"
- "AKTS kredisi 5'ten büyük olan dersleri ve kredilerini listeleyin."

## Sistem Gereksinimleri

- Python 3.10+
- ~2GB RAM (embedding modeli için)
- İnternet bağlantısı (ilk çalıştırmada model indirir)

## API Notları

- **ChatGPT**: OpenAI API anahtarı gerekli (`gpt-4o-mini`)
- **Gemini**: Google API anahtarı gerekli (`gemini-flash-latest`)
- İkisinden biri yoksa o model seçildiğinde hata döner

