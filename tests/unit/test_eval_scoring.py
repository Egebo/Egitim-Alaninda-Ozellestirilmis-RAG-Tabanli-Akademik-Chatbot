"""eval/run_eval.py icindeki db_query_dogruluk_skoru fonksiyonunun saf mantiginin
testi. API cagrisi yapmaz."""
from eval.run_eval import db_query_dogruluk_skoru


def test_tam_eslesme_1_0_skoru_verir():
    assert db_query_dogruluk_skoru('Cevap: 6', '6') == 1.0


def test_coklu_parca_kismi_eslesme():
    cevap = 'Ali Kaya ve Emre Çelik bulundu'
    ground_truth = 'ali kaya, emre çelik, pınar bulut'
    skor = db_query_dogruluk_skoru(cevap, ground_truth)
    assert round(skor, 2) == round(2 / 3, 2)


def test_hic_eslesme_yoksa_0_doner():
    assert db_query_dogruluk_skoru('alakasiz cevap', '42') == 0.0
