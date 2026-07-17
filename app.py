"""
Akademik RAG & Agentic Chatbot — Flask Backend

Bu dosya, uygulamanın arka uç (backend) mantığını içerir. Flask sunucusu, veritabanı bağlantısı,
doğal dil işleme (NLP), RAG (Retrieval-Augmented Generation) mekanizmaları, internet araması
ve web tarayıcı (crawler) bileşenleri bu dosya üzerinden koordine edilir.
"""

import sys
# Windows sistemlerinde emojilerin ve Türkçe karakterlerin konsola sorunsuz yazdırılabilmesi için
# standart çıktı ve hata çıktı kanallarını UTF-8 kodlamasına zorluyoruz.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Gerekli standart Python kütüphanelerini içe aktarıyoruz
import re, json, sqlite3, ast, os, shutil, time, uuid
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# .env dosyasındaki ortam değişkenlerini (API anahtarları vb.) yüklüyoruz
load_dotenv()

# Flask uygulamasını başlatıyor ve dosya yükleme klasörünü / boyut limitini yapılandırıyoruz
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Maksimum yüklenebilir dosya boyutu: 50MB
os.makedirs('uploads', exist_ok=True) # Yükleme klasörü yoksa otomatik oluşturulur

# ─── Lazy imports (Gecikmeli Yükleme) Tanımlamaları ──────────────────────────
# Uygulama başlangıcını hızlandırmak için ağır makine öğrenmesi ve LangChain kütüphanelerini
# ilk API isteği gelene kadar veya ilgili fonksiyon çağrılana kadar yüklemiyoruz (Lazy Load).
_imports_done = False       # Kütüphanelerin yüklenip yüklenmediğini tutan bayrak
embedding_model = None      # Metin vektörleştirme modeli (SentenceEmbeddings)
llm_default = None          # Varsayılan Büyük Dil Modeli (ChatGPT veya Gemini)
db = None                   # SQLAlchemy tabanlı SQLite veritabanı arayüzü
CACHED_SCHEMA = ''          # SQLite veritabanı şema bilgisi (Text-to-SQL için context sağlar)
rag_manager = None          # Vektör veritabanı (Chroma DB) ve belge sorgulama yöneticisi
search_tool = None          # DuckDuckGo arama motoru aracı
SEARCH_OK = False           # İnternet arama modülünün aktif olup olmadığını tutar
example_selector = None     # Benzer SQL örneklerini seçen anlamsal eşleştirici (Few-Shot için)
example_prompt = None       # Örnek SQL şablon yapısı
global_tokens = 0           # Sunucu genelinde harcanan toplam token sayısı
global_cost_usd = 0.0       # Sunucu genelinde oluşan toplam API maliyeti (USD)

