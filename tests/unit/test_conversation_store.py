"""core/conversation_store.py'nin SQLite kalicilik katmanini dogrular. Gercek
dosya sistemine yazar ama conftest.py'deki autouse `_gercek_conversations_db_gizle`
fixture'i DB_YOLU'nu her testte gecici bir dosyaya yonlendirir, gercek
conversations.db'ye asla dokunulmaz."""
from core import conversation_store as depo


def test_hepsini_yukle_bos_ise_bos_dict_doner():
    assert depo.hepsini_yukle() == {}


def test_sohbet_ekle_ve_yukle():
    depo.sohbet_ekle('1', 'Sohbet 1')

    yuklenen = depo.hepsini_yukle()

    assert yuklenen == {'1': {'name': 'Sohbet 1', 'tokens': 0, 'cost': 0.0, 'history': []}}


def test_ayni_id_ile_ikinci_ekleme_yoksayilir():
    depo.sohbet_ekle('1', 'Sohbet 1')
    depo.sohbet_ekle('1', 'Farkli Isim')

    yuklenen = depo.hepsini_yukle()

    assert yuklenen['1']['name'] == 'Sohbet 1'


def test_mesaj_ekle_gecmisi_ve_toplamlari_gunceller():
    depo.sohbet_ekle('1', 'Sohbet 1')
    mesaj = {'user': 'selam', 'cevap': 'merhaba', 'cevap_norag': None,
              'kaynak': 'Sohbet', 'tokens': 42, 'cost': 0.001, 'niyet': 'GENERAL'}

    depo.mesaj_ekle('1', mesaj, sira=1, toplam_tokens=42, toplam_cost=0.001)

    yuklenen = depo.hepsini_yukle()
    assert yuklenen['1']['tokens'] == 42
    assert yuklenen['1']['cost'] == 0.001
    assert yuklenen['1']['history'] == [mesaj]


def test_mesajlar_sira_ile_dogru_siralanir():
    depo.sohbet_ekle('1', 'Sohbet 1')
    depo.mesaj_ekle('1', {'user': 'ilk', 'cevap': 'c1', 'cevap_norag': None,
                           'kaynak': 'Sohbet', 'tokens': 1, 'cost': 0.0, 'niyet': 'GENERAL'}, 1, 1, 0.0)
    depo.mesaj_ekle('1', {'user': 'ikinci', 'cevap': 'c2', 'cevap_norag': None,
                           'kaynak': 'Sohbet', 'tokens': 2, 'cost': 0.0, 'niyet': 'GENERAL'}, 2, 3, 0.0)

    yuklenen = depo.hepsini_yukle()

    assert [m['user'] for m in yuklenen['1']['history']] == ['ilk', 'ikinci']


def test_sohbet_ismini_guncelle():
    depo.sohbet_ekle('1', 'Sohbet 1')

    depo.sohbet_ismini_guncelle('1', 'Öğrenci sayısı sorgusu')

    assert depo.hepsini_yukle()['1']['name'] == 'Öğrenci sayısı sorgusu'


def test_sohbet_sil_mesajlari_da_siler():
    depo.sohbet_ekle('1', 'Sohbet 1')
    depo.mesaj_ekle('1', {'user': 'selam', 'cevap': 'merhaba', 'cevap_norag': None,
                           'kaynak': 'Sohbet', 'tokens': 1, 'cost': 0.0, 'niyet': 'GENERAL'}, 1, 1, 0.0)

    depo.sohbet_sil('1')

    assert depo.hepsini_yukle() == {}


def test_sohbet_sifirla_mesajlari_siler_toplamlari_sifirlar():
    depo.sohbet_ekle('1', 'Sohbet 1')
    depo.mesaj_ekle('1', {'user': 'selam', 'cevap': 'merhaba', 'cevap_norag': None,
                           'kaynak': 'Sohbet', 'tokens': 5, 'cost': 0.002, 'niyet': 'GENERAL'}, 1, 5, 0.002)

    depo.sohbet_sifirla('1')

    yuklenen = depo.hepsini_yukle()
    assert yuklenen['1']['history'] == []
    assert yuklenen['1']['tokens'] == 0
    assert yuklenen['1']['cost'] == 0.0
