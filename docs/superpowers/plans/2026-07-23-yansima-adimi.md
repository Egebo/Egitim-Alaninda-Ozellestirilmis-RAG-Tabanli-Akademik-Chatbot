# Yansıma (Reflection) Adımı Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Orkestratörün RAG/DB_QUERY/SEARCH adımlarından sonra, cevabın soruyu yeterince karşılayıp karşılamadığını gerçek bir LLM çağrısıyla değerlendiren; yetersizse aynı aracı en fazla 1 kez rafine bir alt-soruyla tekrar çalıştıran; ve bu değerlendirme/tekrar-deneme anlarını frontend'de mevcut adım kartları üzerinden canlı gösteren bir katman eklemek.

**Architecture:** Yeni `services/reflection.py` modülü, `services/orchestrator.py::gorev_plani_olustur`'un kullandığı native tool-calling (Pydantic şema + `bind_tools`) desenini tekrarlayan tek bir saf fonksiyon (`yansit`) sağlar. Sıralama mantığı `services/chat.py::_chat_akisi`'nin mevcut adım döngüsüne doğrudan gömülür (ayrı bir wrapper yok). Frontend'de (`templates/index.html`) yeni DOM yapısı yok — mevcut `.step-item[data-tool="..."]` kartı 2 yeni akış olayıyla (`degerlendiriliyor`, `yeniden_deneniyor`) güncellenir.

**Tech Stack:** Mevcut `langchain-core` (`bind_tools`, Pydantic) — yeni bağımlılık yok.

## Global Constraints

- Yansıma sadece `DB_QUERY`, `RAG`, `SEARCH` adımlarında çalışır; `GENERAL`/`META` hiç dokunulmaz.
- En fazla 1 tekrar deneme — rafine soruyla çalıştırılan adım için ikinci bir yansıma yapılmaz.
- `yansit()` içindeki LLM çağrısı başarısız olursa (exception veya boş `tool_calls`) fail-open: `{'yeterli': True, 'rafine_soru': ''}` döner, `logger.exception(...)` ile loglanır. Akış asla kesilmez.
- `yansit()` mevcut `llm.bind_tools(...).invoke(...)` yolunu kullanır — ayrı bir token/maliyet takip mekanizması eklenmez, mevcut `DAILY_BUDGET_USD` guardrail'i otomatik kapsar.
- `gap_analysis.py::cevap_eksik_mi`/`boslugu_kapat` değişmeden kalır.
- Yeni bağımlılık eklenmez. Türkçe fonksiyon/test isimleri kullanılır (mevcut konvansiyon).
- Spec: `docs/superpowers/specs/2026-07-23-reflection-step-design.md`

---

### Task 1: `services/reflection.py` — `yansit()` fonksiyonu

**Files:**
- Create: `services/reflection.py`
- Test: `tests/unit/test_reflection.py`

**Interfaces:**
- Consumes: `core.state.state` (`state.llm_default`), mevcut `logging` konvansiyonu (`logger = logging.getLogger(__name__)`).
- Produces: `yansit(alt_soru: str, cevap: str, kaynak: str, llm=None) -> dict` — döndürdüğü sözlük her zaman `{'yeterli': bool, 'rafine_soru': str}` şeklinde (Task 2 bunu tüketecek).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_reflection.py`:

```python
"""yansit() fonksiyonunun native tool-calling (bind_tools/tool_calls) davranisini
dogrular. LLM gercekte cagrilmaz; llm.bind_tools(...).invoke(...) zincirini taklit
eden sahte bir nesne kullanilir (test_orchestrator_tool_calling.py'deki desenle
ayni sekle sahip)."""
from services.reflection import yansit


class _SahteYansimaYaniti:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ''


class _SahteYansimaLLM:
    def __init__(self, tool_calls=None, patlasin=False):
        self._tool_calls = tool_calls or []
        self._patlasin = patlasin

    def bind_tools(self, tools):
        if self._patlasin:
            raise RuntimeError('bind_tools basarisiz')
        return self

    def invoke(self, girdi):
        return _SahteYansimaYaniti(self._tool_calls)


