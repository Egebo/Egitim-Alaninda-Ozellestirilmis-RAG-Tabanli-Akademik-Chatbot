# Orkestratöre Görünür "Yansıma" (Reflection) Adımı

**Context:** Kullanıcı, başka bir sistemin (referans verdiği "Tunç'un sistemi") çalışma şeklini örnek göstererek, orkestratörün araç kullandığı adımlarda (belge/veritabanı/arama) sonucu aldıktan sonra bunu bir kez daha değerlendirip gerektiğinde rafine bir soruyla tekrar denemesini, ve bu "ikinci düşünme" anını frontend'de açıkça görünür kılmasını istedi. Şu an `services/gap_analysis.py::cevap_eksik_mi` sadece TÜM adımlar bittikten sonra "hiçbir şey bulunamadı mı" diye bakan, LLM'siz bir kural kontrolü — adım bazında "bulunan cevap yeterince iyi mi" sorusunu sormuyor.

**Goal:** RAG/DB_QUERY/SEARCH adımlarından her biri çalıştıktan hemen sonra, gerçek bir LLM çağrısıyla cevabın soruyu yeterince karşılayıp karşılamadığını değerlendiren; yetersizse aynı aracı en fazla 1 kez rafine edilmiş bir alt-soruyla tekrar çalıştıran; ve bu değerlendirme/tekrar-deneme anlarını frontend'de mevcut adım kartları üzerinden canlı gösteren bir "yansıma" katmanı eklemek.

**Architecture:** Yeni, tek sorumluluklu bir modül: `services/reflection.py`. İçinde tek bir saf fonksiyon, `yansit(alt_soru, cevap, kaynak, llm=None) -> dict`, native tool-calling (Pydantic şema + `bind_tools`) ile `{'yeterli': bool, 'rafine_soru': str}` döner — bu, `services/orchestrator.py::gorev_plani_olustur`'un zaten kullandığı desenle birebir aynı (proje genelinde tutarlılık). Sıralama/orkestrasyon mantığı **ayrı bir wrapper fonksiyona değil**, doğrudan `services/chat.py::_chat_akisi`'nin mevcut adım döngüsüne gömülür — `gap_analysis.py::cevap_eksik_mi`/`boslugu_kapat`'ın zaten aynı şekilde `_chat_akisi` içinden doğrudan çağrılmasıyla tutarlı bir seçim. Frontend'de (`templates/index.html`) yeni bir DOM yapısı eklenmiyor: mevcut `.step-item[data-tool="..."]` kartı yeniden kullanılıp üzerindeki etiket iki yeni akış olayıyla ("değerlendiriliyor", "yeniden deneniyor") güncelleniyor.

**Tech Stack:** Mevcut `langchain-core` (`bind_tools`, Pydantic şema) — yeni bağımlılık yok.

## Global Constraints

