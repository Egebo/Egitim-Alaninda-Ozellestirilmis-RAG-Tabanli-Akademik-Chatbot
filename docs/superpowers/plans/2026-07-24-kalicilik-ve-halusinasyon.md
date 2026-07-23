# Belge Kalıcılığı ve Halüsinasyon Önleme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Uygulama yeniden başladığında önceden yüklenmiş belgeleri diskten (yeniden embed etmeden) RAG'a geri yükle. (2) Çok adımlı bir planda TÜM alt-sonuçlar boşsa LLM'e hiç gitmeden dürüst bir mesaj dön; sonuçlar boş değilse de sentez/arama prompt'larını "uydurma yapma" talimatıyla sıkılaştır.

**Architecture:** İki bağımsız görev grubu, aynı dosyalara dokunmuyorlar. Görev 1: `services/rag.py::RagManager.diskten_yukle()` + `core/lazy_imports.py`'de tek satırlık çağrı. Görev 2: `services/gap_analysis.py::tum_sonuclar_eksik_mi()` + `services/chat.py`'nin birleştirme dalına kısa devre + `services/orchestrator.py`'nin iki prompt'una ek talimat.

**Tech Stack:** Mevcut `_Chroma` (builtins injection), `langchain-core` — yeni bağımlılık yok.

## Global Constraints

- Görev 1: senkron yükleme (thread/queue yok); bir belgenin yüklenmesi başarısız olursa sadece o belge atlanır, `logger.warning(...)` ile loglanır, diğerleri etkilenmez; sadece `.pdf/.xlsx/.xls/.txt` desteklenir; `document_store` (kapsam kayıtları) bu akışa dahil değil.
- Görev 2: kısa devre sadece `len(sonuclar) > 1` durumunda devreye girer; tetiklenirse `sonuclari_birlestir` hiç çağrılmaz (LLM maliyeti eklemez, azaltır); sabit mesaj: `"Bu konuda veritabanında, yüklü belgelerde veya internette güvenilir bir bilgi bulamadım. Sorunuzu farklı bir şekilde ifade etmeyi deneyebilirsiniz."`; prompt sıkılaştırması davranışı test edilmez (LLM çıktısı bu projede hiçbir yerde test edilmiyor), sadece prompt METNİNDE yeni talimatın var olduğu doğrulanır.
- Yeni bağımlılık eklenmez. Türkçe fonksiyon/test isimleri kullanılır (mevcut konvansiyon).
- Specler: `docs/superpowers/specs/2026-07-24-belge-kaliciligi-design.md`, `docs/superpowers/specs/2026-07-24-halusinasyon-onleme-design.md`

---

### Task 1: `RagManager.diskten_yukle()` — belge kalıcılığı

**Files:**
- Modify: `services/rag.py` (üst kısım — import + `RagManager.__init__`, satır 1-30)
- Modify: `core/lazy_imports.py` (satır 123-125 civarı)
- Test: `tests/unit/test_rag_diskten_yukle.py`

