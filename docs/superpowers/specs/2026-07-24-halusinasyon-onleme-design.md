# Halüsinasyon Önleme

**Context:** Canlı testte gözlenen ciddi bir hata: kullanıcı yüklü olmayan (RAG hiç devrede değil) CV'ler hakkında soru sordu, orkestratör 3 kez `DB_QUERY` denedi (hepsi "kayıt bulunamadı"), `gap_analysis.py::boslugu_kapat` bir `SEARCH` adımı ekledi (o da alakasız/zayıf sonuç döndü), ve `services/orchestrator.py::sonuclari_birlestir` bu boş/alakasız parçalardan **tamamen uydurma bir hikaye** kurdu (CV'lerde olmayan kişiler arası gizli ilişkiler). Ayrı bir örnekte "egemen nerde" sorusu "Egemen Bozca" (kişi) yerine "Bozcaada" (yer) ile karıştırılıp emin bir tavırla alakasız coğrafi bilgi döndürüldü. Kök sebep: hiçbir yerde "kaynaklarda gerçek bilgi yoksa/alakasızsa uydurma" kuralı yok.

**Goal:** İki katmanlı savunma: (1) çok adımlı bir planda TÜM alt-sonuçlar "bilgi bulunamadı" ise, LLM'e hiç gitmeden (`sonuclari_birlestir` çağrılmadan) dürüst, sabit bir mesaj dön — bu, gözlenen ana hatayı deterministik ve sıfır ek maliyetle tamamen ortadan kaldırır. (2) Sonuçlar boş değil ama alakasız/zayıfsa (ör. yanlış kişi/yer eşleşmesi), `sonuclari_birlestir` ve `internet_arama_yap` prompt'larına "ilgisiz/zayıf kanıttan emin cevap uydurma" talimatı ekle — bu katman kesin garanti vermez (LLM davranışına dayanır) ama riski azaltır.

**Architecture:** Katman 1 için `services/gap_analysis.py`'ye yeni bir saf fonksiyon: `tum_sonuclar_eksik_mi(sonuclar) -> bool` (mevcut `EKSIK_BILGI_IFADELERI` listesini, ama TÜM araçlara — sadece `BILGI_ARAYAN_ARACLAR` değil — uygulayarak). `services/chat.py::_chat_akisi`, `sonuclari_birlestir`'i çağırmadan hemen önce bunu kontrol eder; hepsi eksikse LLM çağrısı atlanır, sabit mesaj kullanılır. Katman 2 için `services/orchestrator.py::sonuclari_birlestir` ve `internet_arama_yap`'ın prompt metinleri güncellenir — kod akışı değişmez.