def ensure_imports():
    """
    LangChain, Chroma, HuggingFace ve model kütüphanelerini belleğe yükler.
    Eğer veritabanı mevcut değilse otomatik olarak demo verileriyle oluşturur.
    Ayrıca Few-Shot SQL örnek seçicisini ve embedding modelini hazırlar.
    """
    global _imports_done, embedding_model, llm_default, db, CACHED_SCHEMA
    global rag_manager, search_tool, SEARCH_OK, example_selector, example_prompt

    # Eğer kütüphaneler daha önce yüklendiyse işlemi tekrarlamadan geri dön
    if _imports_done:
        return

    # Ağır kütüphanelerin gecikmeli (lazy) import işlemleri
    import pandas as pd
    from sqlalchemy import create_engine
    from langchain_community.utilities import SQLDatabase
    from langchain_community.tools import DuckDuckGoSearchRun
    from langchain_community.document_loaders import PyPDFLoader, TextLoader
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_core.example_selectors import SemanticSimilarityExampleSelector
    from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_openai import ChatOpenAI
    from langchain_google_genai import ChatGoogleGenerativeAI

    # Diğer fonksiyonların içerisinden bu modüllere erişebilmek için yerleşik (builtins) nesnelere ekliyoruz
    import builtins
    builtins._pandas = pd
    builtins._Chroma = Chroma
    builtins._PyPDFLoader = PyPDFLoader
    builtins._TextLoader = TextLoader
    builtins._RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter
    builtins._HuggingFaceEmbeddings = HuggingFaceEmbeddings
    builtins._FewShotPromptTemplate = FewShotPromptTemplate
    builtins._PromptTemplate = PromptTemplate
    builtins._ChatOpenAI = ChatOpenAI
    builtins._ChatGoogleGenerativeAI = ChatGoogleGenerativeAI
    builtins._SQLDatabase = SQLDatabase
    builtins._SemanticSimilarityExampleSelector = SemanticSimilarityExampleSelector

    print('📦 Kütüphaneler yüklendi.')

    # ── Demo SQLite Veritabanı Kontrolü ve Kurulumu ───────────────────────────
    db_filename = 'demo_okul.db'
    recreate = False
    # Veritabanının varlığını ve tabloların eksiksiz olduğunu kontrol ediyoruz
    if os.path.exists(db_filename):
        try:
            conn = sqlite3.connect(db_filename)
            cur = conn.cursor()
            # Kritik tablolardan birinin (örneğin projeler) varlığını kontrol ediyoruz
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projeler'")
            if not cur.fetchone():
                recreate = True
            conn.close()
        except:
            recreate = True
            
    # Eğer veritabanı dosyası bozuksa veya tablolar eksikse dosyayı silip sıfırdan kuracağız
    if recreate and os.path.exists(db_filename):
        try:
            os.remove(db_filename)
            print('♻️ Eski veritabanı şeması silindi, yeniden kurulacak.')
        except Exception as e:
            print(f'♻️ Eski veritabanı silinemedi: {e}')

    # Veritabanı dosyası yoksa verileri oluştur
    if not os.path.exists(db_filename):
        _setup_database(db_filename)

    # LangChain SQLDatabase modülü ile veritabanına bağlanıp şemayı önbelleğe (cache) alıyoruz
    try:
        db = SQLDatabase.from_uri(f'sqlite:///{db_filename}')
        CACHED_SCHEMA = db.get_table_info()
        print('✅ Veritabanı bağlantısı OK')
    except Exception as e:
        print(f'DB Hata: {e}')
        db = None
        CACHED_SCHEMA = ''

    # ── Embedding Model ve Few-Shot Örnek Seçici Kurulumu ────────────────────
    print('⚙️ Embedding modeli yükleniyor...')
    # Metinleri anlamsal vektörlere dönüştürmek için hafif ve çok dilli (multilingual) e5 modelini yüklüyoruz
    embedding_model = HuggingFaceEmbeddings(model_name='intfloat/multilingual-e5-small')

    # LLM'in doğal dili doğru SQL sorgularına dönüştürmesini sağlamak için Few-Shot (Örnek tabanlı) sorgular
    ornekler = [
        {'soru': 'Bilgisayar Mühendisliği bölümünde kaç öğrenci var?',
         'sql':  "SELECT count(*) FROM ogrenciler JOIN bolumler ON ogrenciler.bolumid = bolumler.bolumid WHERE bolumler.bolumadi LIKE '%Bilgisayar%';"},
        {'soru': "Ali Kaya'nın notları kaç?",
         'sql':  "SELECT dersler.dersadi, notlar.vize, notlar.final, notlar.ortalama, notlar.harfnotu, notlar.basaridurumu FROM notlar JOIN ogrenciler ON notlar.ogrenciid = ogrenciler.ogrenciid JOIN dersler ON notlar.dersid = dersler.dersid WHERE ogrenciler.ad LIKE '%Ali%' AND ogrenciler.soyad LIKE '%Kaya%';"},
        {'soru': 'Yapay Zeka dersinden kaç kişi geçti?',
         'sql':  "SELECT count(*) FROM notlar JOIN dersler ON notlar.dersid = dersler.dersid WHERE dersler.dersadi LIKE '%Yapay Zeka%' AND notlar.basaridurumu = 'Geçti';"},
        {'soru': 'Okulda hangi bölümler var?', 'sql': 'SELECT bolumadi FROM bolumler;'},
        {'soru': 'Ahmet Yılmaz hocanın hangi dersleri var?',
         'sql':  "SELECT dersler.dersadi FROM dersler JOIN akademisyenler ON dersler.akademisyenid = akademisyenler.akademisyenid WHERE akademisyenler.ad LIKE '%Ahmet%' AND akademisyenler.soyad LIKE '%Yılmaz%';"},
        {'soru': 'Okulda toplam kaç öğrenci var?', 'sql': 'SELECT count(*) FROM ogrenciler;'},
        {'soru': 'Algoritma dersini kim veriyor?',
         'sql':  "SELECT akademisyenler.ad, akademisyenler.soyad, akademisyenler.unvan FROM dersler JOIN akademisyenler ON dersler.akademisyenid = akademisyenler.akademisyenid WHERE dersler.dersadi LIKE '%Algoritma%';"},
        {'soru': 'Ahmet Yılmaz hocanın danışmanlığındaki öğrenciler kimlerdir?',
         'sql':  "SELECT ogrenciler.ad, ogrenciler.soyad FROM ogrenciler JOIN akademisyenler ON ogrenciler.danismanid = akademisyenler.akademisyenid WHERE akademisyenler.ad LIKE '%Ahmet%' AND akademisyenler.soyad LIKE '%Yılmaz%';"},
        {'soru': 'Yapay Zeka veya NLP alanındaki bitirme projeleri hangileridir?',
         'sql':  "SELECT projeler.baslik, projeler.konu FROM projeler WHERE projeler.baslik LIKE '%Yapay Zeka%' OR projeler.konu LIKE '%Yapay Zeka%' OR projeler.baslik LIKE '%NLP%' OR projeler.konu LIKE '%NLP%';"},
        {'soru': 'AKTS kredisi 5\'ten büyük olan dersleri ve kredilerini listeleyin.',
         'sql':  "SELECT dersadi, akts FROM dersler WHERE akts > 5;"},
        {'soru': 'Yazılım Mühendisliği dersinden AA alan öğrencilerin isimleri nelerdir?',
         'sql':  "SELECT ogrenciler.ad, ogrenciler.soyad FROM notlar JOIN ogrenciler ON notlar.ogrenciid = ogrenciler.ogrenciid JOIN dersler ON notlar.dersid = dersler.dersid WHERE dersler.dersadi LIKE '%Yazılım Mühendisliği%' AND notlar.harfnotu = 'AA';"}
    ]

    # SQL oluşturma adımında kullanıcı sorusuna en yakın 3 SQL örneğini seçmek için
    # anlamsal benzerlik arama altyapısını kuruyoruz (SemanticSimilarityExampleSelector)
    example_prompt_obj = PromptTemplate(
        input_variables=['soru', 'sql'],
        template='Soru: {soru}\nSQL: {sql}'
    )
    example_selector = SemanticSimilarityExampleSelector.from_examples(
        ornekler, embedding_model, Chroma, k=3
    )
    example_prompt = example_prompt_obj

    # ── Varsayılan Büyük Dil Modeli (LLM) Yapılandırması ──────────────────────
    openai_ok = bool(os.environ.get('OPENAI_API_KEY'))
    gemini_ok = bool(os.environ.get('GOOGLE_API_KEY'))
    if openai_ok:
        try:
            llm_default = _get_llm('chatgpt')
            print('✅ Varsayılan LLM hazır (ChatGPT)!')
        except Exception as e:
            print(f'⚠️ ChatGPT başlatılamadı: {e}')
            llm_default = None
    elif gemini_ok:
        try:
            llm_default = _get_llm('gemini')
            print('✅ Varsayılan LLM hazır (Gemini)!')
        except Exception as e:
            print(f'⚠️ Gemini başlatılamadı: {e}')
            llm_default = None
    else:
        llm_default = None
        print('⚠️ Uyarı: OpenAI veya Google API anahtarı bulunamadı. Lütfen .env dosyasını ayarlayın.')

    # ── Belge Analiz Yöneticisi (RAG Manager) Kurulumu ────────────────────────
    rag_manager = RagManager()
    rag_manager.db = db

    # ── İnternet Arama Motoru Entegrasyonu ────────────────────────────────────
    try:
        search_tool = DuckDuckGoSearchRun()
        SEARCH_OK = True
    except Exception as e:
        print(f'⚠️ DuckDuckGo başlatılamadı: {e}')
        SEARCH_OK = False

    _imports_done = True
    print('✅ Sistem hazır!')


