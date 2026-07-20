"""Ağır ML/LangChain kütüphanelerinin gecikmeli (lazy) yüklenmesi."""
import os
import sqlite3

from core.state import state
from core.database import _setup_database
from core.llm import _get_llm
from services.rag import RagManager


def ensure_imports():
    """
    LangChain, Chroma, HuggingFace ve model kütüphanelerini belleğe yükler.
    Eğer veritabanı mevcut değilse otomatik olarak demo verileriyle oluşturur.
    Ayrıca Few-Shot SQL örnek seçicisini ve embedding modelini hazırlar.
    """
    if state.imports_done:
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
    if os.path.exists(db_filename):
        try:
            conn = sqlite3.connect(db_filename)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projeler'")
            if not cur.fetchone():
                recreate = True
            conn.close()
        except:
            recreate = True

    if recreate and os.path.exists(db_filename):
        try:
            os.remove(db_filename)
            print('♻️ Eski veritabanı şeması silindi, yeniden kurulacak.')
        except Exception as e:
            print(f'♻️ Eski veritabanı silinemedi: {e}')

    if not os.path.exists(db_filename):
        _setup_database(db_filename)

    try:
        state.db = SQLDatabase.from_uri(f'sqlite:///{db_filename}')
        state.CACHED_SCHEMA = state.db.get_table_info()
        print('✅ Veritabanı bağlantısı OK')
    except Exception as e:
        print(f'DB Hata: {e}')
        state.db = None
        state.CACHED_SCHEMA = ''

    # ── Embedding Model ve Few-Shot Örnek Seçici Kurulumu ────────────────────
    print('⚙️ Embedding modeli yükleniyor...')
    state.embedding_model = HuggingFaceEmbeddings(model_name='intfloat/multilingual-e5-small')

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

    example_prompt_obj = PromptTemplate(
        input_variables=['soru', 'sql'],
        template='Soru: {soru}\nSQL: {sql}'
    )
    state.example_selector = SemanticSimilarityExampleSelector.from_examples(
        ornekler, state.embedding_model, Chroma, k=3
    )
    state.example_prompt = example_prompt_obj

    # ── Varsayılan Büyük Dil Modeli (LLM) Yapılandırması ──────────────────────
    openai_ok = bool(os.environ.get('OPENAI_API_KEY'))
    gemini_ok = bool(os.environ.get('GOOGLE_API_KEY'))
    if openai_ok:
        try:
            state.llm_default = _get_llm('chatgpt')
            print('✅ Varsayılan LLM hazır (ChatGPT)!')
        except Exception as e:
            print(f'⚠️ ChatGPT başlatılamadı: {e}')
            state.llm_default = None
    elif gemini_ok:
        try:
            state.llm_default = _get_llm('gemini')
            print('✅ Varsayılan LLM hazır (Gemini)!')
        except Exception as e:
            print(f'⚠️ Gemini başlatılamadı: {e}')
            state.llm_default = None
    else:
        state.llm_default = None
        print('⚠️ Uyarı: OpenAI veya Google API anahtarı bulunamadı. Lütfen .env dosyasını ayarlayın.')

    # ── Belge Analiz Yöneticisi (RAG Manager) Kurulumu ────────────────────────
    state.rag_manager = RagManager()
    state.rag_manager.db = state.db

    # ── İnternet Arama Motoru Entegrasyonu ────────────────────────────────────
    try:
        state.search_tool = DuckDuckGoSearchRun()
        state.SEARCH_OK = True
    except Exception as e:
        print(f'⚠️ DuckDuckGo başlatılamadı: {e}')
        state.SEARCH_OK = False

    state.imports_done = True
    print('✅ Sistem hazır!')