def test_yeterli_cevapta_true_ve_bos_rafine_soru_doner():
    llm = _SahteYansimaLLM([
        {'name': 'YansimaSonucu', 'args': {'yeterli': True, 'rafine_soru': ''}, 'id': 'call_1'}
    ])
    sonuc = yansit('kac ogrenci var', 'Toplam 25 ogrenci var.', 'Veritabani', llm)
    assert sonuc == {'yeterli': True, 'rafine_soru': ''}


def test_yetersiz_cevapta_rafine_soru_doner():
    llm = _SahteYansimaLLM([
        {'name': 'YansimaSonucu', 'args': {'yeterli': False, 'rafine_soru': 'CVdeki is deneyimi kac yil'}, 'id': 'call_1'}
    ])
    sonuc = yansit('deneyim ne', 'Yeterli bilgi bulunmamaktadir.', 'Belgeler', llm)
    assert sonuc == {'yeterli': False, 'rafine_soru': 'CVdeki is deneyimi kac yil'}


def test_tool_calls_bos_ise_fail_open():
    llm = _SahteYansimaLLM([])
    sonuc = yansit('soru', 'cevap', 'Veritabani', llm)
    assert sonuc == {'yeterli': True, 'rafine_soru': ''}


def test_llm_hata_verirse_fail_open():
    llm = _SahteYansimaLLM(patlasin=True)
    sonuc = yansit('soru', 'cevap', 'Veritabani', llm)
    assert sonuc == {'yeterli': True, 'rafine_soru': ''}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_reflection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.reflection'` (dosya henüz yok).

- [ ] **Step 3: Create `services/reflection.py`**

