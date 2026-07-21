from core import conversation_store
from core import document_store as belge_deposu
from services.orchestrator import niyet_kurala_gore
from services.rag import RagManager


class _SahteRagManager:
    def __init__(self, belgeler):
        self.documents = belgeler

    def erisilebilir_belgeler(self, conv_id=None):
        return self.documents


def test_selamlama_general_doner(fresh_state):
    assert niyet_kurala_gore("selam nasılsın") == 'GENERAL'


def test_meta_soru_dogru_yakalanir(fresh_state):
    assert niyet_kurala_gore("hangi modeli kullanıyorsun") == 'META'


def test_db_keyword_dogru_yakalanir(fresh_state):
    assert niyet_kurala_gore("Ahmet hocanın dersleri neler") == 'DB_QUERY'


def test_belge_yokken_rag_keyword_eslesmez(fresh_state):
    fresh_state.rag_manager = None
    assert niyet_kurala_gore("bu CV'de neler var") is None


def test_rag_keyword_belge_yukluyken_rag_doner(fresh_state):
    fresh_state.rag_manager = _SahteRagManager({'ozgecmis.pdf': {}})
    assert niyet_kurala_gore("bu CV'de neler var") == 'RAG'


def test_belge_adi_db_keywordu_ile_carpisirsa_fast_path_atlanir(fresh_state):
    # Regresyon testi: "CV_-_Egemen_Bozca.pdf" yukluyken "Egemen Bozca hoca mi"
    # gibi bir soru, "hoca" DB anahtar kelimesine ragmen None donmeli
    # (LLM'in cok adimli plan kurmasina izin verilmeli), aksi halde DB_QUERY'e
    # yanlislikla yonlendirilirdi.
    fresh_state.rag_manager = _SahteRagManager({'CV_-_Egemen_Bozca.pdf': {}})
    assert niyet_kurala_gore("Egemen Bozca hoca mı yoksa öğrenci mi?") is None


def test_ilgisiz_db_keywordu_belge_yukluyken_de_calisir(fresh_state):
    # Belge adiyla hicbir tokeni eslesmeyen bir DB sorusu normal calismaya devam etmeli.
    fresh_state.rag_manager = _SahteRagManager({'CV_-_Egemen_Bozca.pdf': {}})
    assert niyet_kurala_gore("Fatma Çelik hocanın dersleri neler") == 'DB_QUERY'


def test_ozel_belgeye_baska_sohbet_rag_yolundan_erisemez(fresh_state):
    """Gercek RagManager + document_store ile uctan uca: bir belge '1' numarali
    sohbete ozelse, '2' numarali sohbet onu RAG hizli-yolundan goremez."""
    conversation_store.sohbet_ekle('1', 'Sohbet 1')
    belge_deposu.kapsam_kaydet('gizli_cv.pdf', 'ozel', sohbet_id='1')

    rm = RagManager()
    rm.documents = {'gizli_cv.pdf': {'vector_store': object()}}
    fresh_state.rag_manager = rm

    assert niyet_kurala_gore("bu cv de ne var", conv_id='1') == 'RAG'
    assert niyet_kurala_gore("bu cv de ne var", conv_id='2') is None
