import sqlite3


def test_setup_database_beklenen_tablolari_olusturur(test_db):
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tablolar = {row[0] for row in cur.fetchall()}
    conn.close()

    assert tablolar == {
        'kullanicilar', 'bolumler', 'akademisyenler',
        'ogrenciler', 'dersler', 'notlar', 'projeler'
    }


def test_setup_database_tohum_veri_dogru_sayida(test_db):
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM bolumler')
    bolum_sayisi = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM ogrenciler')
    ogrenci_sayisi = cur.fetchone()[0]
    conn.close()

    assert bolum_sayisi == 5
    assert ogrenci_sayisi == 25
