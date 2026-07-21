# Native Function Calling Refactor + LLM Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the orchestrator's hand-rolled "ask the LLM for JSON, parse with regex" planning step with OpenAI/Gemini's native tool-calling mechanism (LangChain `bind_tools`/`tool_calls`), and add a small, opt-in RAGAS-based eval harness that measures real answer quality (separate from the existing zero-cost pytest suite, which only checks code correctness).

**Architecture:** Two independent subsystems in one plan. (1) `services/orchestrator.py::gorev_plani_olustur` keeps its exact public signature and return shape but internally swaps regex/`json.loads` parsing for `llm.bind_tools([...]).invoke(...)` + `response.tool_calls`, using Pydantic schemas (one per tool) purely as structured-output definitions — the schemas are never actually executed by LangChain. (2) A new top-level `eval/` package (sibling to `tests/`, not part of the pytest suite) runs the golden-set questions through the real `chat_yanit_uret` pipeline and scores DB_QUERY answers with simple fuzzy matching and RAG answers with RAGAS metrics (`faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`). A small additive refactor to `services/rag.py` (extracting `RagManager.retrieve()` from `RagManager.ask_all()`) is required so the eval harness can capture the actual retrieved chunks that RAGAS needs.

**Tech Stack:** `langchain-core` (`bind_tools`, `pydantic` schemas — already a transitive dependency via `langchain-core`), `ragas` (new dependency), `pytest`/`pytest-mock` (existing).

## Global Constraints

