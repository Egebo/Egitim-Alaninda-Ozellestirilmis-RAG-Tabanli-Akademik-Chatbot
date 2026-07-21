"""eval/golden_set.json dosyasinin yapisal butunlugunu dogrular. API cagrisi
yapmaz, sadece JSON semasini kontrol eder (run_eval.py'nin kullandigi veri
kaynagi)."""
import json
from pathlib import Path

GOLDEN_SET_YOLU = Path(__file__).resolve().parents[2] / 'eval' / 'golden_set.json'
GECERLI_KATEGORILER = {'DB_QUERY', 'RAG', 'GENERAL', 'META', 'SEARCH'}


def _golden_set_yukle():
    with open(GOLDEN_SET_YOLU, encoding='utf-8') as f:
        return json.load(f)


def test_golden_set_dosyasi_gecerli_json_listesidir():
    veri = _golden_set_yukle()
    assert isinstance(veri, list)
    assert len(veri) > 0


def test_her_kayit_zorunlu_alanlari_icerir():
    veri = _golden_set_yukle()
    for kayit in veri:
        assert 'id' in kayit and kayit['id']
        assert 'category' in kayit
        assert 'soru' in kayit and kayit['soru']
        assert 'ground_truth' in kayit


def test_kategoriler_gecerli_degerlerden_biridir():
    veri = _golden_set_yukle()
    for kayit in veri:
        assert kayit['category'] in GECERLI_KATEGORILER


def test_id_alanlari_essizdir():
    veri = _golden_set_yukle()
    idler = [kayit['id'] for kayit in veri]
    assert len(idler) == len(set(idler))


def test_db_query_ve_rag_kayitlarinin_ground_truth_u_bos_olamaz():
    veri = _golden_set_yukle()
    for kayit in veri:
        if kayit['category'] in ('DB_QUERY', 'RAG'):
            assert kayit['ground_truth'], f"{kayit['id']} icin ground_truth bos olamaz"


def test_rag_kayitlarinin_kaynak_dosyasi_belirtilmis_olmalidir():
    veri = _golden_set_yukle()
    for kayit in veri:
        if kayit['category'] == 'RAG':
            assert kayit.get('kaynak_dosya'), f"{kayit['id']} icin kaynak_dosya belirtilmeli"
