"""sonuclari_birlestir ve internet_arama_yap prompt'larinin halusinasyon
onleme talimatlarini icerdigini dogrular. Gercek LLM cagrisi yapilmaz,
llm_invoke_tracked mock'lanir, sadece gonderilen prompt metni kontrol edilir."""
from services.orchestrator import sonuclari_birlestir, internet_arama_yap


def test_sonuclari_birlestir_uydurma_yapma_talimati_icerir(mocker):
    mock_invoke = mocker.patch('services.orchestrator.llm_invoke_tracked', return_value='cevap')
    mocker.patch('services.orchestrator.extract_text', return_value='cevap')
    sonuclar = [{'kaynak': 'Veritabanı', 'soru': 'soru1', 'cevap': 'kayıt bulunamadı'}]

    sonuclari_birlestir('soru', sonuclar, llm=object())

    prompt = mock_invoke.call_args[0][1]
    assert 'uydurma baglantilar' in prompt.lower()


def test_internet_arama_yap_ilgisiz_sonuc_talimati_icerir(mocker, fresh_state):
    fresh_state.SEARCH_OK = True
    fresh_state.search_tool = mocker.Mock(run=mocker.Mock(return_value='arama sonucu metni'))
    mock_invoke = mocker.patch('services.orchestrator.llm_invoke_tracked', return_value='cevap')
    mocker.patch('services.orchestrator.extract_text', return_value='cevap')

    internet_arama_yap('soru', llm=object())

    prompt = mock_invoke.call_args[0][1]
    assert 'ilgisiz sonuçlardan emin bir cevap uydurma' in prompt.lower()
