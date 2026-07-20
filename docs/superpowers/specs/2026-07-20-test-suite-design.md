# Test Suite Design

**Context:** Proje mimari değerlendirmesinde (2026-07-20) iki ana zayıflık tespit edildi: sıfır test kapsamı ve `core/state.py::AppState` global mutable singleton'ının test edilemezliği. Bu spec, ikisinden ilkini — test suite kurulumunu — kapsar. AppState'i dependency injection'a çevirmek (2. adım) bu suite'in yeşil olmasına bağlı; testsiz bir refactor'ün davranış değişikliği yaratmadığını doğrulamanın yolu yok.

**Goal:** Projeye, gerçek API çağrısı yapmayan, hızlı ve deterministik bir pytest suite'i eklemek — önce saf mantık (kural tabanlı, LLM'siz) fonksiyonları, sonra mock'lu LLM ile orkestrasyon akışını, son olarak GitHub Actions ile otomatik çalıştırmayı kapsayacak şekilde.

**Architecture:** `pytest` + `pytest-mock`, `tests/unit/` (saf fonksiyonlar, mock yok) ve `tests/integration/` (mock'lu LLM + Flask test client) olarak ikiye ayrılır. `tests/conftest.py` ortak fixture'ları barındırır: her testten önce/sonra `core.state.state`'i temiz bir `AppState()` ile değiştiren `fresh_state` fixture'ı (global singleton test izolasyonu için gerekli) ve `_setup_database`'i geçici bir SQLite dosyasına yönlendiren `test_db` fixture'ı.

**Tech Stack:** pytest, pytest-mock, Flask test client (mevcut `flask` bağımlılığının parçası), GitHub Actions (CI).

## Global Constraints

- Gerçek OpenAI/Google/Firecrawl/DuckDuckGo API çağrısı yapan hiçbir test yazılmayacak — tüm LLM çağrıları mock'lanır.
- HuggingFace embedding modeli indirip yükleyen testler yazılmayacak (yavaş, ~1.5GB) — `RagManager`'ın embedding-bağımlı kısımları (chunking hariç) kapsam dışı.
- Her test bağımsız çalışabilmeli — `fresh_state` fixture'ı olmadan hiçbir test `core.state.state`'e dokunmamalı.
- `requirements.txt`'e sadece `pytest` ve `pytest-mock` eklenir, mevcut bağımlılıklar değişmez.
- CI workflow'u sadece `pytest` çalıştırır, deploy/publish adımı içermez.

---

## Kapsam (Test Edilecekler)

### 1. Saf mantık (unit, mock gerektirmez)

| Dosya | Fonksiyon | Neyi doğrular |
|---|---|---|
| `tests/unit/test_guardrails.py` | `girdi_guvenli_mi` | Injection kalıpları reddedilir; META soruları yanlış pozitif vermez; 4000 karakter sınırı |
| `tests/unit/test_guardrails.py` | `cikti_guvenli_mi` | `sk-...`/`AIzaSy...`/`fc-...`/`X_API_KEY=...` desenleri redakte edilir |
| `tests/unit/test_gap_analysis.py` | `cevap_eksik_mi` | Boş DB_QUERY/RAG sonucu tespit edilir; META/GENERAL/SEARCH sonuçları görmezden gelinir |
| `tests/unit/test_orchestrator_rules.py` | `niyet_kurala_gore` | Kural eşleşmesi doğru araca yönlendirir; yüklü belge adı geçen sorularda fast-path atlanır (daha önce bulunan "hoca" bug'ının regresyon testi) |
| `tests/unit/test_text_to_sql.py` | `sql_temizle` | Markdown code fence/backtick temizliği doğru çalışır |

### 2. Mock'lu orkestrasyon (integration)

| Dosya | Kapsam | Neyi doğrular |
|---|---|---|
| `tests/integration/test_chat_flow.py` | `_chat_akisi` / `chat_yanit_uret` | `adim_calistir` ve `llm_invoke_tracked` mock'lanır; tek adımlı ve çok adımlı plan senaryoları, gap-analysis fallback tetiklenmesi, guardrail erken reddi |
| `tests/integration/test_routes.py` | Flask test client | `/api/chat` mock'lu servis katmanıyla 200 döner; boş mesaj 400 döner; `/api/stats` beklenen alanları içerir |

### 3. CI

- `.github/workflows/tests.yml`: `push` ve `pull_request` tetikleyicisiyle `pip install -r requirements.txt`, `pip install pytest pytest-mock`, `pytest` çalıştırır.

## Kapsam Dışı

- Gerçek embedding modeli / Chroma vektör araması testleri
- Gerçek LLM çağrısı yapan uçtan uca testler
- Frontend/JS testleri
- Yük/performans testleri
- CI'a deploy/publish adımı ekleme

## Başarı Kriteri

`pytest` komutu proje kökünde sıfır hatayla, harici API çağrısı yapmadan, birkaç saniye içinde tamamlanır. `.github/workflows/tests.yml` her push'ta otomatik çalışır.