- `gorev_plani_olustur(soru: str, llm=None, gecmis: str = '') -> list[{'tool': str, 'soru': str}]` — signature and return shape MUST NOT change. `tests/integration/test_chat_flow.py` mocks this function wholesale (`mocker.patch('services.chat.gorev_plani_olustur', ...)`), so its internals can change freely but its contract cannot.
- `niyet_kurala_gore` (the rule-based fast path) and the `adim_calistir` / `adimlar_calistir` / `sonuclari_birlestir` execution flow in `services/chat.py` are NOT touched by this plan.
- `RagManager.ask_all()`'s public signature and return value (`(cevap, kaynak)` tuple or `None`) MUST NOT change — only its internal retrieval logic is extracted into a new `retrieve()` method.
- Every new pytest test added by this plan makes **zero real API calls** (no OpenAI/Google/Firecrawl/DuckDuckGo/Chroma-embedding calls), matching the existing suite's constraint from `docs/superpowers/plans/2026-07-20-test-suite-plan.md`. Use the `fresh_state` fixture from `tests/conftest.py` wherever `core.state.state` is touched.
- `eval/run_eval.py` is the ONLY piece of this plan that makes real, billed API calls. It is never invoked by `pytest`, `pytest.ini`, or any CI workflow — it's a manual, opt-in script (`python eval/run_eval.py`).
- Only `ragas` is added to `requirements.txt`. No other dependency changes.
- Test/function names and comments are in Turkish, matching the existing codebase's convention.
- `eval/fixtures/buyuk_test_dokumani.txt` is committed to git (it's synthetic test content, not personal data) even though `uploads/*` is gitignored — this keeps the golden set reproducible on a fresh clone. `eval/results/` (generated reports) is gitignored.

---

### Task 1: Orkestratörü native tool-calling'e refactor et

**Files:**
- Modify: `services/orchestrator.py` (imports at top, `gorev_plani_olustur` at lines 83-147)
- Test: `tests/unit/test_orchestrator_tool_calling.py`

**Interfaces:**
- Consumes: `state.llm_default` (or an injected `llm`), `state.rag_manager` (existing), `niyet_kurala_gore` (existing, untouched, same file).
- Produces: `gorev_plani_olustur(soru: str, llm=None, gecmis: str = '') -> list[dict]` (same contract as before — `[{'tool': str, 'soru': str}, ...]`). New module-level Pydantic classes `DB_QUERY`, `RAG`, `SEARCH`, `META`, `GENERAL` in `services/orchestrator.py` (internal use only, not imported elsewhere — verified no other file does `from services.orchestrator import RAG` etc.).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_orchestrator_tool_calling.py`:

```python
"""gorev_plani_olustur'un native tool-calling (bind_tools/tool_calls) davranisini
dogrular. LLM gercekte cagrilmaz; llm.bind_tools(...).invoke(...) zincirini taklit
eden sahte bir nesne kullanilir (gercek LangChain ChatModel'in dondurdugu
AIMessage.tool_calls formatiyla ayni sekle sahip: {'name':..., 'args': {...},
'id':...} sozlukleri)."""
from services.orchestrator import gorev_plani_olustur


class _SahteAracCagrisiYaniti:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ''


class _SahteAracCagrisiLLM:
    def __init__(self, tool_calls):
        self._tool_calls = tool_calls
        self.son_bind_edilen_araclar = None

    def bind_tools(self, tools):
        self.son_bind_edilen_araclar = tools
        return self

    def invoke(self, girdi):
        return _SahteAracCagrisiYaniti(self._tool_calls)


class _SahteRagManager:
    def __init__(self, belgeler):
        self.documents = belgeler


def test_tek_arac_cagrisi_tek_adimlik_plana_donusur(fresh_state):
    fresh_state.rag_manager = _SahteRagManager({'ozgecmis.pdf': {}})
    llm = _SahteAracCagrisiLLM([
        {'name': 'RAG', 'args': {'soru': 'ikinci sayfada ne anlatiliyor'}, 'id': 'call_1'}
    ])
    plan = gorev_plani_olustur('ikinci sayfada ne anlatiliyor', llm, '')
    assert plan == [{'tool': 'RAG', 'soru': 'ikinci sayfada ne anlatiliyor'}]


def test_coklu_arac_cagrisi_coklu_adim_plana_donusur(fresh_state):
    fresh_state.rag_manager = _SahteRagManager({'ozgecmis.pdf': {}})
    llm = _SahteAracCagrisiLLM([
        {'name': 'DB_QUERY', 'args': {'soru': 'ortalama not kac'}, 'id': 'call_1'},
        {'name': 'RAG', 'args': {'soru': 'belgede proje ornegi var mi'}, 'id': 'call_2'},
    ])
    plan = gorev_plani_olustur('Bahsettigim konudaki detaylari ve karsilastirmayi ozetler misin?', llm, '')
    assert plan == [
        {'tool': 'DB_QUERY', 'soru': 'ortalama not kac'},
        {'tool': 'RAG', 'soru': 'belgede proje ornegi var mi'},
    ]


def test_tool_calls_bos_ise_general_a_dusulur(fresh_state):
    fresh_state.rag_manager = None
    llm = _SahteAracCagrisiLLM([])
    plan = gorev_plani_olustur('bugun canim sikkin', llm, '')
    assert plan == [{'tool': 'GENERAL', 'soru': 'bugun canim sikkin'}]


def test_belge_yokken_rag_araci_modele_sunulmaz(fresh_state):
    fresh_state.rag_manager = None
    llm = _SahteAracCagrisiLLM([{'name': 'GENERAL', 'args': {'soru': 'selam'}, 'id': 'call_1'}])
    gorev_plani_olustur('bugun canim sikkin', llm, '')
    sunulan_isimler = [arac.__name__ for arac in llm.son_bind_edilen_araclar]
    assert 'RAG' not in sunulan_isimler


def test_gecersiz_arac_ismi_filtrelenir(fresh_state):
    fresh_state.rag_manager = None
    llm = _SahteAracCagrisiLLM([
        {'name': 'UYDURMA_ARAC', 'args': {'soru': 'x'}, 'id': 'call_1'},
        {'name': 'GENERAL', 'args': {'soru': 'gecerli soru'}, 'id': 'call_2'},
    ])
    plan = gorev_plani_olustur('bugun canim sikkin', llm, '')
    assert plan == [{'tool': 'GENERAL', 'soru': 'gecerli soru'}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_orchestrator_tool_calling.py -v`
Expected: All 5 tests FAIL. The current implementation never calls `.bind_tools(...)` — it calls `llm_invoke_tracked(llm, prompt)` which calls `llm.invoke(prompt)` directly and tries to `json.loads` the (empty, since the fake's `.content == ''`) result, catches the exception, and falls back to `[{'tool': 'GENERAL', 'soru': soru}]` every time. So `test_tek_arac_cagrisi_...`, `test_coklu_arac_cagrisi_...`, and `test_belge_yokken_rag_araci_modele_sunulmaz` (which asserts `son_bind_edilen_araclar` was set — it never gets set) fail with `AssertionError`; `test_tool_calls_bos_ise_general_a_dusulur` happens to pass already (it's a useful regression check to keep).

- [ ] **Step 3: Add the Pydantic tool schemas and refactor `gorev_plani_olustur`**

In `services/orchestrator.py`, replace the top of the file (imports + `GECERLI_ARACLAR`, lines 1-12):

```python
import re

from pydantic import BaseModel, Field

from core.state import state
from core.llm import llm_invoke_tracked, extract_text
from services.text_to_sql import sql_uret_ve_calistir, db_sonuc_formatla

GECERLI_ARACLAR = ['DB_QUERY', 'RAG', 'SEARCH', 'META', 'GENERAL']


class DB_QUERY(BaseModel):
    """Akademik veritabanindaki ogrenci/ders/not/hoca/bolum/proje/danisman/akts/ortalama/harfnotu bilgisi icin kullanilir."""
    soru: str = Field(description='Veritabanina yoneltilecek dogal dil alt-sorusu')


class RAG(BaseModel):
    """Yuklu dosyalardan/belgelerden cevaplanmasi gereken sorular icin kullanilir."""
    soru: str = Field(description='Belgelere yoneltilecek dogal dil alt-sorusu')


class SEARCH(BaseModel):
    """Internette aranmasi gereken guncel veya genel bir bilgi icin kullanilir."""
    soru: str = Field(description='Internette aranacak dogal dil sorusu')


class META(BaseModel):
    """Chatbotun kendi durumu hakkinda soru icin kullanilir (yuklu belge, aktif model vb.)."""
    soru: str = Field(description='Chatbotun durumu hakkindaki soru')


class GENERAL(BaseModel):
    """Genel sohbet, selamlasma, tavsiye veya fikir sorma icin kullanilir."""
    soru: str = Field(description='Genel sohbet mesaji')


_ARAC_SEMALARI = {'DB_QUERY': DB_QUERY, 'RAG': RAG, 'SEARCH': SEARCH, 'META': META, 'GENERAL': GENERAL}
```

(`import json` is removed — it's no longer used anywhere in this file.)

Then replace `gorev_plani_olustur` (the whole function, currently lines 83-147) with:

```python
def gorev_plani_olustur(soru: str, llm=None, gecmis: str = '') -> list:
    """
    Kullanicinin sorusunu bir veya daha fazla {'tool','soru'} adimindan olusan
    bir gorev listesine (to-do list) donusturur. Cogu soru tek adimlik cikar;
    LLM sadece kural tabanli tespit basarisiz oldugunda ve gerektiginde birden
    fazla adim onerir. Plan, modelin native tool-calling mekanizmasi (bind_tools +
    response.tool_calls) ile cikartilir; araclar gercekte cagrilmaz, sadece
    structured cikti semasi olarak kullanilir.
    """
    llm = llm or state.llm_default

    kural_sonucu = niyet_kurala_gore(soru)
    if kural_sonucu:
        return [{'tool': kural_sonucu, 'soru': soru}]

    has_docs = bool(state.rag_manager and state.rag_manager.documents)
    doc_names = list(state.rag_manager.documents.keys()) if has_docs else []
    doc_info = f"(Yuklu Dosyalar: {doc_names})" if has_docs else "(Dosya yok)"

    arac_isimleri = [ad for ad in GECERLI_ARACLAR if ad != 'RAG' or has_docs]
    semalar = [_ARAC_SEMALARI[ad] for ad in arac_isimleri]

    prompt = f"""Asagidaki soruyu cevaplamak icin uygun arac(lar)i cagir (en fazla 3).
Sorularin buyuk cogunlugu TEK bir aracla cevaplanir, o yuzden varsayilan olarak
tek bir arac cagir. Sadece soru acikca birden fazla FARKLI kaynaktan bilgi
istiyorsa (ornek: hem bir ogrencinin notunu hem de yuklu bir belgedeki proje
ornegini istemek) birden fazla arac cagir.

{doc_info}

ONEMLI: Soru "isimleri", "adlari", "onlar", "bunlar", "kac tane", "detaylari",
"o kisi", "ayni" gibi onceki konusmaya atifta bulunan ifadeler iceriyorsa,
onceki konusmanin baglamini kullan.

Onceki konusma (baglam icin kullan):
{gecmis or 'Yok'}

Soru: "{soru}\""""

    try:
        yanit = llm.bind_tools(semalar).invoke(prompt)
        tool_calls = list(getattr(yanit, 'tool_calls', None) or [])

        gecerli_adimlar = []
        for cagri in tool_calls[:3]:
            tool = str(cagri.get('name', '')).upper()
            args = cagri.get('args') or {}
            alt_soru = str(args.get('soru') or soru)
            if tool not in arac_isimleri:
                continue
            gecerli_adimlar.append({'tool': tool, 'soru': alt_soru})

        if gecerli_adimlar:
            return gecerli_adimlar
    except Exception:
        pass

    return [{'tool': 'GENERAL', 'soru': soru}]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_orchestrator_tool_calling.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: All previously-passing tests (including `tests/unit/test_orchestrator_rules.py` and `tests/integration/test_chat_flow.py`, which mocks `gorev_plani_olustur` wholesale and is therefore unaffected by this internal change) still PASS.

- [ ] **Step 6: Commit**

```bash
git add services/orchestrator.py tests/unit/test_orchestrator_tool_calling.py
git commit -m "refactor: orkestratör planlamasını native tool-calling'e geçir"
```

---

### Task 2: RagManager'dan LLM-cagrisiz bir retrieve() metodu cikart

**Files:**
- Modify: `services/rag.py` (`RagManager.ask_all`, lines 85-139)
- Test: `tests/unit/test_rag_retrieve.py`

**Interfaces:**
- Consumes: `RagManager.documents` (existing dict), module constants `SIMILARITY_THRESHOLD`, `FALLBACK_THRESHOLD`, `MAX_TOTAL_CHUNKS`, `_k_per_doc()` (all existing, unchanged).
- Produces: `RagManager.retrieve(self, question: str) -> list | None` — returns the same `list[Document]` (LangChain document chunks, threshold-then-fallback logic identical to today) that `ask_all` used to build inline, or `None` if there are no documents or nothing matches. Needed by Task 4's eval harness to capture RAGAS `retrieved_contexts`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rag_retrieve.py`:

```python
"""RagManager.retrieve()'in ask_all'dan bagimsiz calisabildigini ve threshold
fallback davranisini korudugunu dogrular. Gercek Chroma/embedding kullanilmaz,
vector_store sahte bir nesneyle taklit edilir."""
from services.rag import RagManager


class _SahteDocument:
    def __init__(self, icerik, kaynak=None):
        self.page_content = icerik
        self.metadata = {'source': kaynak} if kaynak else {}


class _SahteRetriever:
    def __init__(self, sonuclar):
        self._sonuclar = sonuclar

    def invoke(self, soru):
        return self._sonuclar


class _SahteVectorStore:
    def __init__(self, sonuclar):
        self._sonuclar = sonuclar
        self.son_search_kwargs = None

    def as_retriever(self, search_type, search_kwargs):
        self.son_search_kwargs = search_kwargs
        return _SahteRetriever(self._sonuclar)


def test_belge_yokken_none_doner():
    rm = RagManager()
    assert rm.retrieve('herhangi bir soru') is None


def test_esik_ustunde_sonuc_varsa_direkt_doner():
    rm = RagManager()
    sonuclar = [_SahteDocument('icerik 1'), _SahteDocument('icerik 2')]
    vs = _SahteVectorStore(sonuclar)
    rm.documents = {'belge.txt': {'vector_store': vs}}

    sonuc = rm.retrieve('soru')

    assert len(sonuc) == 2
    assert vs.son_search_kwargs['score_threshold'] == 0.45


def test_esik_ustunde_sonuc_yoksa_fallback_esigine_duser():
    class _KademeliVectorStore:
        def __init__(self):
            self.cagri_sayisi = 0
            self.son_search_kwargs = None

        def as_retriever(self, search_type, search_kwargs):
            self.son_search_kwargs = search_kwargs
            self.cagri_sayisi += 1
            sonuc = [] if self.cagri_sayisi == 1 else [_SahteDocument('fallback icerik')]
            return _SahteRetriever(sonuc)

    rm = RagManager()
    vs = _KademeliVectorStore()
    rm.documents = {'belge.txt': {'vector_store': vs}}

    sonuc = rm.retrieve('soru')

    assert len(sonuc) == 1
    assert sonuc[0].page_content == 'fallback icerik'
    assert vs.son_search_kwargs['score_threshold'] == 0.1


def test_source_metadata_doc_name_ile_doldurulur():
    rm = RagManager()
    vs = _SahteVectorStore([_SahteDocument('icerik')])
    rm.documents = {'ozel_belge.pdf': {'vector_store': vs}}

    sonuc = rm.retrieve('soru')

    assert sonuc[0].metadata['source'] == 'ozel_belge.pdf'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_rag_retrieve.py -v`
Expected: All 4 tests FAIL with `AttributeError: 'RagManager' object has no attribute 'retrieve'`.

- [ ] **Step 3: Extract `retrieve()` and slim down `ask_all()`**

In `services/rag.py`, replace `RagManager.ask_all` (lines 85-139) with:

```python
    def retrieve(self, question: str):
        """
        Soruya en alakali chunk'lari (LangChain Document listesi) dondurur, LLM
        cagirmaz. Once SIMILARITY_THRESHOLD/k ile, sonuc yoksa FALLBACK_THRESHOLD/2
        ile dener. Belge yoksa veya hicbir chunk eslesmezse None doner.
        """
        if not self.documents:
            return None

        n_docs = len(self.documents)
        k = _k_per_doc(n_docs)

        def _fetch(threshold, k_val):
            results = []
            for doc_name, doc_data in self.documents.items():
                retriever = doc_data['vector_store'].as_retriever(
                    search_type='similarity_score_threshold',
                    search_kwargs={'score_threshold': threshold, 'k': k_val}
                )
                try:
                    docs = retriever.invoke(question)
                    for d in docs:
                        d.metadata.setdefault('source', doc_name)
                    results.extend(docs)
                except:
                    pass
            return results

        all_docs = _fetch(SIMILARITY_THRESHOLD, k)
        if not all_docs:
            all_docs = _fetch(FALLBACK_THRESHOLD, 2)
        if not all_docs:
            return None

        return all_docs[:MAX_TOTAL_CHUNKS]

    def ask_all(self, question: str, llm=None):
        llm = llm or state.llm_default
        sorted_docs = self.retrieve(question)
        if not sorted_docs:
            return None

        source_counts = {}
        for d in sorted_docs:
            src = d.metadata.get('source', 'Bilinmeyen')
            source_counts[src] = source_counts.get(src, 0) + 1

        context_parts = [
            f'--- [KAYNAK: {d.metadata.get("source", "Belge")}] ---\n{d.page_content}'
            for d in sorted_docs
        ]
        context = '\n\n'.join(context_parts)

        system_msg = (
            'Sen yardımcı bir belge analiz asistanısın. YÜKLENEN BELGELERİ kullanarak soruları yanıtla. '
            'Eğer kullanıcı belgelerdeki bilgilere dayanarak bir analiz, puanlama, değerlendirme veya karşılaştırma '
            'yapmanı isterse (örneğin "sen puanla", "puanla" gibi), bunu belgedeki nitel verilere göre kendi '
            'oluşturacağın mantıklı kriterlerle/puanlama ölçeğiyle yap ve detaylandır. '
            'Eğer belgede ilgili hiçbir bilgi yoksa bunu belirt.'
        )
        cevap = extract_text(llm_invoke_tracked(llm, [
            ('system', system_msg),
            ('human', f'Belgeler:\n{context}\n\nSoru: {question}')
        ]))
        kaynak = list(source_counts.keys())[0] if len(source_counts) == 1 else f'{len(source_counts)} belge'
        return cevap, kaynak
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_rag_retrieve.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: All tests still PASS (no existing test references `RagManager.ask_all`'s internals directly, confirmed by searching `tests/` for `RagManager|ask_all|rag_manager` beforehand).

- [ ] **Step 6: Commit**

```bash
git add services/rag.py tests/unit/test_rag_retrieve.py
git commit -m "refactor: RagManager'dan LLM-cagrisiz bir retrieve() metodu cikar"
```

---

### Task 3: Golden set veri seti ve semasi

**Files:**
- Create: `eval/__init__.py`
- Create: `eval/golden_set.json`
- Create: `eval/fixtures/buyuk_test_dokumani.txt` (copy of `uploads/buyuk_test_dokumani.txt`)
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Test: `tests/unit/test_eval_golden_set.py`

**Interfaces:**
- Produces: `eval/golden_set.json` — a JSON list of records, each `{"id": str, "category": "DB_QUERY"|"RAG"|"GENERAL"|"META", "soru": str, "ground_truth": str|null, "kaynak_dosya": str (RAG only)}`. Consumed by Task 4's `eval/run_eval.py`.

- [ ] **Step 1: Write the failing schema test**

Create `tests/unit/test_eval_golden_set.py`:

```python
"""eval/golden_set.json dosyasinin yapisal butunlugunu dogrular. API cagrisi
yapmaz, sadece JSON semasini kontrol eder (run_eval.py'nin kullandigi veri
kaynagi)."""
import json
from pathlib import Path

GOLDEN_SET_YOLU = Path(__file__).resolve().parents[2] / 'eval' / 'golden_set.json'
GECERLI_KATEGORILER = {'DB_QUERY', 'RAG', 'GENERAL', 'META', 'SEARCH'}


def _golden_set_yukle():
    with open(GOLDEN_SET_YOLU, encoding='utf-8') as f:
        return json.load(f)


def test_golden_set_dosyasi_gecerli_json_listesidir():
    veri = _golden_set_yukle()
    assert isinstance(veri, list)
    assert len(veri) > 0


def test_her_kayit_zorunlu_alanlari_icerir():
    veri = _golden_set_yukle()
    for kayit in veri:
        assert 'id' in kayit and kayit['id']
        assert 'category' in kayit
        assert 'soru' in kayit and kayit['soru']
        assert 'ground_truth' in kayit


def test_kategoriler_gecerli_degerlerden_biridir():
    veri = _golden_set_yukle()
    for kayit in veri:
        assert kayit['category'] in GECERLI_KATEGORILER


def test_id_alanlari_essizdir():
    veri = _golden_set_yukle()
    idler = [kayit['id'] for kayit in veri]
    assert len(idler) == len(set(idler))


def test_db_query_ve_rag_kayitlarinin_ground_truth_u_bos_olamaz():
    veri = _golden_set_yukle()
    for kayit in veri:
        if kayit['category'] in ('DB_QUERY', 'RAG'):
            assert kayit['ground_truth'], f"{kayit['id']} icin ground_truth bos olamaz"


def test_rag_kayitlarinin_kaynak_dosyasi_belirtilmis_olmalidir():
    veri = _golden_set_yukle()
    for kayit in veri:
        if kayit['category'] == 'RAG':
            assert kayit.get('kaynak_dosya'), f"{kayit['id']} icin kaynak_dosya belirtilmeli"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_eval_golden_set.py -v`
Expected: FAIL with `FileNotFoundError` (`eval/golden_set.json` doesn't exist yet).

- [ ] **Step 3: Create the `eval` package and fixture document**

```bash
mkdir -p eval/fixtures eval/results
touch eval/__init__.py
cp "uploads/buyuk_test_dokumani.txt" "eval/fixtures/buyuk_test_dokumani.txt"
```

(On Windows PowerShell: `New-Item -ItemType Directory -Force eval/fixtures, eval/results; New-Item -ItemType File -Force eval/__init__.py; Copy-Item "uploads/buyuk_test_dokumani.txt" "eval/fixtures/buyuk_test_dokumani.txt"`)

- [ ] **Step 4: Create `eval/golden_set.json`**

The `DB_QUERY` answers below are computed directly from the seed data in `core/database.py` (verified by hand against the `ogrenciler`/`dersler`/`bolumler` seed rows). The `RAG` answers are grounded in `eval/fixtures/buyuk_test_dokumani.txt`, which has exactly 15 `BOLUM N: <konu>` section headers.

```json
[
  {
    "id": "db-001",
    "category": "DB_QUERY",
    "soru": "Bilgisayar Mühendisliği bölümünde kaç öğrenci var?",
    "ground_truth": "6"
  },
  {
    "id": "db-002",
    "category": "DB_QUERY",
    "soru": "Yapay Zeka Mühendisliği bölümünde kaç öğrenci var?",
    "ground_truth": "5"
  },
  {
    "id": "db-003",
    "category": "DB_QUERY",
    "soru": "Ahmet Yılmaz hocanın hangi dersleri var?",
    "ground_truth": "Yapay Zeka, Veritabanı Yönetim Sistemleri"
  },
  {
    "id": "db-004",
    "category": "DB_QUERY",
    "soru": "Ahmet Yılmaz hocanın danışmanlığındaki öğrenciler kimlerdir?",
    "ground_truth": "Ali Kaya, Emre Çelik, Pınar Bulut"
  },
  {
    "id": "db-005",
    "category": "DB_QUERY",
    "soru": "Okulda toplam kaç öğrenci var?",
    "ground_truth": "25"
  },
  {
    "id": "rag-001",
    "category": "RAG",
    "soru": "Bu belgede toplam kaç ana bölüm (BOLUM) var?",
    "ground_truth": "15",
    "kaynak_dosya": "buyuk_test_dokumani.txt"
  },
  {
    "id": "rag-002",
    "category": "RAG",
    "soru": "Bu belgenin 1. bölümünün konusu nedir?",
    "ground_truth": "Yapay Zeka ve Makine Öğrenmesi",
    "kaynak_dosya": "buyuk_test_dokumani.txt"
  },
  {
    "id": "rag-003",
    "category": "RAG",
    "soru": "Bu belgenin 12. bölümünün konusu nedir?",
    "ground_truth": "Doğal Dil İşleme",
    "kaynak_dosya": "buyuk_test_dokumani.txt"
  },
  {
    "id": "rag-004",
    "category": "RAG",
    "soru": "Bu belgede Siber Güvenlik konusu kaçıncı bölümde işleniyor?",
    "ground_truth": "9. bölüm",
    "kaynak_dosya": "buyuk_test_dokumani.txt"
  },
  {
    "id": "rag-005",
    "category": "RAG",
    "soru": "Bu belgenin son (15.) bölümünün konusu nedir?",
    "ground_truth": "Gömülü Sistemler",
    "kaynak_dosya": "buyuk_test_dokumani.txt"
  },
  {
    "id": "meta-001",
    "category": "META",
    "soru": "Şu an hangi model aktif?",
    "ground_truth": null
  },
  {
    "id": "general-001",
    "category": "GENERAL",
    "soru": "Merhaba, bugün nasılsın?",
    "ground_truth": null
  }
]
```

- [ ] **Step 5: Add `ragas` to `requirements.txt` and install it**

Append to `requirements.txt`:

```
ragas>=0.2.0
```

Run: `pip install -r requirements.txt`
Expected: `ragas` and its dependencies install without dependency-resolution errors against the already-pinned `langchain>=0.2.0` family. If pip reports a conflict, note the exact conflicting package/version pair before proceeding — this plan assumes a clean install.

- [ ] **Step 6: Add `eval/results/` to `.gitignore`**

In `.gitignore`, append:

```
# eval harness reports (generated, timestamped)
eval/results/*
!eval/results/.gitkeep
```

Then:

```bash
touch eval/results/.gitkeep
```

(PowerShell: `New-Item -ItemType File -Force eval/results/.gitkeep`)

- [ ] **Step 7: Run the schema test to verify it passes**

Run: `pytest tests/unit/test_eval_golden_set.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 8: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: All tests still PASS (this task only adds new files; nothing existing was modified except `requirements.txt`/`.gitignore`, which pytest doesn't read).

- [ ] **Step 9: Commit**

```bash
git add eval/__init__.py eval/golden_set.json eval/fixtures/buyuk_test_dokumani.txt eval/results/.gitkeep requirements.txt .gitignore tests/unit/test_eval_golden_set.py
git commit -m "feat: RAGAS eval harness icin golden set ve fixture verisi ekle"
```

---

### Task 4: run_eval.py betiği ve README dokümantasyonu

**Files:**
- Create: `eval/run_eval.py`
- Modify: `README.md`
- Test: `tests/unit/test_eval_scoring.py`

**Interfaces:**
- Consumes: `RagManager.retrieve()` (Task 2), `eval/golden_set.json` (Task 3), `services/chat.py::chat_yanit_uret` (existing, unchanged), `services/conversations.py::_new_conv` (existing, unchanged), `core/llm.py::_calculate_cost` (existing, unchanged).
- Produces: `eval/run_eval.py::db_query_dogruluk_skoru(cevap: str, ground_truth: str) -> float` (pure function, testable offline) and `eval/run_eval.py::calistir()` (the script's entry point, makes real API calls — not covered by pytest).

- [ ] **Step 1: Write the failing test for the pure scoring function**

Create `tests/unit/test_eval_scoring.py`:

```python
"""eval/run_eval.py icindeki db_query_dogruluk_skoru fonksiyonunun saf mantiginin
testi. API cagrisi yapmaz."""
from eval.run_eval import db_query_dogruluk_skoru


def test_tam_eslesme_1_0_skoru_verir():
    assert db_query_dogruluk_skoru('Cevap: 6', '6') == 1.0


def test_coklu_parca_kismi_eslesme():
    cevap = 'Ali Kaya ve Emre Çelik bulundu'
    ground_truth = 'ali kaya, emre çelik, pınar bulut'
    skor = db_query_dogruluk_skoru(cevap, ground_truth)
    assert round(skor, 2) == round(2 / 3, 2)


def test_hic_eslesme_yoksa_0_doner():
    assert db_query_dogruluk_skoru('alakasiz cevap', '42') == 0.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_eval_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.run_eval'` (the file doesn't exist yet).

- [ ] **Step 3: Create `eval/run_eval.py`**

```python
"""RAGAS tabanli LLM eval harness'inin calistirilabilir betigi.

Bu betik GERCEK OpenAI API cagrilari yapar (hem chatbot pipeline'i hem RAGAS'in
kendi degerlendirme metrikleri icin) ve UCRETLIDIR. pytest suite'inin bir
parcasi DEGILDIR, CI'da otomatik calismaz — elle `python eval/run_eval.py` ile
calistirilir. OPENAI_API_KEY .env dosyasindan okunur.
"""
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from core.lazy_imports import ensure_imports
from core.state import state
from core.llm import _calculate_cost
from services.chat import chat_yanit_uret
from services.conversations import _new_conv

GOLDEN_SET_YOLU = Path(__file__).resolve().parent / 'golden_set.json'
SONUC_KLASORU = Path(__file__).resolve().parent / 'results'
TEST_BELGESI = str(Path(__file__).resolve().parent / 'fixtures' / 'buyuk_test_dokumani.txt')

TAHMINI_TOKEN_PER_CAGRI = 800  # kaba tahmin: prompt + context + cevap ortalamasi


def db_query_dogruluk_skoru(cevap: str, ground_truth: str) -> float:
    """Ground truth'taki virgulle ayrilmis her bir parcanin cevapta gecip
    gecmedigini kontrol eden basit bir eslesme orani (RAGAS'in context
    metrikleri SQL retrieval'a uymadigi icin DB_QUERY sorularinda bilerek
    RAGAS kullanilmiyor, dogrudan metin eslesmesi kullaniliyor)."""
    cevap_norm = cevap.lower()
    parcalar = [p.strip().lower() for p in ground_truth.split(',') if p.strip()]
    if not parcalar:
        return 0.0
    eslesen = sum(1 for p in parcalar if p in cevap_norm)
    return eslesen / len(parcalar)


def maliyet_tahmini_yazdir(golden_set):
    db_query_sayisi = sum(1 for k in golden_set if k['category'] == 'DB_QUERY')
    rag_sayisi = sum(1 for k in golden_set if k['category'] == 'RAG')
    diger_sayisi = len(golden_set) - db_query_sayisi - rag_sayisi

    # Pipeline cagrilari: DB_QUERY sorulari SQL uretimi + cevap formatlama icin ~2
    # cagri yapar, RAG/GENERAL/META sorulari ~1 cagri yapar.
    pipeline_cagri = db_query_sayisi * 2 + rag_sayisi * 1 + diger_sayisi * 1
    # RAGAS metrikleri (faithfulness, answer_relevancy, context_precision,
    # context_recall) RAG sorusu basina yaklasik 4 ek LLM cagrisi yapar.
    ragas_cagri = rag_sayisi * 4
    toplam_cagri = pipeline_cagri + ragas_cagri
    toplam_token_tahmini = toplam_cagri * TAHMINI_TOKEN_PER_CAGRI
    tahmini_maliyet = _calculate_cost('gpt-4o-mini', toplam_token_tahmini)

    print(
        f'Kaba maliyet tahmini: {toplam_cagri} LLM cagrisi, ~{toplam_token_tahmini} token, '
        f'~${tahmini_maliyet:.4f} (gpt-4o-mini fiyatlandirmasiyla, ortalama '
        f'{TAHMINI_TOKEN_PER_CAGRI} token/cagri varsayimiyla). Gercek maliyet bundan '
        f'sapabilir; kesin rakam icin calistirdiktan sonraki "Gercek maliyet" satirina bakin.\n'
    )


def rag_ornekleri_hazirla(golden_set, conv_id):
    """RAG kategorisindeki her soru icin (soru, cevap, retrieved_contexts,
    ground_truth) toplar. RagManager.retrieve() LLM cagirmadan sadece ilgili
    chunk'lari dondurur; chat_yanit_uret ise tam pipeline'i (context + LLM
    cevabi) calistirir."""
    ornekler = []
    for kayit in golden_set:
        if kayit['category'] != 'RAG':
            continue
        chunklar = state.rag_manager.retrieve(kayit['soru']) or []
        sonuc = chat_yanit_uret(kayit['soru'], conv_id, model_name='chatgpt')
        ornekler.append({
            'id': kayit['id'],
            'user_input': kayit['soru'],
            'response': sonuc['cevap'],
            'retrieved_contexts': [c.page_content for c in chunklar] or [''],
            'reference': kayit['ground_truth'],
        })
    return ornekler


def rag_ornekleri_skorla(ornekler):
    """RAGAS'in evaluate() API'siyle RAG orneklerini skorlar.
    NOT: ragas'in Dataset/kolon semasi surumler arasi degisti (0.1.x'te
    question/answer/contexts/ground_truth, 0.2.x+'te user_input/response/
    retrieved_contexts/reference). Bu kod requirements.txt'teki ragas>=0.2.0
    icin yazildi — kurulan surum farkli davranirsa `python -c "import ragas;
    help(ragas.evaluate)"` ile gercek imzayi kontrol edin ve asagidaki
    EvaluationDataset.from_list cagrisindaki kolon isimlerini ona gore
    guncelleyin."""
    if not ornekler:
        return None

    from ragas import evaluate, EvaluationDataset
    from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    dataset = EvaluationDataset.from_list([
        {k: v for k, v in o.items() if k != 'id'} for o in ornekler
    ])
    degerlendirici_llm = LangchainLLMWrapper(state.llm_default)
    degerlendirici_embedding = LangchainEmbeddingsWrapper(state.embedding_model)

    sonuc = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=degerlendirici_llm,
        embeddings=degerlendirici_embedding,
    )
    df = sonuc.to_pandas()
    df.insert(0, 'id', [o['id'] for o in ornekler])
    return df


def calistir():
    golden_set = json.loads(GOLDEN_SET_YOLU.read_text(encoding='utf-8'))
    maliyet_tahmini_yazdir(golden_set)

    ensure_imports()
    state.rag_manager.add_document(TEST_BELGESI)
    conv_id = _new_conv('Eval')

    tokens_once = state.global_tokens
    cost_once = state.global_cost_usd

    db_sonuclari = []
    for kayit in golden_set:
        if kayit['category'] != 'DB_QUERY':
            continue
        cevap = chat_yanit_uret(kayit['soru'], conv_id, model_name='chatgpt')['cevap']
        skor = db_query_dogruluk_skoru(cevap, kayit['ground_truth'])
        db_sonuclari.append({
            'id': kayit['id'], 'soru': kayit['soru'], 'cevap': cevap,
            'ground_truth': kayit['ground_truth'], 'skor': skor,
        })

    diger_sonuclari = []
    for kayit in golden_set:
        if kayit['category'] not in ('GENERAL', 'META', 'SEARCH'):
            continue
        cevap = chat_yanit_uret(kayit['soru'], conv_id, model_name='chatgpt')['cevap']
        diger_sonuclari.append({'id': kayit['id'], 'soru': kayit['soru'], 'cevap': cevap})

    rag_ornekleri = rag_ornekleri_hazirla(golden_set, conv_id)
    rag_df = rag_ornekleri_skorla(rag_ornekleri)

    gercek_maliyet = state.global_cost_usd - cost_once
    gercek_token = state.global_tokens - tokens_once

    print('=== DB_QUERY sonuclari (exact/fuzzy match) ===')
    for r in db_sonuclari:
        print(f"[{r['skor']:.2f}] {r['id']}: {r['soru']}")
    ortalama_db_skoru = (sum(r['skor'] for r in db_sonuclari) / len(db_sonuclari)) if db_sonuclari else 0.0
    print(f'Ortalama DB_QUERY skoru: {ortalama_db_skoru:.2f}\n')

    if rag_df is not None and len(rag_df):
        print('=== RAG sonuclari (RAGAS) ===')
        print(rag_df.to_string(index=False))
        print()

    print(f'Gercek maliyet: ${gercek_maliyet:.5f} ({gercek_token} token)')

    SONUC_KLASORU.mkdir(exist_ok=True)
    zaman_damgasi = datetime.now().strftime('%Y%m%d_%H%M%S')
    rapor = {
        'tarih': zaman_damgasi,
        'gercek_maliyet_usd': gercek_maliyet,
        'gercek_token': gercek_token,
        'db_query_sonuclari': db_sonuclari,
        'db_query_ortalama_skor': ortalama_db_skoru,
        'diger_sonuclari': diger_sonuclari,
        'rag_sonuclari': rag_df.to_dict(orient='records') if rag_df is not None and len(rag_df) else [],
    }
    rapor_yolu = SONUC_KLASORU / f'eval_{zaman_damgasi}.json'
    rapor_yolu.write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Rapor kaydedildi: {rapor_yolu}')


if __name__ == '__main__':
    calistir()
```

- [ ] **Step 4: Run the pure-function test to verify it passes**

Run: `pytest tests/unit/test_eval_scoring.py -v`
Expected: All 3 tests PASS. (Importing `eval.run_eval` at module load time pulls in `core.lazy_imports`, `core.state`, etc., which is fine — none of that executes network calls at import time, only inside `calistir()`.)

- [ ] **Step 5: Run the full existing suite to confirm no regressions**

Run: `pytest -v`
Expected: All tests still PASS.

- [ ] **Step 6: Add the "Eval Harness" section to `README.md`**

Insert a new section right after the existing `## API Notları` section (before `## Lisans`):

```markdown
## Eval Harness

`eval/` klasörü, pytest'ten ayrı, gerçek API çağrısı yapan ve ücretli bir
cevap-kalitesi değerlendirme aracı içerir. `tests/` klasöründeki pytest suite'i
kod doğruluğunu (mock'lu, sıfır maliyet) ölçer; `eval/run_eval.py` ise gerçek
modelin gerçek cevap kalitesini ölçer.

### Çalıştırma

```bash
python eval/run_eval.py
```

Çalıştırmadan önce konsola tahmini LLM çağrı sayısı ve dolar maliyeti
yazdırılır. `OPENAI_API_KEY` gereklidir (`.env` dosyasından okunur).

### Ne ölçer

- **DB_QUERY soruları:** `eval/golden_set.json`'daki beklenen değerlerin
  cevapta geçip geçmediğine bakan basit bir eşleşme skoru (0-1 arası).
- **RAG soruları:** [RAGAS](https://github.com/explodinggradients/ragas) ile
  `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`
  metrikleri.
- **GENERAL/META soruları:** Sadece üretilen cevap raporda gösterilir,
  otomatik skorlanmaz (açık uçlu sorular için sabit bir "doğru cevap" yok).

### Ne ölçmez

- Text-to-SQL'in ürettiği SQL'in kendisini değil, sadece nihai doğal dil
  cevabı değerlendirir.
- Orkestratörün doğru aracı seçip seçmediğini (intent routing doğruluğunu)
  ölçmez — bu, `tests/unit/test_orchestrator_rules.py`'nin kapsamındadır.
- Sonuçlar `eval/results/` altına tarih damgalı JSON olarak kaydedilir (git'e
  eklenmez).
```

- [ ] **Step 7: Manual smoke test (not pytest — requires a real `OPENAI_API_KEY`)**

Run: `python eval/run_eval.py`
Expected: Console prints the cost estimate, then runs each golden-set question through the real pipeline, prints DB_QUERY scores and the RAGAS results table, prints the real cost, and writes `eval/results/eval_<timestamp>.json`. If `ragas.evaluate(...)` raises a `TypeError` about unexpected keyword arguments or `EvaluationDataset`/column names, check the installed `ragas` version (`pip show ragas`) against its changelog and adjust the column names in `rag_ornekleri_hazirla`/`rag_ornekleri_skorla` accordingly — this is the one part of the script whose exact call signature depends on the installed library version.

- [ ] **Step 8: Commit**

```bash
git add eval/run_eval.py tests/unit/test_eval_scoring.py README.md
git commit -m "feat: RAGAS tabanli run_eval.py betigi ve Eval Harness README bolumu ekle"
```
