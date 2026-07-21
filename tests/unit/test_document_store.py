"""core/document_store.py'nin belge kapsam (ozel/global) kalicilik katmanini
dogrular. conftest.py'deki autouse fixture conversation_store.DB_YOLU'nu (ve
dolayisiyla document_store'un kullandigi ayni dosyayi) her testte gecici bir
yola yonlendirir. `belgeler.sohbet_id` sohbetler(id)'e FK referansi verdigi
icin 'ozel' kapsamli testler once gercek bir sohbet kaydi olusturur."""
import pytest

from core import conversation_store
from core import document_store as belge_deposu


def test_izlenmeyen_belge_erisilebilir_sayilir():
    assert belge_deposu.belge_erisilebilir_mi('hic_kaydedilmemis.pdf', 'herhangi-bir-sohbet') is True


def test_global_belge_her_sohbete_erisilebilir():
    belge_deposu.kapsam_kaydet('sirket_el_kitabi.pdf', 'global')
    assert belge_deposu.belge_erisilebilir_mi('sirket_el_kitabi.pdf', '1') is True
    assert belge_deposu.belge_erisilebilir_mi('sirket_el_kitabi.pdf', '2') is True


def test_ozel_belge_sadece_sahibi_sohbete_erisilebilir():
    conversation_store.sohbet_ekle('1', 'Sohbet 1')
    belge_deposu.kapsam_kaydet('cv.pdf', 'ozel', sohbet_id='1')
    assert belge_deposu.belge_erisilebilir_mi('cv.pdf', '1') is True
    assert belge_deposu.belge_erisilebilir_mi('cv.pdf', '2') is False


def test_ozel_kapsam_sohbet_id_olmadan_hata_verir():
    with pytest.raises(ValueError):
        belge_deposu.kapsam_kaydet('cv.pdf', 'ozel')


def test_gecersiz_kapsam_hata_verir():
    with pytest.raises(ValueError):
        belge_deposu.kapsam_kaydet('cv.pdf', 'yanlis-deger')


def test_ayni_belge_yeniden_kaydedilirse_kapsam_guncellenir():
    conversation_store.sohbet_ekle('1', 'Sohbet 1')
    belge_deposu.kapsam_kaydet('rapor.pdf', 'ozel', sohbet_id='1')
    belge_deposu.kapsam_kaydet('rapor.pdf', 'global')

    assert belge_deposu.belge_erisilebilir_mi('rapor.pdf', '2') is True
    assert belge_deposu.kapsam_getir('rapor.pdf') == {'kapsam': 'global', 'sohbet_id': None}


def test_tum_kapsamlari_listele():
    conversation_store.sohbet_ekle('1', 'Sohbet 1')
    belge_deposu.kapsam_kaydet('a.pdf', 'ozel', sohbet_id='1')
    belge_deposu.kapsam_kaydet('b.pdf', 'global')

    kayitlar = belge_deposu.tum_kapsamlari_listele()

    assert kayitlar == {
        'a.pdf': {'kapsam': 'ozel', 'sohbet_id': '1'},
        'b.pdf': {'kapsam': 'global', 'sohbet_id': None},
    }


def test_belge_sil_kaydi_kaldirir():
    conversation_store.sohbet_ekle('1', 'Sohbet 1')
    belge_deposu.kapsam_kaydet('gecici.pdf', 'ozel', sohbet_id='1')
    belge_deposu.belge_sil('gecici.pdf')

    assert belge_deposu.kapsam_getir('gecici.pdf') is None
    assert belge_deposu.belge_erisilebilir_mi('gecici.pdf', '2') is True  # artik izlenmiyor -> global