**Interfaces:**
- Consumes: `builtins._Chroma` (mevcut, `core/lazy_imports.py::ensure_imports()` içinde builtins'e enjekte ediliyor), `RagManager.embeddings` property (mevcut).
- Produces: `RagManager(cache_dir='./chroma_db', upload_dir='uploads')` (yeni `upload_dir` parametresi), `RagManager.diskten_yukle() -> None` (yan etkisi: `self.documents`'ı doldurur).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rag_diskten_yukle.py`:

```python
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
    monkeypatch.setattr(builtins, '_Chroma', _SahteChroma)
    rm = _kur(tmp_path, ['belge.txt'], ['belge_txt'])

    rm.diskten_yukle()

    assert 'belge.txt' in rm.documents
    assert rm.documents['belge.txt']['vector_store'].persist_directory.endswith('belge_txt')


def test_chroma_klasoru_yoksa_atlanir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, '_Chroma', _SahteChroma)
    rm = _kur(tmp_path, ['belge.txt'], [])

    rm.diskten_yukle()

    assert rm.documents == {}


def test_chroma_baglantisi_patlarsa_atlanir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, '_Chroma', _PatlayanChroma)
    rm = _kur(tmp_path, ['belge.txt'], ['belge_txt'])

    rm.diskten_yukle()

    assert rm.documents == {}


def test_desteklenmeyen_uzanti_ve_gitkeep_atlanir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, '_Chroma', _SahteChroma)
    rm = _kur(tmp_path, ['.gitkeep', 'belge.docx'], ['belge_docx'])

    rm.diskten_yukle()

    assert rm.documents == {}


def test_uploads_klasoru_yoksa_hata_firlatmaz(tmp_path):
    rm = RagManager(cache_dir=str(tmp_path / 'chroma_db'), upload_dir=str(tmp_path / 'olmayan_klasor'))
    rm.diskten_yukle()
    assert rm.documents == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_rag_diskten_yukle.py -v`
Expected: FAIL with `AttributeError: 'RagManager' object has no attribute 'diskten_yukle'` (ilk 4 test), `test_uploads_klasoru_yoksa_hata_firlatmaz` de aynı sebeple FAIL.

- [ ] **Step 3: `services/rag.py`'yi güncelle**

Dosyanın başındaki (satır 1-11) mevcut:

```python
"""Yüklenen belgeler üzerinde RAG (Retrieval-Augmented Generation) sorgulama."""
import os
import shutil

from core.state import state
from core.llm import llm_invoke_tracked, extract_text
from core import document_store as belge_deposu

SIMILARITY_THRESHOLD = 0.45
MAX_TOTAL_CHUNKS = 20
FALLBACK_THRESHOLD = 0.1
```

şu şekilde değiştir (logging eklenir):

```python
"""Yüklenen belgeler üzerinde RAG (Retrieval-Augmented Generation) sorgulama."""
import logging
import os
import shutil

from core.state import state
from core.llm import llm_invoke_tracked, extract_text
from core import document_store as belge_deposu

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.45
MAX_TOTAL_CHUNKS = 20
FALLBACK_THRESHOLD = 0.1
DESTEKLENEN_UZANTILAR = ('pdf', 'xlsx', 'xls', 'txt')
```

Mevcut (satır 23-27):

```python
class RagManager:
    def __init__(self, cache_dir='./chroma_db'):
        self.cache_dir = cache_dir
        self.documents = {}
        self.db = None
```

şu şekilde değiştir:

```python
class RagManager:
    def __init__(self, cache_dir='./chroma_db', upload_dir='uploads'):
        self.cache_dir = cache_dir
        self.upload_dir = upload_dir
        self.documents = {}
        self.db = None

    def diskten_yukle(self):
        """
        uploads/ klasorundeki her desteklenen dosya icin, karsilik gelen
        chroma_db/<guvenli_isim>/ klasoru varsa (daha once embed edilmis ve
        silinmemis) yeniden embed etmeden baglanip self.documents'a ekler.
        Klasor yoksa ya da baglanti basarisiz olursa o belge atlanir, loglanir.
        """
        if not os.path.isdir(self.upload_dir):
            return
        for dosya_adi in os.listdir(self.upload_dir):
            ext = dosya_adi.rsplit('.', 1)[-1].lower() if '.' in dosya_adi else ''
            if ext not in DESTEKLENEN_UZANTILAR:
                continue
            if dosya_adi in self.documents:
                continue
            safe = dosya_adi.replace('.', '_').replace(' ', '_')
            doc_persist_dir = os.path.join(self.cache_dir, safe)
            if not os.path.isdir(doc_persist_dir):
                continue
            try:
                vs = _Chroma(persist_directory=doc_persist_dir, embedding_function=self.embeddings)
                self.documents[dosya_adi] = {'vector_store': vs}
            except Exception:
                logger.warning(f'⚠️ {dosya_adi} diskten geri yuklenemedi, atlaniyor', exc_info=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_rag_diskten_yukle.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: `core/lazy_imports.py`'ye çağrı noktasını ekle**

Mevcut (satır 123-125):

```python
    # ── Belge Analiz Yöneticisi (RAG Manager) Kurulumu ────────────────────────
    state.rag_manager = RagManager()
    state.rag_manager.db = state.db
```

şu şekilde değiştir:

```python
    # ── Belge Analiz Yöneticisi (RAG Manager) Kurulumu ────────────────────────
    state.rag_manager = RagManager()
    state.rag_manager.db = state.db
    state.rag_manager.diskten_yukle()
```

Bu satır otomatik test edilmiyor — `ensure_imports()` gerçek ML kütüphaneleri yüklediği için bu projenin test suite'i onu hiç doğrudan çağırmıyor (bkz. `tests/conftest.py::fresh_state`'in `state.imports_done = True` ile bunu atlaması). Doğrulama Step 6'da manuel.

- [ ] **Step 6: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: Tüm testler (107) PASS.

Sonra manuel doğrulama: `python app.py` çalıştır, `uploads/`'ta önceden yüklenmiş bir belge varsa (örn. bir `.txt`/`.pdf`), tarayıcıda giriş yap, o belgeyle ilgili bir soru sor — RAG aracının devreye girdiğini (adım göstergesinde "Belgeler taranıyor") gör.

- [ ] **Step 7: Commit**

```bash
git add services/rag.py core/lazy_imports.py tests/unit/test_rag_diskten_yukle.py
git commit -m "feat: acilista yuklu belgeleri diskten geri yukle (RagManager.diskten_yukle)"
```

---

### Task 2: Halüsinasyon önleme — kısa devre + prompt sıkılaştırması

**Files:**
- Modify: `services/gap_analysis.py` (sona ekleme)
- Modify: `services/chat.py` (satır 8-10 import bloğu, satır 195-202 birleştirme dalı)
- Modify: `services/orchestrator.py` (satır 55-63 `internet_arama_yap`, satır 246-262 `sonuclari_birlestir`)
- Test: `tests/unit/test_gap_analysis.py`, `tests/integration/test_chat_flow.py`, `tests/unit/test_orchestrator_prompts.py` (yeni)

**Interfaces:**
- Consumes: `services.gap_analysis.EKSIK_BILGI_IFADELERI` (mevcut, aynı dosyada).
- Produces: `tum_sonuclar_eksik_mi(sonuclar: list) -> bool` (Task 2 içinde kullanılır), `services.chat.BILGI_BULUNAMADI_MESAJI: str` (test dosyalarının import edeceği sabit).

- [ ] **Step 1: Write the failing tests (gap_analysis)**

`tests/unit/test_gap_analysis.py`'nin başındaki import satırını güncelle:

```python
from services.gap_analysis import cevap_eksik_mi, boslugu_kapat, tum_sonuclar_eksik_mi
```

(mevcut `from services.gap_analysis import cevap_eksik_mi, boslugu_kapat` satırının yerine geçer)

Dosyanın sonuna ekle:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_gap_analysis.py -v`
Expected: Yeni 3 test FAIL (`ImportError: cannot import name 'tum_sonuclar_eksik_mi'`), diğer mevcut testler bu import hatası yüzünden COLLECTION ERROR verir (dosya genelinde import satırı bozuk olduğu için).

- [ ] **Step 3: `services/gap_analysis.py`'ye fonksiyonu ekle**

Dosyanın sonuna ekle:

```python
def tum_sonuclar_eksik_mi(sonuclar: list) -> bool:
    """
    Coklu adimli bir planda TUM adimlarin sonucu bilgi icermiyorsa True doner.
    cevap_eksik_mi'den farki: sadece DB_QUERY/RAG degil, TUM araclarin (SEARCH
    dahil) sonucuna bakar — birlestirme adiminin bos/ilgisiz parcalardan hikaye
    uydurmasini (halusinasyon) onlemek icin kullanilir.
    """
    if not sonuclar:
        return False
    for s in sonuclar:
        cevap_lower = (s['cevap'] or '').lower()
        if not any(ifade in cevap_lower for ifade in EKSIK_BILGI_IFADELERI):
            return False
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_gap_analysis.py -v`
Expected: Tüm testler (8) PASS.

- [ ] **Step 5: Write the failing test (chat.py wiring)**

`tests/integration/test_chat_flow.py`'nin başındaki import satırını güncelle:

```python
from services.chat import chat_yanit_uret, chat_yanit_uret_stream, BILGI_BULUNAMADI_MESAJI
```

(mevcut `from services.chat import chat_yanit_uret, chat_yanit_uret_stream` satırının yerine geçer)

Dosyanın sonuna ekle:

```python
def test_tum_sonuclar_eksikse_birlestirme_atlanir(mocker, fresh_state, sahte_llm):
    conv_id = _new_conv()
    mocker.patch('services.chat._get_llm', return_value=sahte_llm())
    mocker.patch('services.chat.gorev_plani_olustur', return_value=[
        {'tool': 'DB_QUERY', 'soru': 'soru1'},
        {'tool': 'SEARCH', 'soru': 'soru2'},
    ])
    mocker.patch('services.chat.adim_calistir', side_effect=[
        {'tool': 'DB_QUERY', 'soru': 'soru1', 'cevap': 'Aradığınız kriterlere uygun kayıt bulunamadı.', 'kaynak': 'Veritabanı'},
        {'tool': 'SEARCH', 'soru': 'soru2', 'cevap': 'yeterli bilgi bulunmamaktadır', 'kaynak': 'İnternet'},
    ])
    birlestir_mock = mocker.patch('services.chat.sonuclari_birlestir')

    olaylar = list(chat_yanit_uret_stream('soru1 ve soru2', conv_id, 'chatgpt'))

    birlestir_mock.assert_not_called()
    tipler = [o['type'] for o in olaylar]
    assert 'birlestiriliyor' not in tipler
    final = [o for o in olaylar if o['type'] == 'final'][0]
    assert final['cevap'] == BILGI_BULUNAMADI_MESAJI
```

(`services.chat.yansit` burada bilerek mock'lanmıyor — `sahte_llm()`'in `bind_tools` metodu yok, `yansit()` bu durumda kendi fail-open davranışına düşer ve rafine soruyla tekrar denemez; bu, `test_cok_adimli_plan_birlestirilir`'in de zaten güvendiği mevcut davranış.)

- [ ] **Step 6: Run the test to verify it fails**

Run: `pytest tests/integration/test_chat_flow.py -v`
Expected: Yeni test FAIL (`ImportError: cannot import name 'BILGI_BULUNAMADI_MESAJI'`), dosya genelinde collection error.

- [ ] **Step 7: `services/chat.py`'yi güncelle**

Mevcut (satır 8-15):

```python
from services.orchestrator import gorev_plani_olustur, adim_calistir, sonuclari_birlestir, genel_cevap_uret
from services.gap_analysis import cevap_eksik_mi, boslugu_kapat
from services.guardrails import girdi_guvenli_mi, cikti_guvenli_mi, gunluk_butce_asildi_mi, gunluk_maliyete_ekle
from services.reflection import yansit

logger = logging.getLogger(__name__)

YANSITILACAK_ARACLAR = {'DB_QUERY', 'RAG', 'SEARCH'}
```

şu şekilde değiştir:

```python
from services.orchestrator import gorev_plani_olustur, adim_calistir, sonuclari_birlestir, genel_cevap_uret
from services.gap_analysis import cevap_eksik_mi, boslugu_kapat, tum_sonuclar_eksik_mi
from services.guardrails import girdi_guvenli_mi, cikti_guvenli_mi, gunluk_butce_asildi_mi, gunluk_maliyete_ekle
from services.reflection import yansit

logger = logging.getLogger(__name__)

YANSITILACAK_ARACLAR = {'DB_QUERY', 'RAG', 'SEARCH'}
BILGI_BULUNAMADI_MESAJI = (
    'Bu konuda veritabanında, yüklü belgelerde veya internette güvenilir bir '
    'bilgi bulamadım. Sorunuzu farklı bir şekilde ifade etmeyi deneyebilirsiniz.'
)
```

Mevcut (satır 195-202):

```python
        niyet = '+'.join(dict.fromkeys(s['tool'] for s in sonuclar))
        if len(sonuclar) == 1:
            cevap = sonuclar[0]['cevap']
            kaynak = sonuclar[0]['kaynak']
        else:
            yield {'type': 'birlestiriliyor'}
            cevap = sonuclari_birlestir(soru_baglamli, sonuclar, llm)
            kaynak = '+'.join(dict.fromkeys(s['kaynak'] for s in sonuclar))
```

şu şekilde değiştir:

```python
        niyet = '+'.join(dict.fromkeys(s['tool'] for s in sonuclar))
        if len(sonuclar) == 1:
            cevap = sonuclar[0]['cevap']
            kaynak = sonuclar[0]['kaynak']
        elif tum_sonuclar_eksik_mi(sonuclar):
            cevap = BILGI_BULUNAMADI_MESAJI
            kaynak = '+'.join(dict.fromkeys(s['kaynak'] for s in sonuclar))
        else:
            yield {'type': 'birlestiriliyor'}
            cevap = sonuclari_birlestir(soru_baglamli, sonuclar, llm)
            kaynak = '+'.join(dict.fromkeys(s['kaynak'] for s in sonuclar))
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/integration/test_chat_flow.py -v`
Expected: Tüm testler (9) PASS.

- [ ] **Step 9: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: Tüm testler PASS.

- [ ] **Step 10: Commit (kısa devre kısmı)**

```bash
git add services/gap_analysis.py services/chat.py tests/unit/test_gap_analysis.py tests/integration/test_chat_flow.py
git commit -m "fix: tum sonuclar eksikse LLM'e gitmeden durust mesaj don (halusinasyon onleme)"
```

- [ ] **Step 11: Write the failing tests (prompt sıkılaştırması)**

Create `tests/unit/test_orchestrator_prompts.py`:

```python
"""sonuclari_birlestir ve internet_arama_yap prompt'larinin halusinasyon
onleme talimatlarini icerdigini dogrular. Gercek LLM cagrisi yapilmaz,
llm_invoke_tracked mock'lanir, sadece gonderilen prompt metni kontrol edilir."""
from services.orchestrator import sonuclari_birlestir, internet_arama_yap


def test_sonuclari_birlestir_uydurma_yapma_talimati_icerir(mocker):
    mock_invoke = mocker.patch('services.orchestrator.llm_invoke_tracked', return_value='cevap')
    mocker.patch('services.orchestrator.extract_text', return_value='cevap')
    sonuclar = [{'kaynak': 'Veritabanı', 'soru': 'soru1', 'cevap': 'kayıt bulunamadı'}]

    sonuclari_birlestir('soru', sonuclar, llm=object())

    prompt = mock_invoke.call_args[0][1]
    assert 'uydurma baglantilar' in prompt.lower()


def test_internet_arama_yap_ilgisiz_sonuc_talimati_icerir(mocker, fresh_state):
    fresh_state.SEARCH_OK = True
    fresh_state.search_tool = mocker.Mock(run=mocker.Mock(return_value='arama sonucu metni'))
    mock_invoke = mocker.patch('services.orchestrator.llm_invoke_tracked', return_value='cevap')
    mocker.patch('services.orchestrator.extract_text', return_value='cevap')

    internet_arama_yap('soru', llm=object())

    prompt = mock_invoke.call_args[0][1]
    assert 'ilgisiz sonuçlardan emin bir cevap uydurma' in prompt.lower()
```

- [ ] **Step 12: Run the tests to verify they fail**

Run: `pytest tests/unit/test_orchestrator_prompts.py -v`
Expected: İki test de FAIL (`AssertionError` — talimat metni henüz prompt'ta yok).

- [ ] **Step 13: `services/orchestrator.py`'yi güncelle**

Mevcut (satır 55-63):

```python
def internet_arama_yap(soru: str, llm=None) -> str:
    llm = llm or state.llm_default
    if not state.SEARCH_OK: return genel_cevap_uret(soru, '', llm)
    try:
        sonuc = state.search_tool.run(soru)
        return extract_text(llm_invoke_tracked(llm,
            f'Arama sonuçlarına dayanarak Türkçe cevap ver.\nSoru: {soru}\nSonuçlar: {sonuc}\nCevap:'
        ))
    except Exception as e:
```

şu şekilde değiştir:

```python
def internet_arama_yap(soru: str, llm=None) -> str:
    llm = llm or state.llm_default
    if not state.SEARCH_OK: return genel_cevap_uret(soru, '', llm)
    try:
        sonuc = state.search_tool.run(soru)
        return extract_text(llm_invoke_tracked(llm,
            f'Arama sonuçlarına dayanarak Türkçe cevap ver. Eğer arama sonuçları '
            f'soruyla gerçekten ilgili değilse (örn. farklı bir kişi, yer ya da '
            f'konu hakkındaysa), bunları kullanma ve sonuçların soruyla ilgili '
            f'görünmediğini belirt — asla ilgisiz sonuçlardan emin bir cevap uydurma.\n'
            f'Soru: {soru}\nSonuçlar: {sonuc}\nCevap:'
        ))
    except Exception as e:
```

Mevcut (satır 254-261):

```python
    prompt = f"""Kullanicinin sorusu birden fazla kaynaktan toplanan bilgiyle cevaplandi. Asagidaki parcalari
tek, akici ve tutarli bir Turkce yanitta birlestir. Kaynaklari yanitin icinde dogal bir sekilde belirt,
gereksiz tekrar yapma.

Kullanicinin orijinal sorusu: "{soru}"

Toplanan bilgiler:
{parcalar}
```

şu şekilde değiştir:

```python
    prompt = f"""Kullanicinin sorusu birden fazla kaynaktan toplanan bilgiyle cevaplandi. Asagidaki parcalari
tek, akici ve tutarli bir Turkce yanitta birlestir. Kaynaklari yanitin icinde dogal bir sekilde belirt,
gereksiz tekrar yapma.

ONEMLI: Parcalardan biri "bulunamadi"/"bilgi yok" turunden bir sonuc iceriyorsa,
bunu oldugu gibi belirt — o kaynaktan gercek bilgi olmadigini gizleme. Farkli
parcalardaki isimleri, olaylari veya kisileri birbiriyle iliskilendirerek
varsayimsal/uydurma baglantilar KURMA. Sadece parcalarda GERCEKTEN yazili olan
bilgiyi kullan.

Kullanicinin orijinal sorusu: "{soru}"

Toplanan bilgiler:
{parcalar}
```

(Bu iki bloğun hemen altındaki kapanış satırları — `\nBirlesik yanit:"""` ve `return extract_text(...)` — değişmeden kalır, sadece araya yeni paragraf giriyor.)

- [ ] **Step 14: Run the tests to verify they pass**

Run: `pytest tests/unit/test_orchestrator_prompts.py -v`
Expected: İki test de PASS.

- [ ] **Step 15: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: Tüm testler PASS.

- [ ] **Step 16: Commit**

```bash
git add services/orchestrator.py tests/unit/test_orchestrator_prompts.py
git commit -m "fix: sentez ve internet arama prompt'larina uydurma-yapma talimati ekle"
```