```python
"""
Arac kullanilan adimlarin (RAG/DB_QUERY/SEARCH) cevabinin sorulan soruyu
yeterince karsilayip karsilamadigini degerlendiren, tek fonksiyonluk bir katman.
"""
import logging

from pydantic import BaseModel, Field

from core.state import state

logger = logging.getLogger(__name__)


class YansimaSonucu(BaseModel):
    """Bir arac adiminin cevabinin sorulan soruyu yeterince karsilayip karsilamadigini degerlendirir."""
    yeterli: bool = Field(description='Cevap soruyu yeterince karsiliyor mu')
    rafine_soru: str = Field(default='', description='Yetersizse daha net/spesifik bir alt-soru; yeterliyse bos')


def yansit(alt_soru: str, cevap: str, kaynak: str, llm=None) -> dict:
    """
    Bir arac adiminin sonucunu degerlendirir. LLM basarisiz olursa (exception
    veya bos tool_calls) fail-open davranir ({'yeterli': True, 'rafine_soru': ''})
    — akisi asla kesmez.
    """
    llm = llm or state.llm_default
    prompt = f"""Asagidaki soru-cevap ciftini degerlendir: cevap, sorulan soruyu
yeterince karsiliyor mu? Yuzeysel, alakasiz ya da "bilgi bulunamadi" turunden
bir cevapsa YETERSIZ say ve daha net/spesifik bir alt-soru oner.

Soru: "{alt_soru}"
Kaynak: {kaynak}
Cevap: "{cevap}\""""

    try:
        yanit = llm.bind_tools([YansimaSonucu]).invoke(prompt)
        tool_calls = list(getattr(yanit, 'tool_calls', None) or [])
        if tool_calls:
            args = tool_calls[0].get('args') or {}
            return {
                'yeterli': bool(args.get('yeterli', True)),
                'rafine_soru': str(args.get('rafine_soru') or ''),
            }
    except Exception:
        logger.exception('Yansima basarisiz, yeterli=True varsayilarak devam ediliyor')

    return {'yeterli': True, 'rafine_soru': ''}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_reflection.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: All previously-passing tests (95) still PASS — bu dosya henuz hicbir yerden import edilmiyor.

- [ ] **Step 6: Commit**

```bash
git add services/reflection.py tests/unit/test_reflection.py
git commit -m "feat: cevap yeterliligini degerlendiren yansit() fonksiyonunu ekle"
```

---

### Task 2: `services/chat.py` — adım döngüsüne yansımayı göm

**Files:**
- Modify: `services/chat.py` (import satırları, `_chat_akisi` içindeki adım döngüsü — mevcut satır 8-10 ve 167-173)
- Test: `tests/integration/test_chat_flow.py`

**Interfaces:**
- Consumes: `services.reflection.yansit(alt_soru, cevap, kaynak, llm) -> dict` (Task 1).
- Produces: `_chat_akisi` artık her RAG/DB_QUERY/SEARCH adımından sonra ek olarak `{'type': 'degerlendiriliyor', 'tool': str}` ve (sadece yetersizse) `{'type': 'yeniden_deneniyor', 'tool': str}` + ikinci bir `{'type': 'adim_bitti', ...}` yield eder. Bu, `chat_yanit_uret_stream`'i tüketen her şeyi (Task 3'teki frontend, SSE route) etkiler; `chat_yanit_uret` (sadece `final` alan) etkilenmez.

- [ ] **Step 1: Write the failing tests**

`tests/integration/test_chat_flow.py`'nin başındaki import satırını güncelle:

```python
from services.chat import chat_yanit_uret, chat_yanit_uret_stream
```

(mevcut `from services.chat import chat_yanit_uret` satırının yerine geçer)

Dosyanın sonuna ekle:

```python
def test_yansima_yeterliyse_tekrar_denenmez(mocker, fresh_state, sahte_llm):
    conv_id = _new_conv()
    mocker.patch('services.chat._get_llm', return_value=sahte_llm())
    mocker.patch('services.chat.gorev_plani_olustur', return_value=[{'tool': 'RAG', 'soru': 'CVdeki deneyim ne'}])
    adim_mock = mocker.patch('services.chat.adim_calistir', return_value={
        'tool': 'RAG', 'soru': 'CVdeki deneyim ne', 'cevap': '5 yıl deneyim', 'kaynak': 'Belgeler'
    })
    mocker.patch('services.chat.yansit', return_value={'yeterli': True, 'rafine_soru': ''})

    olaylar = list(chat_yanit_uret_stream('CVdeki deneyim ne', conv_id, 'chatgpt'))

    tipler = [o['type'] for o in olaylar]
    assert 'degerlendiriliyor' in tipler
    assert 'yeniden_deneniyor' not in tipler
    assert adim_mock.call_count == 1


def test_yansima_yetersizse_rafine_soruyla_tekrar_denenir(mocker, fresh_state, sahte_llm):
    conv_id = _new_conv()
    mocker.patch('services.chat._get_llm', return_value=sahte_llm())
    mocker.patch('services.chat.gorev_plani_olustur', return_value=[{'tool': 'RAG', 'soru': 'deneyim ne'}])
    mocker.patch('services.chat.adim_calistir', side_effect=[
        {'tool': 'RAG', 'soru': 'deneyim ne', 'cevap': 'Yeterli bilgi bulunmamaktadir.', 'kaynak': 'Belgeler'},
        {'tool': 'RAG', 'soru': 'CVdeki is deneyimi kac yil', 'cevap': '5 yıl deneyim', 'kaynak': 'Belgeler'},
    ])
    mocker.patch('services.chat.yansit', return_value={'yeterli': False, 'rafine_soru': 'CVdeki is deneyimi kac yil'})

    olaylar = list(chat_yanit_uret_stream('deneyim ne', conv_id, 'chatgpt'))

    tipler = [o['type'] for o in olaylar]
    assert 'degerlendiriliyor' in tipler
    assert 'yeniden_deneniyor' in tipler
    assert tipler.count('adim_bitti') == 2
    final = [o for o in olaylar if o['type'] == 'final'][0]
    assert final['cevap'] == '5 yıl deneyim'


