"""yansit() fonksiyonunun native tool-calling (bind_tools/tool_calls) davranisini
dogrular. LLM gercekte cagrilmaz; llm.bind_tools(...).invoke(...) zincirini taklit
eden sahte bir nesne kullanilir (test_orchestrator_tool_calling.py'deki desenle
ayni sekle sahip)."""
from services.reflection import yansit


class _SahteYansimaYaniti:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ''


class _SahteYansimaLLM:
    def __init__(self, tool_calls=None, patlasin=False):
        self._tool_calls = tool_calls or []
        self._patlasin = patlasin

    def bind_tools(self, tools):
        if self._patlasin:
            raise RuntimeError('bind_tools basarisiz')
        return self

    def invoke(self, girdi):
        return _SahteYansimaYaniti(self._tool_calls)


def test_yeterli_cevapta_true_ve_bos_rafine_soru_doner():
    llm = _SahteYansimaLLM([
        {'name': 'YansimaSonucu', 'args': {'yeterli': True, 'rafine_soru': ''}, 'id': 'call_1'}
    ])
    sonuc = yansit('kac ogrenci var', 'Toplam 25 ogrenci var.', 'Veritabani', llm)
    assert sonuc == {'yeterli': True, 'rafine_soru': ''}


def test_yetersiz_cevapta_rafine_soru_doner():
    llm = _SahteYansimaLLM([
        {'name': 'YansimaSonucu', 'args': {'yeterli': False, 'rafine_soru': 'CVdeki is deneyimi kac yil'}, 'id': 'call_1'}
    ])
    sonuc = yansit('deneyim ne', 'Yeterli bilgi bulunmamaktadir.', 'Belgeler', llm)
    assert sonuc == {'yeterli': False, 'rafine_soru': 'CVdeki is deneyimi kac yil'}


def test_tool_calls_bos_ise_fail_open():
    llm = _SahteYansimaLLM([])
    sonuc = yansit('soru', 'cevap', 'Veritabani', llm)
    assert sonuc == {'yeterli': True, 'rafine_soru': ''}


def test_llm_hata_verirse_fail_open():
    llm = _SahteYansimaLLM(patlasin=True)
    sonuc = yansit('soru', 'cevap', 'Veritabani', llm)
    assert sonuc == {'yeterli': True, 'rafine_soru': ''}
