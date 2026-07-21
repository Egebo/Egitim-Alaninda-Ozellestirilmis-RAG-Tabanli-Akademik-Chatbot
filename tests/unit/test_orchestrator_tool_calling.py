"""gorev_plani_olustur'un native tool-calling (bind_tools/tool_calls) davranisini
dogrular. LLM gercekte cagrilmaz; llm.bind_tools(...).invoke(...) zincirini taklit
eden sahte bir nesne kullanilir (gercek LangChain ChatModel'in dondurdugu
AIMessage.tool_calls formatiyla ayni sekle sahip: {'name':..., 'args': {...},
'id':...} sozlukleri)."""
from services.orchestrator import gorev_plani_olustur


class _SahteAracCagrisiYaniti:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ''


class _SahteAracCagrisiLLM:
    def __init__(self, tool_calls):
        self._tool_calls = tool_calls
        self.son_bind_edilen_araclar = None

    def bind_tools(self, tools):
        self.son_bind_edilen_araclar = tools
        return self

    def invoke(self, girdi):
        return _SahteAracCagrisiYaniti(self._tool_calls)


class _SahteRagManager:
    def __init__(self, belgeler):
        self.documents = belgeler

    def erisilebilir_belgeler(self, conv_id=None):
        return self.documents


def test_tek_arac_cagrisi_tek_adimlik_plana_donusur(fresh_state):
    fresh_state.rag_manager = _SahteRagManager({'ozgecmis.pdf': {}})
    llm = _SahteAracCagrisiLLM([
        {'name': 'RAG', 'args': {'soru': 'ikinci sayfada ne anlatiliyor'}, 'id': 'call_1'}
    ])
    plan = gorev_plani_olustur('ikinci sayfada ne anlatiliyor', llm, '')
    assert plan == [{'tool': 'RAG', 'soru': 'ikinci sayfada ne anlatiliyor'}]


def test_coklu_arac_cagrisi_coklu_adim_plana_donusur(fresh_state):
    fresh_state.rag_manager = _SahteRagManager({'ozgecmis.pdf': {}})
    llm = _SahteAracCagrisiLLM([
        {'name': 'DB_QUERY', 'args': {'soru': 'ortalama not kac'}, 'id': 'call_1'},
        {'name': 'RAG', 'args': {'soru': 'belgede proje ornegi var mi'}, 'id': 'call_2'},
    ])
    plan = gorev_plani_olustur('Bahsettigim konudaki detaylari ve karsilastirmayi ozetler misin?', llm, '')
    assert plan == [
        {'tool': 'DB_QUERY', 'soru': 'ortalama not kac'},
        {'tool': 'RAG', 'soru': 'belgede proje ornegi var mi'},
    ]


def test_tool_calls_bos_ise_general_a_dusulur(fresh_state):
    fresh_state.rag_manager = None
    llm = _SahteAracCagrisiLLM([])
    plan = gorev_plani_olustur('bugun canim sikkin', llm, '')
    assert plan == [{'tool': 'GENERAL', 'soru': 'bugun canim sikkin'}]


def test_belge_yokken_rag_araci_modele_sunulmaz(fresh_state):
    fresh_state.rag_manager = None
    llm = _SahteAracCagrisiLLM([{'name': 'GENERAL', 'args': {'soru': 'selam'}, 'id': 'call_1'}])
    gorev_plani_olustur('bugun canim sikkin', llm, '')
    sunulan_isimler = [arac.__name__ for arac in llm.son_bind_edilen_araclar]
    assert 'RAG' not in sunulan_isimler


def test_gecersiz_arac_ismi_filtrelenir(fresh_state):
    fresh_state.rag_manager = None
    llm = _SahteAracCagrisiLLM([
        {'name': 'UYDURMA_ARAC', 'args': {'soru': 'x'}, 'id': 'call_1'},
        {'name': 'GENERAL', 'args': {'soru': 'gecerli soru'}, 'id': 'call_2'},
    ])
    plan = gorev_plani_olustur('bugun canim sikkin', llm, '')
    assert plan == [{'tool': 'GENERAL', 'soru': 'gecerli soru'}]