def _setup_database(db_filename):
    """
    Uygulama ilk kez başlatıldığında veya veritabanı silindiğinde çalıştırılır.
    SQLite üzerinde akademik şemayı (Öğrenciler, Akademisyenler, Dersler, Notlar, Projeler) oluşturur
    ve tohum (seed) verilerini ekler.
    """
    conn = sqlite3.connect(db_filename)
    cur = conn.cursor()
    
    # Tablo Tanımlamaları:
    # 1. Kullanıcılar tablosu (Gelecekteki giriş/auth sistemleri için taslak)
    cur.execute('CREATE TABLE kullanicilar   (kullaniciid   INTEGER PRIMARY KEY, email TEXT, sifrehash TEXT)')
    # 2. Üniversite Bölümleri
    cur.execute('CREATE TABLE bolumler       (bolumid       INTEGER PRIMARY KEY, bolumadi TEXT)')
    # 3. Akademisyenler (Hocalar)
    cur.execute('CREATE TABLE akademisyenler (akademisyenid INTEGER PRIMARY KEY, ad TEXT, soyad TEXT, unvan TEXT, bolumid INTEGER, eposta TEXT)')
    # 4. Öğrenciler (Bölüm ve Danışman akademisyen ilişkili)
    cur.execute('CREATE TABLE ogrenciler     (ogrenciid     INTEGER PRIMARY KEY, ad TEXT, soyad TEXT, bolumid INTEGER, eposta TEXT, kayityili INTEGER, danismanid INTEGER)')
    # 5. Dersler (Bölüm, Dersi veren hoca ve AKTS kredisi ilişkili)
    cur.execute('CREATE TABLE dersler        (dersid        INTEGER PRIMARY KEY, dersadi TEXT, bolumid INTEGER, akademisyenid INTEGER, akts INTEGER)')
    # 6. Notlar (Vize, final notları ve hesaplanan ortalama, harf notu, geçme/kalma durumu)
    cur.execute('CREATE TABLE notlar         (notid         INTEGER PRIMARY KEY, ogrenciid INTEGER, dersid INTEGER, vize INTEGER, final INTEGER, ortalama REAL, harfnotu TEXT, basaridurumu TEXT)')
    # 7. Mezuniyet/Bitirme Projeleri (Öğrenci ve Danışman hoca ilişkili)
    cur.execute('CREATE TABLE projeler       (projeid       INTEGER PRIMARY KEY, baslik TEXT, konu TEXT, ogrenciid INTEGER, danismanid INTEGER)')

    cur.executemany('INSERT INTO kullanicilar VALUES (?,?,?)', [
        (1,'admin@admin.com','123456'),
        (2,'ogretmen@uni.com','pass123')
    ])
    
    cur.executemany('INSERT INTO bolumler VALUES (?,?)', [
        (1, 'Bilgisayar Mühendisliği'),
        (2, 'Yazılım Mühendisliği'),
        (3, 'Elektrik-Elektronik Mühendisliği'),
        (4, 'Endüstri Mühendisliği'),
        (5, 'Yapay Zeka Mühendisliği')
    ])

    cur.executemany('INSERT INTO akademisyenler VALUES (?,?,?,?,?,?)', [
        (1, 'Ahmet', 'Yılmaz', 'Prof. Dr.', 1, 'ahmet.yilmaz@uni.edu.tr'),
        (2, 'Fatma', 'Çelik', 'Doç. Dr.', 2, 'fatma.celik@uni.edu.tr'),
        (3, 'Mehmet', 'Demir', 'Dr. Öğr. Üyesi', 3, 'mehmet.demir@uni.edu.tr'),
        (4, 'Zeynep', 'Arslan', 'Prof. Dr.', 1, 'zeynep.arslan@uni.edu.tr'),
        (5, 'Hüseyin', 'Kaya', 'Doç. Dr.', 4, 'huseyin.kaya@uni.edu.tr'),
        (6, 'Elif', 'Şahin', 'Dr. Öğr. Üyesi', 2, 'elif.sahin@uni.edu.tr'),
        (7, 'Murat', 'Özkan', 'Prof. Dr.', 3, 'murat.ozkan@uni.edu.tr'),
        (8, 'Selin', 'Aktaş', 'Dr. Öğr. Üyesi', 5, 'selin.aktas@uni.edu.tr'),
        (9, 'Caner', 'Soylu', 'Prof. Dr.', 5, 'caner.soylu@uni.edu.tr'),
        (10, 'Aslı', 'Yurt', 'Doç. Dr.', 4, 'asli.yurt@uni.edu.tr')
    ])

    cur.executemany('INSERT INTO ogrenciler VALUES (?,?,?,?,?,?,?)', [
        (1, 'Ali', 'Kaya', 1, 'ali.kaya@std.uni.edu.tr', 2022, 1),
        (2, 'Ayşe', 'Demir', 2, 'ayse.demir@std.uni.edu.tr', 2021, 2),
        (3, 'Cemil', 'Arslan', 1, 'cemil.arslan@std.uni.edu.tr', 2023, 4),
        (4, 'Deniz', 'Yılmaz', 3, 'deniz.yilmaz@std.uni.edu.tr', 2022, 3),
        (5, 'Emre', 'Çelik', 1, 'emre.celik@std.uni.edu.tr', 2022, 1),
        (6, 'Fatma', 'Kara', 2, 'fatma.kara@std.uni.edu.tr', 2021, 6),
        (7, 'Gizem', 'Şahin', 4, 'gizem.sahin@std.uni.edu.tr', 2022, 5),
        (8, 'Hakan', 'Doğan', 4, 'hakan.dogan@std.uni.edu.tr', 2023, 10),
        (9, 'İrem', 'Polat', 2, 'irem.polat@std.uni.edu.tr', 2022, 6),
        (10, 'Kerem', 'Yıldız', 1, 'kerem.yildiz@std.uni.edu.tr', 2022, 4),
        (11, 'Lale', 'Erdoğan', 3, 'lale.erdogan@std.uni.edu.tr', 2021, 7),
        (12, 'Mert', 'Güneş', 4, 'mert.gunes@std.uni.edu.tr', 2022, 5),
        (13, 'Nisan', 'Aydın', 2, 'nisan.aydin@std.uni.edu.tr', 2021, 2),
        (14, 'Okan', 'Kurt', 4, 'okan.kurt@std.uni.edu.tr', 2023, 10),
        (15, 'Pınar', 'Bulut', 1, 'pinar.bulut@std.uni.edu.tr', 2022, 1),
        (16, 'Burak', 'Şen', 5, 'burak.sen@std.uni.edu.tr', 2022, 8),
        (17, 'Gamze', 'Tekin', 5, 'gamze.tekin@std.uni.edu.tr', 2022, 9),
        (18, 'Serkan', 'Ak', 5, 'serkan.ak@std.uni.edu.tr', 2023, 8),
        (19, 'Melis', 'Can', 3, 'melis.can@std.uni.edu.tr', 2022, 3),
        (20, 'Umut', 'Kılıç', 3, 'umut.kilic@std.uni.edu.tr', 2023, 7),
        (21, 'Ece', 'Koç', 2, 'ece.koc@std.uni.edu.tr', 2022, 2),
        (22, 'Yiğit', 'Öztürk', 1, 'yigit.ozturk@std.uni.edu.tr', 2021, 4),
        (23, 'Başak', 'Ay', 4, 'basak.ay@std.uni.edu.tr', 2022, 5),
        (24, 'Kaan', 'Taş', 5, 'kaan.tas@std.uni.edu.tr', 2022, 9),
        (25, 'Sinem', 'Yıldırım', 5, 'sinem.yildirim@std.uni.edu.tr', 2021, 8)
    ])

    cur.executemany('INSERT INTO dersler VALUES (?,?,?,?,?)', [
        (1, 'Yapay Zeka', 1, 1, 6),
        (2, 'Algoritma ve Veri Yapıları', 1, 4, 7),
        (3, 'Nesne Yönelimli Programlama', 2, 6, 5),
        (4, 'Web Programlama', 2, 2, 6),
        (5, 'Devre Teorisi', 3, 3, 6),
        (6, 'Sinyaller ve Sistemler', 3, 7, 7),
        (7, 'Statik', 4, 5, 5),
        (8, 'Yöneylem Araştırması', 4, 10, 7),
        (9, 'Derin Öğrenme', 5, 9, 7),
        (10, 'Doğal Dil İşleme', 5, 8, 6),
        (11, 'Veritabanı Yönetim Sistemleri', 1, 1, 5),
        (12, 'Yazılım Mühendisliği Temelleri', 2, 2, 6)
    ])

    raw_notlar = [
        (1, 1, 78, 88), (1, 2, 55, 49), (1, 11, 80, 85),
        (2, 3, 90, 95), (2, 4, 85, 78), (2, 12, 75, 80),
        (3, 1, 70, 75), (3, 2, 40, 35), (3, 11, 62, 58),
        (4, 5, 60, 65), (4, 6, 55, 50),
        (5, 1, 85, 90), (5, 2, 66, 70), (5, 11, 92, 95),
        (6, 3, 65, 70), (6, 4, 45, 40), (6, 12, 58, 62),
        (7, 7, 80, 78), (7, 8, 72, 68),
        (8, 7, 55, 48), (8, 8, 88, 92),
        (9, 3, 82, 85), (9, 4, 90, 88), (9, 12, 76, 72),
        (10, 1, 60, 55), (10, 2, 88, 91), (10, 11, 70, 72),
        (11, 5, 95, 98), (11, 6, 88, 90),
        (12, 7, 50, 45), (12, 8, 62, 58),
        (13, 3, 82, 86), (13, 4, 78, 80), (13, 12, 85, 88),
        (14, 7, 68, 72), (14, 8, 55, 60),
        (15, 1, 88, 92), (15, 2, 75, 78), (15, 11, 95, 97),
        (16, 9, 85, 90), (16, 10, 75, 70),
        (17, 9, 90, 92), (17, 10, 80, 85),
        (18, 9, 45, 52), (18, 10, 60, 58),
        (19, 5, 72, 76), (19, 6, 68, 70),
        (20, 5, 55, 48), (20, 6, 82, 80),
        (21, 3, 88, 85), (21, 4, 92, 95), (21, 12, 80, 82),
        (22, 1, 90, 92), (22, 2, 82, 85), (22, 11, 88, 90),
        (23, 7, 74, 78), (23, 8, 70, 72),
        (24, 9, 88, 85), (24, 10, 90, 92),
        (25, 9, 78, 82), (25, 10, 85, 88)
    ]

    notlar_data = []
    for idx, (oid, did, vize, final) in enumerate(raw_notlar, start=1):
        ortalama = vize * 0.4 + final * 0.6
        if ortalama >= 90: hn = 'AA'
        elif ortalama >= 85: hn = 'BA'
        elif ortalama >= 80: hn = 'BB'
        elif ortalama >= 75: hn = 'CB'
        elif ortalama >= 70: hn = 'CC'
        elif ortalama >= 60: hn = 'DC'
        elif ortalama >= 50: hn = 'DD'
        elif ortalama >= 40: hn = 'FD'
        else: hn = 'FF'
        bd = 'Geçti' if ortalama >= 50 else 'Kaldı'
        notlar_data.append((idx, oid, did, vize, final, round(ortalama, 2), hn, bd))

    cur.executemany('INSERT INTO notlar VALUES (?,?,?,?,?,?,?,?)', notlar_data)

    cur.executemany('INSERT INTO projeler VALUES (?,?,?,?,?)', [
        (1, "LLM Tabanlı Akademik Asistan", "Doğal Dil İşleme (NLP) ve RAG Mimarileri", 1, 1),
        (2, "Otonom Sürüş için Yapay Zeka Tabanlı Yol Tespiti", "Bilgisayarlı Görü ve Derin Öğrenme", 2, 2),
        (3, "Mikroservis Mimarisi ile E-Ticaret", "Yazılım Tasarımı ve Dağıtık Sistemler", 6, 6),
        (4, "IoT Tabanlı Akıllı Sera Sistemi", "Sensör Ağları ve Mikrodenetleyiciler", 4, 3),
        (5, "Veri Analitiği ile Müşteri Segmentasyonu", "Makine Öğrenmesi ve Kümeleme", 7, 5),
        (6, "Derin Öğrenme ile Tıbbi Görüntü Analizi", "Yapay Zeka Destekli CNN ve Medikal Görüntüleme", 17, 9),
        (7, "Transformatör Modelleri ile Türkçe Soru-Cevap", "BERT ve NLP Model İnce Ayar", 16, 8),
        (8, "Enerji Tüketimi Tahmini", "Zaman Serisi Analizi ve Regresyon", 11, 7)
    ])

    conn.commit()
    conn.close()
    print('✅ Zenginleştirilmiş Demo DB kuruldu.')


