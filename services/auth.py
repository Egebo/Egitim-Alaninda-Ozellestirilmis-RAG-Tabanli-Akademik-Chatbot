"""Kullanici girisi (login) dogrulamasi.

demo_okul.db'deki kullanicilar tablosunu dogrudan sqlite3 ile okur; state.db
(SQLAlchemy/LangChain sarmalayicisi) Text-to-SQL icin agir bir kurulum
gerektirdigi ve login akisinin ensure_imports()'a (ML kutuphaneleri, embedding
modeli) bagli olmamasi gerektigi icin kullanilmaz.
"""
import sqlite3

from werkzeug.security import check_password_hash

DB_DOSYASI = 'demo_okul.db'


def kullanici_dogrula(email: str, sifre: str):
    """email/sifre dogru eslesirse {'id': int, 'email': str} dondurur, aksi
    halde None."""
    if not email or not sifre:
        return None

    conn = sqlite3.connect(DB_DOSYASI)
    try:
        satir = conn.execute(
            'SELECT kullaniciid, email, sifrehash FROM kullanicilar WHERE email = ?', (email,)
        ).fetchone()
    finally:
        conn.close()

    if not satir:
        return None

    kullaniciid, kayitli_email, sifrehash = satir
    if not sifrehash or not check_password_hash(sifrehash, sifre):
        return None

    return {'id': kullaniciid, 'email': kayitli_email}
