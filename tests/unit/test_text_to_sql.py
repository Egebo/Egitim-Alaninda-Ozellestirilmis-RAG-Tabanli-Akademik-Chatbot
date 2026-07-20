from services.text_to_sql import sql_temizle, db_sonuc_formatla


def test_kod_blogu_temizlenir():
    ham = "```sql\nSELECT * FROM ogrenciler;\n```"
    assert sql_temizle(ham) == "SELECT * FROM ogrenciler;"


def test_backtick_tek_tirnaga_donusur():
    ham = "SELECT * FROM `ogrenciler` WHERE ad = 'Ali'"
    assert sql_temizle(ham) == "SELECT * FROM 'ogrenciler' WHERE ad = 'Ali'"


def test_ilike_like_e_donusur():
    ham = "SELECT ad FROM ogrenciler WHERE bolum ILIKE '%Bilgisayar%'"
    assert sql_temizle(ham) == "SELECT ad FROM ogrenciler WHERE bolum LIKE '%Bilgisayar%'"


def test_llm_aciklama_metni_kirpilir():
    ham = 'Elbette, iste sorgu:\nSELECT * FROM ogrenciler WHERE ad = "Ali";'
    assert sql_temizle(ham) == "SELECT * FROM ogrenciler WHERE ad = 'Ali';"


def test_bos_sonuc_kayit_bulunamadi_mesaji_doner():
    assert db_sonuc_formatla('kaç öğrenci var', '[]') == 'Aradığınız kriterlere uygun kayıt bulunamadı.'


def test_tek_sayisal_sonuc_kac_ifadesiyle_formatlanir():
    assert db_sonuc_formatla('kaç öğrenci var', '[(25,)]') == 'Toplam **25**.'


def test_ortalama_iceren_soru_yuvarlanir():
    assert db_sonuc_formatla('ortalaması kaç', '[(85.333,)]') == 'Ortalama not: **85.33**'


def test_coklu_satir_madde_isaretiyle_listelenir():
    sonuc = "[('Ali', 'Kaya'), ('Ayşe', 'Demir')]"
    beklenen = '• Ali Kaya\n• Ayşe Demir'
    assert db_sonuc_formatla('öğrencileri listele', sonuc) == beklenen
