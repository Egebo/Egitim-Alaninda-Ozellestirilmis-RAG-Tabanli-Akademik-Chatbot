"""Belgelerin kapsam (scope) bilgisinin kalıcı yazılması: her belge ya bir
sohbete özeldir (sadece o sohbet arayabilir) ya da global'dir (tüm sohbetler
arayabilir).

Aynı `conversations.db` dosyasını kullanır (conversation_store.DB_YOLU
üzerinden — bu modülü değil, canlı referansı okuyoruz ki testlerdeki
DB_YOLU yönlendirmesi burayı da otomatik kapsasın).

Tasarım kararı: bir belgenin bu tabloda HİÇ kaydı yoksa (ör. RagManager'a
doğrudan programatik olarak eklenmiş — eval harness, testler, ya da bu
özellikten önce yüklenmiş eski belgeler), erişim GLOBAL kabul edilir. Sadece
composer'dan/yönetim ekranından yapılan yeni yüklemeler açıkça bir kapsam
kaydı oluşturur.
"""
import sqlite3

from core import conversation_store

GECERLI_KAPSAMLAR = ('ozel', 'global')

_SEMA = '''
    CREATE TABLE IF NOT EXISTS belgeler (
        belge_adi TEXT PRIMARY KEY,
        kapsam TEXT NOT NULL CHECK (kapsam IN ('ozel', 'global')),
        sohbet_id TEXT REFERENCES sohbetler(id) ON DELETE CASCADE
    );
'''


def _baglan():
    # `belgeler.sohbet_id`, `sohbetler(id)`'e FK referansi verdigi icin o tablonun
    # once var oldugundan emin oluyoruz (conversation_store'un kendi semasi).
    conn = conversation_store._baglan()
    conn.executescript(_SEMA)
    return conn


def kapsam_kaydet(belge_adi: str, kapsam: str, sohbet_id: str = None):
    if kapsam not in GECERLI_KAPSAMLAR:
        raise ValueError(f"Geçersiz kapsam: {kapsam}")
    if kapsam == 'ozel' and not sohbet_id:
        raise ValueError("'ozel' kapsam için sohbet_id gerekli")
    conn = _baglan()
    try:
        conn.execute(
            'INSERT INTO belgeler (belge_adi, kapsam, sohbet_id) VALUES (?, ?, ?) '
            'ON CONFLICT(belge_adi) DO UPDATE SET kapsam = excluded.kapsam, sohbet_id = excluded.sohbet_id',
            (belge_adi, kapsam, sohbet_id if kapsam == 'ozel' else None)
        )
        conn.commit()
    finally:
        conn.close()


def kapsam_getir(belge_adi: str):
    """Kayıt varsa {'kapsam':..., 'sohbet_id':...} döner, yoksa None (izlenmeyen belge)."""
    conn = _baglan()
    try:
        conn.row_factory = sqlite3.Row
        satir = conn.execute(
            'SELECT kapsam, sohbet_id FROM belgeler WHERE belge_adi = ?', (belge_adi,)
        ).fetchone()
        return {'kapsam': satir['kapsam'], 'sohbet_id': satir['sohbet_id']} if satir else None
    finally:
        conn.close()


def belge_erisilebilir_mi(belge_adi: str, sohbet_id: str) -> bool:
    """Verilen sohbetin bu belgeyi arayıp aramayacağını belirler."""
    kayit = kapsam_getir(belge_adi)
    if kayit is None:
        return True  # izlenmeyen belge -> global/eski davranış
    if kayit['kapsam'] == 'global':
        return True
    return kayit['sohbet_id'] == sohbet_id


def tum_kapsamlari_listele() -> dict:
    """Tüm izlenen belgelerin {belge_adi: {'kapsam':..., 'sohbet_id':...}} eşlemesini döner.
    İzlenmeyen belgeler burada YOKTUR — çağıran taraf, RagManager'ın tam belge
    listesiyle birleştirip eksik olanları 'global' (izlenmeyen) sayar."""
    conn = _baglan()
    try:
        conn.row_factory = sqlite3.Row
        satirlar = conn.execute('SELECT belge_adi, kapsam, sohbet_id FROM belgeler').fetchall()
        return {s['belge_adi']: {'kapsam': s['kapsam'], 'sohbet_id': s['sohbet_id']} for s in satirlar}
    finally:
        conn.close()


def belge_sil(belge_adi: str):
    conn = _baglan()
    try:
        conn.execute('DELETE FROM belgeler WHERE belge_adi = ?', (belge_adi,))
        conn.commit()
    finally:
        conn.close()
