"""fresh_state fixture'inin izolasyonu gercekten sagladigini dogrular:
bir testin yaptigi degisiklik, teardown sonrasi bir sonraki teste sizmamali."""
from core.state import state


def test_fresh_state_degeri_degistirir(fresh_state):
    fresh_state.conv_counter = 42
    assert state.conv_counter == 42


# UYARI: Bu test fresh_state fixture'i ISTEMIYOR cunku fixture'in setup'i
# conv_counter'i 0'a sifirlardi ve teardown kontrolu anlamsiz olurdu. Onceki
# test'in yaptigi 42 degerini raw singleton'dan dogru secebilmek icin fixture
# kullanmiyoruz. Bunun basarili olmasi, bu test'in dosya-tanimi sirasinda
# onceki test'ten hemen sonra calistigini varsayar (pytest varsayilani).
# Rasgelelestirme eklenmis olsaydi, bu test otomatik olarak kirilir.
def test_fresh_state_teardown_sonrasi_sizinti_olmaz():
    # Bir onceki testin fresh_state fixture'i artik teardown olmus olmali;
    # conv_counter, o testin icinde biraktigi 42 degerinde KALMAMALI.
    assert state.conv_counter != 42