- Yansıma **sadece** `DB_QUERY`, `RAG`, `SEARCH` adımlarında çalışır — `GENERAL`/`META` adımları hiç dokunulmadan kalır (bunlar zaten en-iyi-çaba/best-effort cevap üretir, "yetersiz" kavramı onlara uymaz).
- **En fazla 1 tekrar deneme** — rafine soruyla tekrar çalıştırılan adım için ikinci bir yansıma yapılmaz (sonsuz döngü riski yok, mevcut `boslugu_kapat`'ın "en fazla 1 SEARCH ekle" sınırıyla aynı felsefe).
- `yansit()` içindeki LLM çağrısı herhangi bir sebeple başarısız olursa (API hatası, ağ sorunu) **fail-open**: `{'yeterli': True, 'rafine_soru': ''}` döner, `logger.exception(...)` ile loglanır — kullanıcı akışı asla kesilmez, `gorev_plani_olustur`'a eklediğimiz loglama düzeltmesiyle aynı prensip.
- `yansit()`, mevcut `llm_invoke_tracked`/`bind_tools` yolunu kullandığı için token/maliyet takibi ve `DAILY_BUDGET_USD` günlük bütçe guardrail'i otomatik olarak doğru çalışmaya devam eder — ayrı bir maliyet kontrolü eklenmiyor.
- Mevcut `gap_analysis.py::cevap_eksik_mi`/`boslugu_kapat` mekanizması **değişmeden** kalır; yansıma bundan bağımsız, tamamlayıcı bir katman.
- Yeni bağımlılık eklenmez.

---

## Veri Akışı

Örnek: kullanıcı bir belge sorusu soruyor, ilk RAG sonucu yetersiz çıkıyor.

| Sıra | Olay | Frontend'de görünen |
|---|---|---|
| 1 | `{type: 'adim_basladi', tool: 'RAG'}` | "Belgeler taranıyor…" |
| 2 | `{type: 'adim_bitti', tool: 'RAG', kaynak}` | "Belgeler tarandı" |
| 3 | `{type: 'degerlendiriliyor', tool: 'RAG'}` **(yeni)** | "Sonuç değerlendiriliyor…" |
| 4 | `{type: 'yeniden_deneniyor', tool: 'RAG'}` **(yeni, sadece yetersizse)** | "Daha net bir soruyla tekrar deneniyor…" |
| 5 | `{type: 'adim_bitti', tool: 'RAG', kaynak}` | "Belgeler tarandı" (final, kart kapanır) |

Yansıma "yeterli" bulursa 3. adımdan sonra doğrudan bir sonraki plan adımına (ya da birleştirmeye) geçilir, 4-5 hiç yayılmaz.

### Backend: `services/chat.py::_chat_akisi` adım döngüsü

```python
YANSITILACAK_ARACLAR = {'DB_QUERY', 'RAG', 'SEARCH'}

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

### `services/reflection.py`

```python
class YansimaSonucu(BaseModel):
    """Bir arac adiminin cevabinin sorulan soruyu yeterince karsilayip karsilamadigini degerlendirir."""
    yeterli: bool = Field(description='Cevap soruyu yeterince karsiliyor mu')
    rafine_soru: str = Field(default='', description='Yetersizse daha net/spesifik bir alt-soru; yeterliyse bos')

def yansit(alt_soru: str, cevap: str, kaynak: str, llm=None) -> dict:
    """
    Bir arac adiminin sonucunu degerlendirir. LLM basarisiz olursa fail-open
    davranir ({'yeterli': True, 'rafine_soru': ''}) — akisi asla kesmez.
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

### Frontend: `templates/index.html` akış olayı işleyicisi

Mevcut `adim_basladi`/`adim_bitti` `else if` zincirine, aynı `.step-item[data-tool="${olay.tool}"]` kartını bulup etiketini değiştiren 2 yeni dal eklenir:

```js
} else if (olay.type === 'degerlendiriliyor') {
  const item = list.querySelector(`.step-item[data-tool="${olay.tool}"]`);
  if (item) { item.classList.add('active'); item.querySelector('.step-label').textContent = 'Sonuç değerlendiriliyor…'; }
  summaryLabel.textContent = 'Sonuç değerlendiriliyor…';
} else if (olay.type === 'yeniden_deneniyor') {
  const item = list.querySelector(`.step-item[data-tool="${olay.tool}"]`);
  if (item) { item.querySelector('.step-label').textContent = 'Daha net bir soruyla tekrar deneniyor…'; }
  summaryLabel.textContent = 'Daha net bir soruyla tekrar deneniyor…';
}
```

## Test Planı

- `tests/unit/test_reflection.py`: `yansit()` için sahte LLM (mevcut `test_orchestrator_tool_calling.py`'deki `_SahteAracCagrisiLLM` deseniyle) — yeterli=True senaryosu, yeterli=False+rafine_soru senaryosu, LLM exception fırlattığında fail-open (`yeterli=True`) davranışı.
- `tests/integration/test_chat_flow.py`: `adim_calistir` ve `yansit` mock'lanarak, (a) RAG adımından sonra `degerlendiriliyor` olayının yayıldığı, (b) yetersiz sonuçta `yeniden_deneniyor` + ikinci `adim_bitti`'nin yayıldığı, (c) `GENERAL` adımında bu olayların hiç yayılmadığı doğrulanır.

## Kapsam Dışı

- `GENERAL`/`META` adımlarında yansıma
- Birden fazla tekrar deneme (retry loop)
- Yansımayı açıp kapatan bir kullanıcı ayarı/toggle
- `gap_analysis.py`'nin mevcut mekanizmasını değiştirmek
- RAGAS eval harness'ine (`eval/`) bu yeni davranışı ekstra ölçmek

## Bilinen Etki

Her RAG/DB_QUERY/SEARCH adımı artık +1 LLM çağrısı (yetersiz bulunursa +2) yapıyor — bu, mesaj başına gecikmeyi ve maliyeti artırır. Mevcut `DAILY_BUDGET_USD` guardrail'i toplam maliyeti zaten sınırladığı için ayrı bir önlem gerekmiyor, ama halka açık demo'da bütçenin daha hızlı tükeneceği bilinmeli.

## Başarı Kriteri

`pytest` sıfır hatayla geçer (yeni testler dahil). Uygulama çalışır durumdayken bir RAG/DB_QUERY sorusu sorulduğunda frontend'de "Sonuç değerlendiriliyor…" adımı görünür; kasıtlı olarak yetersiz bir cevap senaryosunda "Daha net bir soruyla tekrar deneniyor…" adımı da görünüp sonunda final bir cevapla kart kapanır.