def test_general_adiminda_yansima_calismaz(mocker, fresh_state, sahte_llm):
    conv_id = _new_conv()
    mocker.patch('services.chat._get_llm', return_value=sahte_llm())
    mocker.patch('services.chat.gorev_plani_olustur', return_value=[{'tool': 'GENERAL', 'soru': 'selam'}])
    mocker.patch('services.chat.adim_calistir', return_value={
        'tool': 'GENERAL', 'soru': 'selam', 'cevap': 'Merhaba!', 'kaynak': 'Sohbet'
    })
    yansit_mock = mocker.patch('services.chat.yansit')

    olaylar = list(chat_yanit_uret_stream('selam', conv_id, 'chatgpt'))

    tipler = [o['type'] for o in olaylar]
    assert 'degerlendiriliyor' not in tipler
    yansit_mock.assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/integration/test_chat_flow.py -v`
Expected: Yeni 3 test FAIL — `services.chat.yansit` henüz mevcut değil (`AttributeError` veya `ModuleNotFoundError` benzeri bir hata `mocker.patch` sırasında), diğer mevcut testler PASS kalır.

- [ ] **Step 3: `services/chat.py`'ye yansımayı göm**

`services/chat.py`'nin başındaki mevcut import + logger bloğunu (satır 8-12):

```python
from services.orchestrator import gorev_plani_olustur, adim_calistir, sonuclari_birlestir, genel_cevap_uret
from services.gap_analysis import cevap_eksik_mi, boslugu_kapat
from services.guardrails import girdi_guvenli_mi, cikti_guvenli_mi, gunluk_butce_asildi_mi, gunluk_maliyete_ekle

logger = logging.getLogger(__name__)
```

şu şekilde değiştir (bir import satırı ve bir sabit tanımı ekleniyor):

```python
from services.orchestrator import gorev_plani_olustur, adim_calistir, sonuclari_birlestir, genel_cevap_uret
from services.gap_analysis import cevap_eksik_mi, boslugu_kapat
from services.guardrails import girdi_guvenli_mi, cikti_guvenli_mi, gunluk_butce_asildi_mi, gunluk_maliyete_ekle
from services.reflection import yansit

logger = logging.getLogger(__name__)

