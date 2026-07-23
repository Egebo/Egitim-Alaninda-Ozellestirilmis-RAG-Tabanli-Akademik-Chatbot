from services.gap_analysis import cevap_eksik_mi, boslugu_kapat, tum_sonuclar_eksik_mi


def test_db_query_bos_sonuc_eksik_sayilir():
    sonuclar = [{'tool': 'DB_QUERY', 'cevap': 'Aradığınız kriterlere uygun kayıt bulunamadı.', 'kaynak': 'Veritabanı'}]
    assert cevap_eksik_mi(sonuclar) is True


def test_rag_hata_kaynagi_eksik_sayilir():
    sonuclar = [{'tool': 'RAG', 'cevap': 'bir seyler patladi', 'kaynak': 'Hata'}]
    assert cevap_eksik_mi(sonuclar) is True


def test_basarili_db_sonucu_eksik_sayilmaz():
    sonuclar = [{'tool': 'DB_QUERY', 'cevap': 'Sonuç: **25**', 'kaynak': 'Veritabanı'}]
    assert cevap_eksik_mi(sonuclar) is False


def test_general_bos_gibi_gorunse_de_eksik_sayilmaz():
    # GENERAL/META bilgi arayan arac degil; "kayıt bulunamadı" gecse bile boşluk sayilmaz.
    sonuclar = [{'tool': 'GENERAL', 'cevap': 'kayıt bulunamadı diyebilirim', 'kaynak': 'Sohbet'}]
    assert cevap_eksik_mi(sonuclar) is False


def test_boslugu_kapat_search_adimi_ekler(mocker):
    mock_adim_calistir = mocker.patch('services.gap_analysis.adim_calistir')
    mock_adim_calistir.return_value = {
        'tool': 'SEARCH', 'soru': 'soru', 'cevap': 'internet cevabi', 'kaynak': 'İnternet'
    }
    sonuclar = [{'tool': 'DB_QUERY', 'cevap': 'kayıt bulunamadı', 'kaynak': 'Veritabanı'}]

    yeni_sonuclar = boslugu_kapat('soru', sonuclar, '', llm=None, model_name='chatgpt')

    assert len(yeni_sonuclar) == 2
    assert yeni_sonuclar[-1]['tool'] == 'SEARCH'
    mock_adim_calistir.assert_called_once()


def test_boslugu_kapat_search_zaten_denenmisse_tekrar_eklemez(mocker):
    mock_adim_calistir = mocker.patch('services.gap_analysis.adim_calistir')
    sonuclar = [{'tool': 'SEARCH', 'cevap': 'zaten arandi', 'kaynak': 'İnternet'}]

    yeni_sonuclar = boslugu_kapat('soru', sonuclar, '', llm=None, model_name='chatgpt')

    assert yeni_sonuclar == sonuclar
    mock_adim_calistir.assert_not_called()


def test_tum_sonuclar_eksik_ise_true():
    sonuclar = [
        {'tool': 'DB_QUERY', 'cevap': 'Aradığınız kriterlere uygun kayıt bulunamadı.', 'kaynak': 'Veritabanı'},
        {'tool': 'SEARCH', 'cevap': 'yeterli bilgi bulunmamaktadır', 'kaynak': 'İnternet'},
    ]
    assert tum_sonuclar_eksik_mi(sonuclar) is True


def test_bir_sonuc_gercek_bilgi_icerirse_false():
    sonuclar = [
        {'tool': 'DB_QUERY', 'cevap': 'Aradığınız kriterlere uygun kayıt bulunamadı.', 'kaynak': 'Veritabanı'},
        {'tool': 'SEARCH', 'cevap': 'Ali Kaya 5 yıl deneyimli bir yazılımcı.', 'kaynak': 'İnternet'},
    ]
    assert tum_sonuclar_eksik_mi(sonuclar) is False


def test_bos_liste_false_doner():
    assert tum_sonuclar_eksik_mi([]) is False