# ─── Yardımcı fonksiyonlar ────────────────────────────────────────────────────

def _get_llm(model_name: str):
    if model_name == 'gemini':
        key = os.environ.get('GOOGLE_API_KEY')
        if not key:
            raise ValueError("Google API anahtarı (GOOGLE_API_KEY) bulunamadı. Lütfen .env dosyasını kontrol edin.")
        return _ChatGoogleGenerativeAI(model='gemini-flash-latest', google_api_key=key, temperature=0)
    
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise ValueError("OpenAI API anahtarı (OPENAI_API_KEY) bulunamadı. Lütfen .env dosyasını kontrol edin.")
    return _ChatOpenAI(model='gpt-4o-mini', openai_api_key=key, temperature=0)


def _calculate_cost(model_name: str, tokens: int) -> float:
    mn = model_name.lower()
    if 'gpt-4o-mini' in mn: return (tokens / 1_000_000) * 0.30
    if 'gpt-4o'      in mn: return (tokens / 1_000_000) * 3.75
    if 'gpt'         in mn: return (tokens / 1_000_000) * 0.30
    if 'gemini'      in mn: return (tokens / 1_000_000) * 0.075
    return 0.0


def llm_invoke_tracked(llm, input_data):
    global global_tokens, global_cost_usd
    response = llm.invoke(input_data)
    tokens = 0
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        tokens = response.usage_metadata.get('total_tokens', 0)
    if tokens == 0 and hasattr(response, 'response_metadata') and response.response_metadata:
        tu = response.response_metadata.get('token_usage', {})
        tokens = tu.get('total_tokens', 0)
    if tokens > 0:
        global_tokens += tokens
        mn = getattr(llm, 'model_name', getattr(llm, 'model', 'unknown'))
        global_cost_usd += _calculate_cost(mn, tokens)
    return response


def extract_text(response) -> str:
    if hasattr(response, 'content'):
        c = response.content
        if isinstance(c, str): return c.strip()
        if isinstance(c, list):
            return ''.join(p['text'] if isinstance(p, dict) else str(p) for p in c).strip()
        return str(c).strip()
    return str(response).strip()


def sql_temizle(t: str) -> str:
    # Markdown kod bloklarını temizle (```sql ... ``` veya ``` ... ```)
    t = re.sub(r'```(?:sql)?\s*', '', t, flags=re.IGNORECASE).strip()
    t = t.replace('`', '"')
    # SELECT sorgusunu bul (noktalı virgül opsiyonel)
    m = re.search(r'SELECT\b.*', t, re.DOTALL | re.IGNORECASE)
    if m: t = m.group(0).strip()
    # Sondaki kalıntı tırnak/çizgileri temizle
    t = re.sub(r'["\s]+$', '', t).strip()
    t = re.sub(r'ILIKE', 'LIKE', t, flags=re.IGNORECASE)
    t = re.sub(r'"([^"]+)"', r"'\1'", t)
    return t