YANSITILACAK_ARACLAR = {'DB_QUERY', 'RAG', 'SEARCH'}
```

`_chat_akisi` içindeki adım döngüsünü (mevcut satır 167-173) şu şekilde değiştir:

```python
    try:
        sonuclar = []
        for i, adim in enumerate(adimlar, start=1):
            yield {'type': 'adim_basladi', 'tool': adim['tool'], 'index': i, 'toplam': len(adimlar)}
            sonuc = adim_calistir(adim, gecmis, llm, model_name, conv_id)
            yield {'type': 'adim_bitti', 'tool': sonuc['tool'], 'kaynak': sonuc['kaynak']}

            if adim['tool'] in YANSITILACAK_ARACLAR:
                yield {'type': 'degerlendiriliyor', 'tool': sonuc['tool']}
                yansima = yansit(adim['soru'], sonuc['cevap'], sonuc['kaynak'], llm)
                if not yansima['yeterli'] and yansima['rafine_soru']:
                    yield {'type': 'yeniden_deneniyor', 'tool': sonuc['tool']}
                    rafine_adim = {'tool': adim['tool'], 'soru': yansima['rafine_soru']}
                    sonuc = adim_calistir(rafine_adim, gecmis, llm, model_name, conv_id)
                    yield {'type': 'adim_bitti', 'tool': sonuc['tool'], 'kaynak': sonuc['kaynak']}

            sonuclar.append(sonuc)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/integration/test_chat_flow.py -v`
Expected: Tüm testler (3 yeni + mevcut 6) PASS.

- [ ] **Step 5: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: Tüm testler (98) PASS.

- [ ] **Step 6: Commit**

```bash
git add services/chat.py tests/integration/test_chat_flow.py
git commit -m "feat: adim dongusune yansima adimini gom (degerlendiriliyor/yeniden_deneniyor olaylari)"
```

---

### Task 3: Frontend — adım kartlarında yansımayı göster

**Files:**
- Modify: `templates/index.html` (`handleStepEvent` fonksiyonu, mevcut satır 1365-1396)

**Interfaces:**
- Consumes: Task 2'nin SSE üzerinden (`/api/chat/stream`) yaydığı `{'type': 'degerlendiriliyor', 'tool': str}` ve `{'type': 'yeniden_deneniyor', 'tool': str}` olayları.
- Produces: Yok (bu, akışın son tüketicisi — otomatik test yok, bu projede frontend/JS testleri kapsam dışı, bkz. `docs/superpowers/specs/2026-07-20-test-suite-design.md` "Kapsam Dışı").

- [ ] **Step 1: `handleStepEvent`'e iki yeni dal ekle**

`templates/index.html` içinde, mevcut şu bloğu:

```js
  } else if (olay.type === 'adim_bitti') {
    const item = list.querySelector(`.step-item[data-tool="${olay.tool}"]`);
    if (item) {
      item.classList.remove('active', 'pending'); item.classList.add('done');
      const lbl = item.querySelector('.step-label');
      lbl.textContent = lbl.dataset.done;
      if (olay.kaynak) item.querySelector('.step-source').textContent = olay.kaynak;
    }
  } else if (olay.type === 'birlestiriliyor') {
```

şu şekilde değiştir (araya iki yeni `else if` dalı ekleniyor):

```js
  } else if (olay.type === 'adim_bitti') {
    const item = list.querySelector(`.step-item[data-tool="${olay.tool}"]`);
    if (item) {
      item.classList.remove('active', 'pending'); item.classList.add('done');
      const lbl = item.querySelector('.step-label');
      lbl.textContent = lbl.dataset.done;
      if (olay.kaynak) item.querySelector('.step-source').textContent = olay.kaynak;
    }
  } else if (olay.type === 'degerlendiriliyor') {
    const item = list.querySelector(`.step-item[data-tool="${olay.tool}"]`);
    if (item) {
      item.classList.remove('done', 'pending'); item.classList.add('active');
      item.querySelector('.step-label').textContent = 'Sonuç değerlendiriliyor…';
    }
    summaryLabel.textContent = 'Sonuç değerlendiriliyor…';
  } else if (olay.type === 'yeniden_deneniyor') {
    const item = list.querySelector(`.step-item[data-tool="${olay.tool}"]`);
    if (item) {
      item.querySelector('.step-label').textContent = 'Daha net bir soruyla tekrar deneniyor…';
    }
    summaryLabel.textContent = 'Daha net bir soruyla tekrar deneniyor…';
  } else if (olay.type === 'birlestiriliyor') {
```

- [ ] **Step 2: Manuel doğrulama**

Run: `python app.py` (yerel geliştirme sunucusu), tarayıcıda `http://localhost:5000` aç, giriş yap.

Bir RAG sorusu sor (örn. yüklü bir belgeyle ilgili net bir soru — reflection "yeterli" dönecek şekilde). Adım kartında sırasıyla şunları gör:
1. "Belgeler taranıyor…" (aktif)
2. "Sonuç değerlendiriliyor…" (aktif, aynı kart)
3. "Belgeler tarandı" (done)

`yansit`'in gerçekten "yetersiz" dönüp tekrar deneme adımını (`"Daha net bir soruyla tekrar deneniyor…"`) tetiklediği bir senaryoyu görmek için, geçici olarak `services/reflection.py::yansit`'in başına `return {'yeterli': False, 'rafine_soru': 'test rafine soru'}` satırını ekleyip bir RAG sorusu sor, adım kartında 4 aşamayı (tara → değerlendir → tekrar dene → tara) gör, sonra bu geçici satırı kaldır.

Expected: Konsol/network sekmesinde hata yok, adım kartı düzgün ilerliyor, final cevap görünüyor.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: yansima adimlarini (degerlendiriliyor/yeniden deneniyor) frontend'de goster"
```
