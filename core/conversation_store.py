"""Konusmalarin (sohbetlerin) SQLite'a kalici yazilmasi.

`core.state.state.conversations` calisma aninda hala bellek-ici "source of
truth" olarak kalir (mevcut okuma yollari degismez) — bu modul sadece
write-through bir kalicilik katmanidir: her mutasyonda (yeni sohbet, mesaj,
silme, sifirlama) ayni bilgiyi diske de yazar, uygulama basladiginda ise
diskten belleğe geri yukler. Ayri bir `conversations.db` dosyasi kullanilir
(demo_okul.db'nin şema-uyusmazliginda kendini yeniden kuran mantigindan
bagimsiz olsun diye).
"""
import sqlite3

DB_YOLU = 'conversations.db'

_SEMA = '''
    CREATE TABLE IF NOT EXISTS sohbetler (
        id TEXT PRIMARY KEY,
        isim TEXT NOT NULL,
        tokens INTEGER NOT NULL DEFAULT 0,
        cost REAL NOT NULL DEFAULT 0.0,
        olusturulma TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS mesajlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sohbet_id TEXT NOT NULL REFERENCES sohbetler(id) ON DELETE CASCADE,
        kullanici TEXT NOT NULL,
        cevap TEXT,
        cevap_norag TEXT,
        kaynak TEXT,
        tokens INTEGER,
        cost REAL,
        niyet TEXT,
        sira INTEGER NOT NULL
    );
'''


def _baglan():
    """Her cagrida taze bir baglanti acar (Flask dev sunucusu istekleri farkli
    thread'lerde isleyebilir; sqlite3 baglantilari thread'ler arasi paylasilamaz).
    Sema idempotent sekilde burada garanti edilir, ayri bir kurulum adimina
    gerek birakmaz."""
    conn = sqlite3.connect(DB_YOLU)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.executescript(_SEMA)
    return conn


def hepsini_yukle():
    """DB'deki tum sohbetleri ve mesajlarini state.conversations formatinda
    (dict) dondurur. Hic sohbet yoksa bos dict doner."""
    conn = _baglan()
    conn.row_factory = sqlite3.Row
    try:
        sohbetler = conn.execute('SELECT * FROM sohbetler').fetchall()
        sonuc = {}
        for s in sohbetler:
            mesajlar = conn.execute(
                'SELECT * FROM mesajlar WHERE sohbet_id = ? ORDER BY sira', (s['id'],)
            ).fetchall()
            sonuc[s['id']] = {
                'name': s['isim'],
                'tokens': s['tokens'],
                'cost': s['cost'],
                'history': [
                    {
                        'user': m['kullanici'], 'cevap': m['cevap'], 'cevap_norag': m['cevap_norag'],
                        'kaynak': m['kaynak'], 'tokens': m['tokens'], 'cost': m['cost'], 'niyet': m['niyet'],
                    }
                    for m in mesajlar
                ],
            }
        return sonuc
    finally:
        conn.close()


def sohbet_ekle(conv_id: str, isim: str):
    conn = _baglan()
    try:
        conn.execute('INSERT OR IGNORE INTO sohbetler (id, isim) VALUES (?, ?)', (conv_id, isim))
        conn.commit()
    finally:
        conn.close()


def sohbet_ismini_guncelle(conv_id: str, yeni_isim: str):
    conn = _baglan()
    try:
        conn.execute('UPDATE sohbetler SET isim = ? WHERE id = ?', (yeni_isim, conv_id))
        conn.commit()
    finally:
        conn.close()


def sohbet_sil(conv_id: str):
    conn = _baglan()
    try:
        conn.execute('DELETE FROM sohbetler WHERE id = ?', (conv_id,))
        conn.commit()
    finally:
        conn.close()


def sohbet_sifirla(conv_id: str):
    conn = _baglan()
    try:
        conn.execute('DELETE FROM mesajlar WHERE sohbet_id = ?', (conv_id,))
        conn.execute('UPDATE sohbetler SET tokens = 0, cost = 0.0 WHERE id = ?', (conv_id,))
        conn.commit()
    finally:
        conn.close()


def mesaj_ekle(conv_id: str, mesaj: dict, sira: int, toplam_tokens: int, toplam_cost: float):
    conn = _baglan()
    try:
        conn.execute(
            'INSERT INTO mesajlar (sohbet_id, kullanici, cevap, cevap_norag, kaynak, tokens, cost, niyet, sira) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (conv_id, mesaj['user'], mesaj['cevap'], mesaj.get('cevap_norag'), mesaj['kaynak'],
             mesaj['tokens'], mesaj['cost'], mesaj['niyet'], sira)
        )
        conn.execute('UPDATE sohbetler SET tokens = ?, cost = ? WHERE id = ?', (toplam_tokens, toplam_cost, conv_id))
        conn.commit()
    finally:
        conn.close()