**Tech Stack:** Yeni bağımlılık yok; mevcut kalıp (rule-based, LLM'siz kontrol → `guardrails.py`/`gap_analysis.py` ile aynı felsefe).

## Global Constraints

- Katman 1 sadece `len(sonuclar) > 1` durumunda devreye girer (tek adımlı planlarda zaten sentez/birleştirme yok, araç kendi dürüst cevabını olduğu gibi döndürüyor — risk yok).
- Katman 1 tetiklenirse `sonuclari_birlestir` **hiç çağrılmaz** — ek LLM maliyeti eklemez, aksine bir çağrıyı ortadan kaldırır.
- Sabit mesaj: `"Bu konuda veritabanında, yüklü belgelerde veya internette güvenilir bir bilgi bulamadım. Sorunuzu farklı bir şekilde ifade etmeyi deneyebilirsiniz."`
- Katman 2, mevcut prompt'lara EKLEME yapar, davranışı test edilebilir şekilde değiştirmez (LLM çıktısı test edilmiyor — bu projenin mevcut testleri hiçbir yerde gerçek LLM çıktı kalitesini doğrulamıyor, sadece kod akışını; `eval/` klasörü ayrı, ücretli, opt-in bir araç).
- Yeni bağımlılık eklenmez.

---

## Katman 1: Deterministik Kısa Devre

### `services/gap_analysis.py`

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

(`EKSIK_BILGI_IFADELERI` zaten aynı dosyada tanımlı, ek import gerekmez.)

### `services/chat.py::_chat_akisi`

Mevcut:

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

şu şekilde değiştirilir:

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

`services/chat.py`'nin başına sabit eklenir:

```python
BILGI_BULUNAMADI_MESAJI = (
    'Bu konuda veritabanında, yüklü belgelerde veya internette güvenilir bir '
    'bilgi bulamadım. Sorunuzu farklı bir şekilde ifade etmeyi deneyebilirsiniz.'
)
```

Import satırı güncellenir: `from services.gap_analysis import cevap_eksik_mi, boslugu_kapat, tum_sonuclar_eksik_mi`.

## Katman 2: Prompt Sıkılaştırması

### `services/orchestrator.py::sonuclari_birlestir`

Mevcut prompt'a şu paragraf eklenir (mevcut "Kullanicinin orijinal sorusu" satırından önce):

```
ONEMLI: Parcalardan biri "bulunamadi"/"bilgi yok" turunden bir sonuc iceriyorsa,
bunu oldugu gibi belirt — o kaynaktan gercek bilgi olmadigini gizleme. Farkli
parcalardaki isimleri, olaylari veya kisileri birbiriyle iliskilendirerek
varsayimsal/uydurma baglantilar KURMA. Sadece parcalarda GERCEKTEN yazili olan
bilgiyi kullan.
```

### `services/orchestrator.py::internet_arama_yap`

Mevcut prompt:

```python
        return extract_text(llm_invoke_tracked(llm,
            f'Arama sonuçlarına dayanarak Türkçe cevap ver.\nSoru: {soru}\nSonuçlar: {sonuc}\nCevap:'
        ))
```

şu şekilde değiştirilir:

```python
        return extract_text(llm_invoke_tracked(llm,
            f'Arama sonuçlarına dayanarak Türkçe cevap ver. Eğer arama sonuçları '
            f'soruyla gerçekten ilgili değilse (örn. farklı bir kişi, yer ya da '
            f'konu hakkındaysa), bunları kullanma ve sonuçların soruyla ilgili '
            f'görünmediğini belirt — asla ilgisiz sonuçlardan emin bir cevap uydurma.\n'
            f'Soru: {soru}\nSonuçlar: {sonuc}\nCevap:'
        ))
```

## Test Planı

**Katman 1 (deterministik, tam test edilebilir):**

`tests/unit/test_gap_analysis.py`'ye eklenir:
- `tum_sonuclar_eksik_mi`: tüm sonuçlar eksik ifadeler içeriyorsa `True`
- en az bir sonuç gerçek bilgi içeriyorsa `False`
- boş liste → `False`

`tests/integration/test_chat_flow.py`'ye eklenir:
- 2 adımlı plan, ikisi de "kayıt bulunamadı" türünden cevap dönüyor → `sonuclari_birlestir` **çağrılmıyor** (mock `assert_not_called()`), final `cevap == BILGI_BULUNAMADI_MESAJI`, `'birlestiriliyor'` olayı yayılmıyor
- 2 adımlı plan, biri gerçek bilgi içeriyor → `sonuclari_birlestir` çağrılıyor (mevcut `test_cok_adimli_plan_birlestirilir` zaten bunu dolaylı kapsıyor, regresyon kontrolü)

**Katman 2:** LLM çıktısı test edilmiyor (proje konvansiyonu); sadece prompt metninde yeni talimat cümlelerinin gerçekten yer aldığı doğrulanır (basit string-containment testi, `tests/unit/test_orchestrator_prompts.py`):
- `sonuclari_birlestir`'in ürettiği prompt'ta "varsayimsal/uydurma baglantilar KURMA" ifadesi geçiyor
- `internet_arama_yap`'ın ürettiği prompt'ta "ilgisiz sonuçlardan emin bir cevap uydurma" ifadesi geçiyor

## Kapsam Dışı

- RAGAS benzeri bir faithfulness/groundedness skorlayıcısının canlı akışa eklenmesi (mevcut `eval/` zaten opt-in, ücretli bir araç olarak bunu ölçüyor; canlı akışa eklemek ek LLM maliyeti demek, spec'in "sıfır ek maliyet" ilkesiyle çelişir)
- `RagManager.ask_all`'ın kendi honesty talimatı (zaten var, dokunulmuyor)
- DB_QUERY/`db_sonuc_formatla` (zaten gözlenen örnekte dürüst "kayıt bulunamadı" döndürüyordu, sorun o katmanda değil)

## Başarı Kriteri

`pytest` sıfır hatayla geçer (yeni testler dahil). Gözlenen orijinal senaryo (yüklü belge yokken CV'ler hakkında soru → 3x boş DB_QUERY + SEARCH) artık uydurma bir hikaye yerine `BILGI_BULUNAMADI_MESAJI`'nı döner.
