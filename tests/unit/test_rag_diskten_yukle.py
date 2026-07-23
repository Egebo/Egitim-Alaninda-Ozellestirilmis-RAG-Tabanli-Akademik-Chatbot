"""RagManager.diskten_yukle()'nin uploads/ + chroma_db/ uzerinden belgeleri
yeniden embed etmeden geri yukledigini dogrular. Gercek Chroma/embedding
kullanilmaz, builtins._Chroma sahte bir sinifla degistirilir."""
import builtins

from services.rag import RagManager


class _SahteChroma:
    def __init__(self, persist_directory, embedding_function):
        self.persist_directory = persist_directory


class _PatlayanChroma:
    def __init__(self, persist_directory, embedding_function):
        raise RuntimeError('baglanti basarisiz')


def _kur(tmp_path, dosyalar, chroma_klasorleri):
    upload_dir = tmp_path / 'uploads'
    cache_dir = tmp_path / 'chroma_db'
    upload_dir.mkdir()
    cache_dir.mkdir()
    for dosya_adi in dosyalar:
        (upload_dir / dosya_adi).write_text('icerik')
    for klasor_adi in chroma_klasorleri:
        (cache_dir / klasor_adi).mkdir()
    return RagManager(cache_dir=str(cache_dir), upload_dir=str(upload_dir))


def test_dosya_ve_chroma_klasoru_varsa_yuklenir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, '_Chroma', _SahteChroma, raising=False)
    rm = _kur(tmp_path, ['belge.txt'], ['belge_txt'])

    rm.diskten_yukle()

    assert 'belge.txt' in rm.documents
    assert rm.documents['belge.txt']['vector_store'].persist_directory.endswith('belge_txt')


def test_chroma_klasoru_yoksa_atlanir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, '_Chroma', _SahteChroma, raising=False)
    rm = _kur(tmp_path, ['belge.txt'], [])

    rm.diskten_yukle()

    assert rm.documents == {}


def test_chroma_baglantisi_patlarsa_atlanir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, '_Chroma', _PatlayanChroma, raising=False)
    rm = _kur(tmp_path, ['belge.txt'], ['belge_txt'])

    rm.diskten_yukle()

    assert rm.documents == {}


def test_desteklenmeyen_uzanti_ve_gitkeep_atlanir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, '_Chroma', _SahteChroma, raising=False)
    rm = _kur(tmp_path, ['.gitkeep', 'belge.docx'], ['belge_docx'])

    rm.diskten_yukle()

    assert rm.documents == {}


def test_uploads_klasoru_yoksa_hata_firlatmaz(tmp_path):
    rm = RagManager(cache_dir=str(tmp_path / 'chroma_db'), upload_dir=str(tmp_path / 'olmayan_klasor'))
    rm.diskten_yukle()
    assert rm.documents == {}
