"""services/auth.py'nin kullanici_dogrula fonksiyonunu, gecici/izole bir demo
veritabanina (test_db fixture) karsi dogrular. Gercek demo_okul.db'ye dokunmaz."""
from services import auth


def test_dogru_email_ve_sifre_ile_kullanici_doner(test_db, monkeypatch):
    monkeypatch.setattr(auth, 'DB_DOSYASI', test_db)
    kullanici = auth.kullanici_dogrula('admin@admin.com', '123456')
    assert kullanici == {'id': 1, 'email': 'admin@admin.com'}


def test_yanlis_sifre_none_doner(test_db, monkeypatch):
    monkeypatch.setattr(auth, 'DB_DOSYASI', test_db)
    assert auth.kullanici_dogrula('admin@admin.com', 'yanlis-sifre') is None


def test_bilinmeyen_email_none_doner(test_db, monkeypatch):
    monkeypatch.setattr(auth, 'DB_DOSYASI', test_db)
    assert auth.kullanici_dogrula('yok@yok.com', '123456') is None


def test_bos_girdi_none_doner(test_db, monkeypatch):
    monkeypatch.setattr(auth, 'DB_DOSYASI', test_db)
    assert auth.kullanici_dogrula('', '') is None
    assert auth.kullanici_dogrula('admin@admin.com', '') is None
