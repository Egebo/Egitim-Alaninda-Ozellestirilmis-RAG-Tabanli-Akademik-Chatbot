"""Testler arasinda paylasilan fixture'lar: state izolasyonu, gecici DB, sahte LLM."""
import pytest

from core.state import state


@pytest.fixture(autouse=True)
def _gercek_api_anahtarlarini_gizle(monkeypatch):
    """Bir test yanlislikla _get_llm'i mock'lamayi unutursa gercek bir API
    cagrisi denemek yerine hemen ValueError ile patlasin diye, her testte
    gercek API anahtarlarini ortamdan gizler."""
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)


@pytest.fixture
def fresh_state():
    """
    core.state.state tek bir singleton nesne oldugu icin (bircok servis modulu
    onu `from core.state import state` ile iceri aktardigindan hepsi ayni
    referansi tutar), objeyi YENIDEN OLUSTURMAK bu referanslari guncellemez.
    Bunun yerine mevcut ornegin alanlarini bilinen bos degerlere sifirlar,
    testten sonra orijinal degerlerine geri yukleriz.
    """
    onceki = vars(state).copy()

    state.imports_done = True  # ensure_imports() agir yuklemeyi atlasin
    state.embedding_model = None
    state.llm_default = None
    state.db = None
    state.CACHED_SCHEMA = ''
    state.rag_manager = None
    state.search_tool = None
    state.SEARCH_OK = False
    state.example_selector = None
    state.example_prompt = None
    state.global_tokens = 0
    state.global_cost_usd = 0.0
    state.conversations = {}
    state.active_conv_id = None
    state.conv_counter = 0

    yield state

    for anahtar, deger in onceki.items():
        setattr(state, anahtar, deger)


@pytest.fixture
def test_db(tmp_path):
    """_setup_database'i gecici bir SQLite dosyasina kurar, dosya yolunu (str) dondurur."""
    from core.database import _setup_database
    db_yolu = tmp_path / 'test_okul.db'
    _setup_database(str(db_yolu))
    return str(db_yolu)


class _SahteYanit:
    def __init__(self, icerik):
        self.content = icerik


class _SahteLLM:
    """LLM.invoke() arayuzunu taklit eder; sirali cagrilarda onceden verilmis
    cevaplari sirayla dondurur, tukenince bos string doner. Gercek API
    cagrisi yapmadan orkestrasyon testlerinde llm parametresi olarak kullanilir."""
    def __init__(self, cevaplar=None):
        self._cevaplar = list(cevaplar or [])

    def invoke(self, girdi):
        if self._cevaplar:
            return _SahteYanit(self._cevaplar.pop(0))
        return _SahteYanit('')


@pytest.fixture
def sahte_llm():
    return _SahteLLM
