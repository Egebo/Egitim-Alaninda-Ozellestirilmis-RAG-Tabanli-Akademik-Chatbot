"""RagManager.retrieve()'in ask_all'dan bagimsiz calisabildigini ve threshold
fallback davranisini korudugunu dogrular. Gercek Chroma/embedding kullanilmaz,
vector_store sahte bir nesneyle taklit edilir."""
from core import conversation_store
from core import document_store as belge_deposu
from services.rag import RagManager


class _SahteDocument:
    def __init__(self, icerik, kaynak=None):
        self.page_content = icerik
        self.metadata = {'source': kaynak} if kaynak else {}


class _SahteRetriever:
    def __init__(self, sonuclar):
        self._sonuclar = sonuclar

    def invoke(self, soru):
        return self._sonuclar


class _SahteVectorStore:
    def __init__(self, sonuclar):
        self._sonuclar = sonuclar
        self.son_search_kwargs = None

    def as_retriever(self, search_type, search_kwargs):
        self.son_search_kwargs = search_kwargs
        return _SahteRetriever(self._sonuclar)


def test_belge_yokken_none_doner():
    rm = RagManager()
    assert rm.retrieve('herhangi bir soru') is None


def test_esik_ustunde_sonuc_varsa_direkt_doner():
    rm = RagManager()
    sonuclar = [_SahteDocument('icerik 1'), _SahteDocument('icerik 2')]
    vs = _SahteVectorStore(sonuclar)
    rm.documents = {'belge.txt': {'vector_store': vs}}

    sonuc = rm.retrieve('soru')

    assert len(sonuc) == 2
    assert vs.son_search_kwargs['score_threshold'] == 0.45


def test_esik_ustunde_sonuc_yoksa_fallback_esigine_duser():
    class _KademeliVectorStore:
        def __init__(self):
            self.cagri_sayisi = 0
            self.son_search_kwargs = None

        def as_retriever(self, search_type, search_kwargs):
            self.son_search_kwargs = search_kwargs
            self.cagri_sayisi += 1
            sonuc = [] if self.cagri_sayisi == 1 else [_SahteDocument('fallback icerik')]
            return _SahteRetriever(sonuc)

    rm = RagManager()
    vs = _KademeliVectorStore()
    rm.documents = {'belge.txt': {'vector_store': vs}}

    sonuc = rm.retrieve('soru')

    assert len(sonuc) == 1
    assert sonuc[0].page_content == 'fallback icerik'
    assert vs.son_search_kwargs['score_threshold'] == 0.1


def test_source_metadata_doc_name_ile_doldurulur():
    rm = RagManager()
    vs = _SahteVectorStore([_SahteDocument('icerik')])
    rm.documents = {'ozel_belge.pdf': {'vector_store': vs}}

    sonuc = rm.retrieve('soru')

    assert sonuc[0].metadata['source'] == 'ozel_belge.pdf'


def test_conv_id_verilmezse_izlenmeyen_belgeler_de_taranir():
    rm = RagManager()
    vs = _SahteVectorStore([_SahteDocument('icerik')])
    rm.documents = {'izlenmeyen.pdf': {'vector_store': vs}}

    assert rm.retrieve('soru', conv_id=None) is not None


def test_ozel_belge_baska_sohbetten_gorulmez():
    conversation_store.sohbet_ekle('1', 'Sohbet 1')
    belge_deposu.kapsam_kaydet('gizli_cv.pdf', 'ozel', sohbet_id='1')

    rm = RagManager()
    rm.documents = {'gizli_cv.pdf': {'vector_store': _SahteVectorStore([_SahteDocument('icerik')])}}

    assert rm.retrieve('soru', conv_id='1') is not None
    assert rm.retrieve('soru', conv_id='2') is None


def test_global_belge_her_sohbetten_gorulur():
    belge_deposu.kapsam_kaydet('el_kitabi.pdf', 'global')

    rm = RagManager()
    rm.documents = {'el_kitabi.pdf': {'vector_store': _SahteVectorStore([_SahteDocument('icerik')])}}

    assert rm.retrieve('soru', conv_id='1') is not None
    assert rm.retrieve('soru', conv_id='2') is not None


def test_erisilebilir_belgeler_karma_kapsamlari_dogru_filtreler():
    conversation_store.sohbet_ekle('1', 'Sohbet 1')
    belge_deposu.kapsam_kaydet('ozel_a.pdf', 'ozel', sohbet_id='1')
    belge_deposu.kapsam_kaydet('global_b.pdf', 'global')
    # 'izlenmeyen_c.pdf' hicbir kapsam kaydina sahip degil -> global sayilir

    rm = RagManager()
    rm.documents = {
        'ozel_a.pdf': {'vector_store': None},
        'global_b.pdf': {'vector_store': None},
        'izlenmeyen_c.pdf': {'vector_store': None},
    }

    assert set(rm.erisilebilir_belgeler(conv_id='1').keys()) == {'ozel_a.pdf', 'global_b.pdf', 'izlenmeyen_c.pdf'}
    assert set(rm.erisilebilir_belgeler(conv_id='2').keys()) == {'global_b.pdf', 'izlenmeyen_c.pdf'}