def niyet_siniflandir(soru: str, llm=None, gecmis: str = '') -> str:
    """
    Kullanıcıdan gelen soruyu analiz ederek sistemin hangi kanala (Niyete) gideceğini belirler.
    Kanallar:
    - DB_QUERY: SQLite akademik veritabanına sorgu atılacak (Öğrenci, not, ders, proje sorguları)
    - RAG: Yüklü belgeler (CV, PDF, TXT vb.) üzerinden cevaplanacak sorular
    - SEARCH: DuckDuckGo üzerinden internet araması yapılacak güncel konular
    - META: Chatbotun kendi yapısı (kullanılan model, yüklü dosyalar vb.) hakkındaki sorular
    - GENERAL: Genel selamlaşma, sohbet veya fikir alışverişi
    """
    llm = llm or llm_default
    s_lower = soru.lower()

    # 1. Aşama: Hızlı Selamlaşma / Genel Sohbet Kontrolü (Kural Tabanlı)
    selamlama = ['selam', 'merhaba', 'hey', 'nasılsın', 'naber',
                 'günaydın', 'iyi akşamlar', 'iyi geceler', 'hi ', 'hello']
    if any(k in s_lower for k in selamlama):
        return 'GENERAL'

    # 1b. Aşama: Hızlı Sistem Durumu (Meta) Kontrolü (Kural Tabanlı)
    # Sadece kendi sistemimizle ilgili doğrudan durum sorgularını yakalamak için anahtar kelimeleri daraltıyoruz.
    meta_kelimeleri = [
        'seçili model', 'model seçili',
        'aktif model', 'model aktif',
        'seçili llm', 'llm seçili',
        'aktif llm', 'llm aktif',
        'hangi modeli kullan',
        'yüklü belge', 'belgeler yüklü',
        'yüklü dosya', 'dosyalar yüklü'
    ]
    if any(k in s_lower for k in meta_kelimeleri):
        return 'META'

    # 2. Aşama: Yüklü belge varsa RAG keyword kontrolü (DB'den önce)
    rag_keywords = ['aday', 'cv', 'özgeçmiş', 'ozgecmis', 'belge', 'dosya',
                    'başvuru', 'basvuru', 'sertifika', 'deneyim', 'yetenek',
                    'beceri', 'mezun', 'diploma', 'işe al', 'ise al']
    if rag_manager and rag_manager.documents and any(k in s_lower for k in rag_keywords):
        return 'RAG'

    # 3. Aşama: Veritabanı Kelimeleri Kontrolü (Hızlı bypass ile API maliyetini düşürme)
    db_keywords = ['öğrenci', 'ogrenci', 'ders', 'not', 'vize', 'final',
                   'hoca', 'akademisyen', 'bölüm', 'bolum', 'proje', 'tez',
                   'danışman', 'danisman', 'akts', 'ortalama', 'harf', 'eposta', 'e-posta']
    if any(k in s_lower for k in db_keywords):
        return 'DB_QUERY'

    # 4. Aşama: Belirsiz durumlarda LLM (Yapay Zeka) ile niyet sınıflandırma
    has_docs = bool(rag_manager and rag_manager.documents)
    doc_names = list(rag_manager.documents.keys()) if has_docs else []
    doc_info = f"(Yuklu Dosyalar: {doc_names})" if has_docs else "(Dosya yok)"
    
    prompt = f"""Asagidaki soruyu siniflandir. SADECE tek bir kelime yaz:
DB_QUERY  → Akademik veritabanindaki ogrenci/ders/not/hoca/bolum/proje/danisman/akts/ortalama/harfnotu bilgisi soruluyor
RAG       → Yuklu dosyalardan/belgelerden cevaplanmasi gereken veya bu dosyalardaki konularla/kisilerle ilgili olan sorular {doc_info}
SEARCH    → Internette aranmasi gereken guncel veya genel bir bilgi soruluyor
GENERAL   → Genel sohbet, selamlasma, tavsiye, fikir sorma
META      → Chatbotun kendi durumu hakkinda soru (yuklu belge, model vb.)

ONEMLI: Soru, yuklu dosya isimlerinde gecen veya ima edilen kisiler/konular (Ornegin: 'egemen bozca' veya 'egebo') ile ilgiliyse, veritabaninda bu kisiler/konular bulunmayacagi icin bunu kesinlikle RAG olarak siniflandirmalisin.

ONEMLI: Soru "isimleri", "adlari", "onlar", "bunlar", "kac tane", "detaylari", "o kisi", "ayni" gibi onceki konusmaya atifta bulunan ifadeler iceriyorsa, onceki konusmanin kategorisini kullan.

Önceki konuşma (bağlam için kullan):
{gecmis or 'Yok'}

Soru: "{soru}"

Cevap (sadece bir kelime):"""
    try:
        r = extract_text(llm_invoke_tracked(llm, prompt)).strip().upper()
        for kategori in ['DB_QUERY', 'RAG', 'SEARCH', 'META', 'GENERAL']:
            if kategori in r:
                # RAG seçildiyse belge yoksa GENERAL'e düşür
                if kategori == 'RAG' and not has_docs:
                    return 'GENERAL'
                return kategori
    except:
        pass
    return 'GENERAL'


def soruyu_baglamla_guncelle(soru: str, gecmis: str, llm=None) -> str:
    """
    Konuşma geçmişini kullanarak kullanıcının son sorusunu bağlamlaştırır.
    Zamirleri (o, onun, onlar, bu, vb.) veya atıfları geçmişteki gerçek isimlerle/konularla değiştirir.
    Eğer geçmiş yoksa veya son soru bağımsızsa orijinal soruyu aynen döndürür.
    """
    if not gecmis:
        return soru
    llm = llm or llm_default
    has_docs = bool(rag_manager and rag_manager.documents)
    doc_names = list(rag_manager.documents.keys()) if has_docs else []
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
            yeni_soru = re.sub(r'^["\']|["\']$', '', yeni_soru).strip()
            return yeni_soru
    except Exception as e:
        print(f"⚠️ Soruyu bağlamlaştırma hatası: {e}")
    return soru


def genel_cevap_uret(soru: str, gecmis: str, llm=None) -> str:
    llm = llm or llm_default
    return extract_text(llm_invoke_tracked(llm,
        f'Sen yardımcı bir Türkçe asistansın.\n\n'
        f'Önceki konuşma: {gecmis or "Yok"}\nKullanıcı: {soru}\nAsistan:'
    ))


def internet_arama_yap(soru: str, llm=None) -> str:
    llm = llm or llm_default
    if not SEARCH_OK: return genel_cevap_uret(soru, '', llm)
    try:
        sonuc = search_tool.run(soru)
        return extract_text(llm_invoke_tracked(llm,
            f'Arama sonuçlarına dayanarak Türkçe cevap ver.\nSoru: {soru}\nSonuçlar: {sonuc}\nCevap:'
        ))
    except Exception as e:
        return f'İnternet araması yapılamadı: {e}'


def sql_uret_ve_calistir(soru: str, gecmis: str = '', llm=None):
    """
    Doğal dil sorusunu veritabanı şemasına uygun SQLite SELECT sorgusuna dönüştürür.
    Sorguyu çalıştırır, hata oluşursa LLM ile otomatik self-correction (düzeltme) döngüsü çalıştırır.
    """
    llm = llm or llm_default
    
    # 1. Aşama: Few-Shot (Örneklere dayalı) şablonu oluşturma
    # FewShotPromptTemplate {} karakterlerini şablon değişkeni olarak yorumlar,
    # bu yüzden schema ve geçmişdeki süslü parantezleri escape etmek gerekir.
    schema_escaped = CACHED_SCHEMA.replace('{', '{{').replace('}', '}}')
    gecmis_escaped = (gecmis or 'Yok').replace('{', '{{').replace('}', '}}')
    few_shot = _FewShotPromptTemplate(
        example_selector=example_selector, example_prompt=example_prompt,
        prefix=f'Sen bir SQLite veritabanı uzmanısın.\nŞema:\n{schema_escaped}\n'
               f'Önceki konuşma: {gecmis_escaped}\n'
               f'KURALLAR:\n'
               f'1. SADECE geçerli bir SQLite SQL sorgusu döndür. Açıklama yazma.\n'
               f'2. LIKE kullan (ILIKE kullanma).\n'
               f'3. Tek SELECT cümlesi olsun.\n'
               f'4. Önceki konuşma geçmişini (bağlamı) SADECE yeni soru önceki konuşulan bir konuya, derse veya kişiye açıkça atıfta bulunuyorsa (örneğin "bu ders", "onun notları", "o hoca", "aynı bölüm", "başarı durumu nedir" vb.) kullan. Eğer yeni soru genel veya bağımsız bir soruysa (örneğin tüm dersleri listelemek gibi genel bir soru), önceki konuşmadaki filtreleri (örneğin belirli bir ders adını veya kişi adını) yeni soruya ASLA dahil etme.\n'
               f'Örnekler:',
        suffix='\nSoru: {soru}\nSQL: ', input_variables=['soru']
    )
    
    # 2. Aşama: SQL sorgusunun LLM tarafından üretilmesi
    ham = extract_text(llm_invoke_tracked(llm, few_shot.format(soru=soru)))
    sql = sql_temizle(ham)
    
    # 3. Aşama: Sorguyu çalıştırma ve hata durumunda otomatik düzeltme (Self-Correction)
    try:
        return sql, db.run(sql)
    except Exception as e:
        # Hata durumunda LLM'e hatayı ve şemayı tekrar gösterip düzeltilmiş SQL istenir
        fix_sql = sql_temizle(extract_text(llm_invoke_tracked(llm,
            f'Hatalı SQL: {sql}\nHata: {e}\nŞema: {CACHED_SCHEMA}\nSADECE düzeltilmiş SQL döndür.'
        )))
        return fix_sql, db.run(fix_sql)


def db_sonuc_formatla(soru: str, sonuc: str) -> str:
    if not sonuc or str(sonuc).strip() in ('[]', 'None', '', '[()]'):
        return 'Aradığınız kriterlere uygun kayıt bulunamadı.'
    try:
        rows = ast.literal_eval(str(sonuc))
    except:
        return f'Sonuç: {sonuc}'
    if not rows: return 'Kayıt bulunamadı.'
    s = soru.lower()
    if len(rows) == 1 and isinstance(rows[0], tuple) and len(rows[0]) == 1:
        v = rows[0][0]
        if isinstance(v, float): v = round(v, 2)
        if 'ortalama' in s: return f'Ortalama not: **{v}**'
        if 'en yüksek' in s: return f'En yüksek not: **{v}**'
        if 'kaç' in s: return f'Toplam **{v}**.'
        return f'Sonuç: **{v}**'
    lines = []
    for r in rows:
        if isinstance(r, tuple):
            vals = [str(round(v, 2)) if isinstance(v, float) else str(v) for v in r if v is not None]
            # 2 string değerden oluşan tuple → isim-soyisim gibi, boşlukla birleştir
            sep = ' ' if len(vals) == 2 and all(not v.replace('.','').isdigit() for v in vals) else ' – '
            lines.append('• ' + sep.join(vals))
        else:
            lines.append(f'• {r}')
    if len(lines) > 50:
        lines = lines[:50]
        lines.append('\n⚠️ İlk 50 kayıt gösteriliyor.')
    return '\n'.join(lines)


# ─── RAG Manager ─────────────────────────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.45
MAX_TOTAL_CHUNKS = 20
FALLBACK_THRESHOLD = 0.1


def _k_per_doc(n_docs: int) -> int:
    return max(1, MAX_TOTAL_CHUNKS // n_docs)


class RagManager:
    def __init__(self, cache_dir='./chroma_db'):
        self.cache_dir = cache_dir
        self.documents = {}
        self.db = None

    @property
    def embeddings(self):
        return embedding_model

    def add_document(self, path: str) -> str:
        doc_name = os.path.basename(path)
        ext = path.rsplit('.', 1)[-1].lower()
        if doc_name in self.documents:
            return doc_name

        if ext == 'pdf':
            loader = _PyPDFLoader(path)
        elif ext in ('xlsx', 'xls'):
            df = _pandas.read_excel(path)
            tmp = path + '.txt'
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(df.to_string())
            loader = _TextLoader(tmp, encoding='utf-8')
        elif ext == 'txt':
            loader = _TextLoader(path, encoding='utf-8')
        else:
            raise ValueError(f'Desteklenmeyen dosya türü: {ext}')

        docs = loader.load()
        splits = _RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(docs)

        safe = doc_name.replace('.', '_').replace(' ', '_')
        doc_persist_dir = os.path.join(self.cache_dir, safe)
        vs = _Chroma.from_documents(splits, self.embeddings, persist_directory=doc_persist_dir)
        self.documents[doc_name] = {'vector_store': vs}
        return doc_name

    def remove_document(self, doc_name: str):
        if doc_name in self.documents:
            del self.documents[doc_name]
            safe = doc_name.replace('.', '_').replace(' ', '_')
            doc_persist_dir = os.path.join(self.cache_dir, safe)
            try:
                if os.path.exists(doc_persist_dir):
                    shutil.rmtree(doc_persist_dir)
            except:
                pass

    def list_documents(self):
        return list(self.documents.keys())

    def ask_all(self, question: str, llm=None):
        llm = llm or llm_default
        if not self.documents:
            return None

        n_docs = len(self.documents)
        k = _k_per_doc(n_docs)

        def _fetch(threshold, k_val):
            results = []
            for doc_name, doc_data in self.documents.items():
                retriever = doc_data['vector_store'].as_retriever(
                    search_type='similarity_score_threshold',
                    search_kwargs={'score_threshold': threshold, 'k': k_val}
                )
                try:
                    docs = retriever.invoke(question)
                    for d in docs:
                        d.metadata.setdefault('source', doc_name)
                    results.extend(docs)
                except:
                    pass
            return results

        all_docs = _fetch(SIMILARITY_THRESHOLD, k)
        if not all_docs:
            all_docs = _fetch(FALLBACK_THRESHOLD, 2)
        if not all_docs:
            return None

        sorted_docs = all_docs[:MAX_TOTAL_CHUNKS]
        source_counts = {}
        for d in sorted_docs:
            src = d.metadata.get('source', 'Bilinmeyen')
            source_counts[src] = source_counts.get(src, 0) + 1

        context_parts = [
            f'--- [KAYNAK: {d.metadata.get("source", "Belge")}] ---\n{d.page_content}'
            for d in sorted_docs
        ]
        context = '\n\n'.join(context_parts)

        system_msg = (
            'Sen yardımcı bir belge analiz asistanısın. YÜKLENEN BELGELERİ kullanarak soruları yanıtla. '
            'Eğer kullanıcı belgelerdeki bilgilere dayanarak bir analiz, puanlama, değerlendirme veya karşılaştırma '
            'yapmanı isterse (örneğin "sen puanla", "puanla" gibi), bunu belgedeki nitel verilere göre kendi '
            'oluşturacağın mantıklı kriterlerle/puanlama ölçeğiyle yap ve detaylandır. '
            'Eğer belgede ilgili hiçbir bilgi yoksa bunu belirt.'
        )
        cevap = extract_text(llm_invoke_tracked(llm, [
            ('system', system_msg),
            ('human', f'Belgeler:\n{context}\n\nSoru: {question}')
        ]))
        kaynak = list(source_counts.keys())[0] if len(source_counts) == 1 else f'{len(source_counts)} belge'
        return cevap, kaynak


# ─── Global konuşma yönetimi ──────────────────────────────────────────────────

conversations = {}
active_conv_id = None
conv_counter = 0


def _new_conv(isim=None):
    global conv_counter, active_conv_id
    conv_counter += 1
    cid = str(conv_counter)
    conversations[cid] = {
        'name': isim or f'Sohbet {conv_counter}',
        'history': [],
        'tokens': 0,
        'cost': 0.0,
    }
    active_conv_id = cid
    return cid


_new_conv()


def chat_yanit_uret(soru: str, conv_id: str, model_name: str = 'chatgpt', karsilastir: bool = False):
    """
    Kullanıcı sorusuna yanıt üretme akışını koordine eden ana fonksiyon.
    Sırasıyla: Niyet Sınıflandırma -> (DB veya Meta Sorgusu) -> (RAG Belge Analizi) -> (İnternet Araması / Genel Sohbet)
    aşamalarını işletir, token ve maliyet bilgilerini hesaplar.
    """
    global global_tokens, global_cost_usd
    ensure_imports()

    if conv_id not in conversations:
        return {'error': 'Geçersiz sohbet ID'}

    conv = conversations[conv_id]
    # LLM'e bağlam olarak gönderilmek üzere sohbet geçmişinin son 5 turu birleştirilir
    gecmis = '\n'.join(
        f"Kullanıcı: {h['user']}\nBot: {h['cevap']}"
        for h in conv['history'][-5:]
    )

    llm = _get_llm(model_name)
    
    # 1. Adım: Soruyu konuşma geçmişiyle bağlamlaştır (Query Condensation)
    soru_baglamli = soruyu_baglamla_guncelle(soru, gecmis, llm)
    
    # Sınıflandırma ve yönlendirmeleri bağlamlaştırılmış soruya göre yapıyoruz
    niyet = niyet_siniflandir(soru_baglamli, llm, gecmis)
    cevap = None
    kaynak = 'Bilinmeyen'

    # Tur başına token ve maliyet takibi için işlem öncesi sayaçlar tutulur
    tokens_before = global_tokens
    cost_before = global_cost_usd

    try:
        # Adım 1: Öncelikli Niyetlerin Çözülmesi (DB_QUERY, RAG veya META)
        if niyet == 'DB_QUERY':
            if not db:
                cevap = 'Veritabanı bağlantısı yok.'
                kaynak = 'Hata'
            else:
                try:
                    sql, raw = sql_uret_ve_calistir(soru_baglamli, gecmis, llm)
                    cevap = db_sonuc_formatla(soru_baglamli, raw)
                    kaynak = 'Veritabanı'
                except Exception as e:
                    cevap = f'Bu soruyu işleyemedim: {e}'
                    kaynak = 'Hata'
        elif niyet == 'RAG':
            # Doğrudan belge analizi — DB sorgusu atlanır
            if rag_manager and rag_manager.documents:
                result = rag_manager.ask_all(soru_baglamli, llm)
                if result:
                    cevap, kaynak = result
            if cevap is None:
                cevap = 'Yüklü belgelerde bu soruya yanıt bulunamadı.'
                kaynak = 'Belgeler'
        elif niyet == 'META':
            docs = rag_manager.list_documents() if rag_manager else []
            cevap = extract_text(llm_invoke_tracked(llm, [
                ('system', 'Sen bir sistem asistanısın. Türkçe cevap ver.'),
                ('human', f'Senin adın Akademik Chatbot. Model: {model_name}. Yüklü belgeler: {docs or "Yok"}. Soru: {soru_baglamli}')
            ]))
            kaynak = 'Sistem'

        # Adım 2: DB/META yanıt verdiyse RAG'ı atla; RAG zaten niyet olarak ele alındı.
        # SEARCH niyetinde RAG atlanır — internet araması yapılacak.
        if cevap is None and niyet not in ('RAG', 'DB_QUERY', 'META', 'SEARCH') and rag_manager and rag_manager.documents:
            result = rag_manager.ask_all(soru_baglamli, llm)
            if result:
                cevap, kaynak = result
                red_kelimeleri = ['yeterli bilgi bulunmamaktadır', 'kapsamamaktadır',
                                  'bilgi içermiyor', 'bilgi yok', 'bilgi bulunmuyor',
                                  'bilgi bulunmamaktadır', 'ulaşılamamaktadır']
                if any(k in cevap.lower() for k in red_kelimeleri):
                    cevap = None

        # Adım 3: Hala yanıt üretilemediyse, niyet SEARCH ise internete sorulur, değilse Genel Yapay Zeka cevabı verilir
        if cevap is None:
            if niyet == 'SEARCH':
                cevap = internet_arama_yap(soru_baglamli, llm)
                kaynak = 'İnternet'
            else:
                cevap = genel_cevap_uret(soru_baglamli, gecmis, llm)
                kaynak = 'Sohbet'

    except Exception as e:
        import traceback; traceback.print_exc()
        cevap = f'Hata oluştu: {e}'
        kaynak = 'Sistem'

    # RAG Karşılaştırma Modu aktifse, RAG'sız (düz LLM) yanıtı üret
    cevap_norag = None
    if karsilastir:
        if niyet in ('GENERAL', 'META'):
            cevap_norag = cevap
        else:
            try:
                # Veritabanı, belge veya web araması gibi ek bilgiler olmadan doğrudan LLM'e soruluyor
                cevap_norag = genel_cevap_uret(soru_baglamli, gecmis, llm)
            except Exception as e:
                cevap_norag = f"RAG'sız yanıt üretilemedi: {e}"

    # Bu tura ait token tüketimi ve harcanan dolar miktarı hesaplanır
    msg_tokens = global_tokens - tokens_before
    msg_cost = global_cost_usd - cost_before

    # Sohbet geçmişine ve sohbetin toplam istatistiklerine kaydedilir
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

    return {
        'cevap': cevap,
        'cevap_norag': cevap_norag,
        'kaynak': kaynak,
        'niyet': niyet,
        'tokens': conv['tokens'],
        'cost': f'${conv["cost"]:.5f}',
        'msg_tokens': msg_tokens,
        'msg_cost': f'${msg_cost:.5f}'
    }


# ─── Web Crawler ──────────────────────────────────────────────────────────────

import urllib.request, urllib.robotparser
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser


class _HTMLTextExtractor(HTMLParser):
    SKIP_TAGS = {'script','style','noscript','head',
                 'nav','footer','aside','form','button','svg','iframe'}
    def __init__(self):
        super().__init__()
        self._stack = []; self._skip = False; self.texts = []
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS: self._stack.append(tag); self._skip = True
    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop(); self._skip = bool(self._stack)
    def handle_data(self, data):
        if not self._skip:
            t = data.strip()
            if t: self.texts.append(t)
    def get_text(self): return ' '.join(self.texts)


def _html_to_text(html):
    p = _HTMLTextExtractor()
    try: p.feed(html)
    except: pass
    return re.sub(r'\s{3,}', '\n\n', p.get_text()).strip()


def _get_links(html, base_url):
    base_netloc = urlparse(base_url).netloc
    links = []
    class LP(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                href = dict(attrs).get('href','')
                if href:
                    abs_url = urljoin(base_url, href)
                    p = urlparse(abs_url)
                    if p.netloc == base_netloc:
                        links.append(p._replace(fragment='').geturl())
    lp = LP()
    try: lp.feed(html)
    except: pass
    return list(set(links))


def website_to_rag(start_url, max_pages=30, delay=0.3, respect_robots=True, status_cb=None):
    ensure_imports()

    def log(m):
        print(f'[CRAWLER] {m}')
        if status_cb: status_cb(m)

    parsed = urlparse(start_url)
    domain = parsed.netloc
    base = f"{parsed.scheme}://{domain}"
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; AcademicBot/1.0)'}

    rp = urllib.robotparser.RobotFileParser()
    if respect_robots:
        try: rp.set_url(f"{base}/robots.txt"); rp.read()
        except: pass

    queue, visited, skipped = [start_url], set(), 0
    texts = []

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited: continue
        if respect_robots and not rp.can_fetch('*', url):
            skipped += 1; continue
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                ct = r.headers.get('Content-Type','')
                if 'text/html' not in ct: skipped += 1; continue
                html = r.read().decode('utf-8', errors='replace')
        except Exception as e:
            log(f'⚠️ {url}: {e}'); skipped += 1; continue

        visited.add(url)
        text = _html_to_text(html)
        if len(text) > 100:
            texts.append(f"\n\n{'='*60}\nKAYNAK: {url}\n{'='*60}\n{text}")

        for lnk in _get_links(html, url):
            if lnk not in visited and lnk not in queue:
                queue.append(lnk)

        log(f'✅ [{len(visited)}/{max_pages}] {url}')
        time.sleep(delay)

    if not texts:
        return {'crawled': 0, 'skipped': skipped, 'doc_name': None}

    combined = f"WEB SİTESİ: {start_url}\nTarih: {time.strftime('%Y-%m-%d %H:%M')}\n" + ''.join(texts)
    slug = re.sub(r'[^a-zA-Z0-9]', '_', domain)[:40]
    os.makedirs('uploads', exist_ok=True)
    path = f'uploads/web_{slug}.txt'

    with open(path, 'w', encoding='utf-8') as f:
        f.write(combined)

    doc_name = rag_manager.add_document(path)
    return {'crawled': len(visited), 'skipped': skipped, 'doc_name': doc_name}


# ─── Flask Route'ları ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/init', methods=['POST'])
def api_init():
    try:
        ensure_imports()
        return jsonify({'ok': True, 'message': 'Sistem hazır!'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    soru = data.get('message', '').strip()
    conv_id = data.get('conv_id', active_conv_id)
    model = data.get('model', 'chatgpt')
    karsilastir = data.get('karsilastir', False)

    if not soru:
        return jsonify({'error': 'Mesaj boş olamaz'}), 400

    result = chat_yanit_uret(soru, conv_id, model, karsilastir)
    return jsonify(result)


@app.route('/api/conversations', methods=['GET'])
def api_conversations():
    return jsonify({
        'conversations': [
            {'id': cid, 'name': c['name'], 'tokens': c['tokens'], 'cost': f"${c['cost']:.5f}"}
            for cid, c in conversations.items()
        ],
        'active': active_conv_id
    })


@app.route('/api/conversations/new', methods=['POST'])
def api_new_conv():
    cid = _new_conv()
    return jsonify({'id': cid, 'name': conversations[cid]['name']})


@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
def api_delete_conv(conv_id):
    global active_conv_id
    if conv_id in conversations:
        del conversations[conv_id]
    if conversations:
        active_conv_id = list(conversations.keys())[-1]
    else:
        _new_conv()
    return jsonify({'ok': True, 'active': active_conv_id})


@app.route('/api/conversations/<conv_id>/switch', methods=['POST'])
def api_switch_conv(conv_id):
    global active_conv_id
    if conv_id not in conversations:
        return jsonify({'error': 'Geçersiz sohbet'}), 404
    active_conv_id = conv_id
    conv = conversations[conv_id]
    return jsonify({
        'ok': True,
        'history': conv['history'],
        'tokens': conv['tokens'],
        'cost': f"${conv['cost']:.5f}"
    })


@app.route('/api/conversations/<conv_id>/reset', methods=['POST'])
def api_reset_conv(conv_id):
    if conv_id not in conversations:
        return jsonify({'error': 'Geçersiz sohbet'}), 404
    conversations[conv_id]['history'] = []
    conversations[conv_id]['tokens'] = 0
    conversations[conv_id]['cost'] = 0.0
    return jsonify({'ok': True})


@app.route('/api/documents', methods=['GET'])
def api_list_documents():
    ensure_imports()
    return jsonify({'documents': rag_manager.list_documents()})


@app.route('/api/documents/upload', methods=['POST'])
def api_upload():
    ensure_imports()
    if 'files' not in request.files:
        return jsonify({'error': 'Dosya seçilmedi'}), 400

    files = request.files.getlist('files')
    uploaded = []
    errors = []

    for f in files:
        if f.filename == '':
            continue
        filename = secure_filename(f.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        f.save(path)
        try:
            doc_name = rag_manager.add_document(path)
            uploaded.append(doc_name)
        except Exception as e:
            errors.append(f'{filename}: {e}')

    return jsonify({
        'uploaded': uploaded,
        'errors': errors,
        'documents': rag_manager.list_documents()
    })


@app.route('/api/documents/<doc_name>', methods=['DELETE'])
def api_delete_doc(doc_name):
    ensure_imports()
    rag_manager.remove_document(doc_name)
    return jsonify({'ok': True, 'documents': rag_manager.list_documents()})


@app.route('/api/crawl', methods=['POST'])
def api_crawl():
    ensure_imports()
    data = request.json
    url = data.get('url', '').strip()
    max_pages = int(data.get('max_pages', 30))

    if not url or not url.startswith('http'):
        return jsonify({'error': 'Geçerli URL girin'}), 400

    result = website_to_rag(url, max_pages=max_pages)
    if not result['crawled']:
        return jsonify({'error': 'İçerik alınamadı'}), 400

    return jsonify({
        'ok': True,
        'crawled': result['crawled'],
        'doc_name': result['doc_name'],
        'documents': rag_manager.list_documents()
    })


@app.route('/api/stats', methods=['GET'])
def api_stats():
    return jsonify({
        'tokens': global_tokens,
        'cost': f'${global_cost_usd:.5f}',
        'documents': rag_manager.list_documents() if rag_manager else [],
        'conversations': len(conversations)
    })


if __name__ == '__main__':
    print('🚀 Akademik Chatbot başlatılıyor...')
    print('📌 http://localhost:5000 adresinde çalışıyor')
    app.run(debug=True, host='0.0.0.0', port=5000)
