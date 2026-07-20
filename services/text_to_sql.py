"""Doğal dil sorusunu SQL'e çeviren ve sonucu biçimlendiren Text-to-SQL katmanı."""
import re
import ast

from core.state import state
from core.llm import llm_invoke_tracked, extract_text


def sql_temizle(t: str) -> str:
    t = re.sub(r'```(?:sql)?\s*', '', t, flags=re.IGNORECASE).strip()
    t = t.replace('`', '"')
    m = re.search(r'SELECT\b.*', t, re.DOTALL | re.IGNORECASE)
    if m: t = m.group(0).strip()
    t = re.sub(r'["\s]+$', '', t).strip()
    t = re.sub(r'ILIKE', 'LIKE', t, flags=re.IGNORECASE)
    t = re.sub(r'"([^"]+)"', r"'\1'", t)
    return t


def sql_uret_ve_calistir(soru: str, gecmis: str = '', llm=None):
    """
    Doğal dil sorusunu veritabanı şemasına uygun SQLite SELECT sorgusuna dönüştürür.
    Sorguyu çalıştırır, hata oluşursa LLM ile otomatik self-correction (düzeltme) döngüsü çalıştırır.
    """
    llm = llm or state.llm_default

    schema_escaped = state.CACHED_SCHEMA.replace('{', '{{').replace('}', '}}')
    gecmis_escaped = (gecmis or 'Yok').replace('{', '{{').replace('}', '}}')
    few_shot = _FewShotPromptTemplate(
        example_selector=state.example_selector, example_prompt=state.example_prompt,
        prefix=f'Sen bir SQLite veritabanı uzmanısın.\nŞema:\n{schema_escaped}\n'
               f'Önceki konuşma: {gecmis_escaped}\n'
               f'KURALLAR:\n'
               f'1. SADECE geçerli bir SQLite SQL sorgusu döndür. Açıklama yazma.\n'
               f'2. LIKE kullan (ILIKE kullanma).\n'
               f'3. Tek SELECT cümlesi olsun.\n'
               f'4. Önceki konuşma geçmişini (bağlamı) SADECE yeni soru önceki konuşulan bir konuya, derse veya kişiye açıkça atıfta bulunuyorsa (örneğin "bu ders", "onun notları", "o hoca", "aynı bölüm", "başarı durumu nedir" vb.) kullan. Eğer yeni soru genel veya bağımsız bir soruysa (örneğin tüm dersleri listelemek gibi genel bir soru), önceki konuşmadaki filtreleri (örneğin belirli bir ders adını veya kişi adını) yeni soruya ASLA dahil etme.\n'
               f'Örnekler:',
        suffix='\nSoru: {soru}\nSQL: ', input_variables=['soru']
    )

    ham = extract_text(llm_invoke_tracked(llm, few_shot.format(soru=soru)))
    sql = sql_temizle(ham)

    try:
        return sql, state.db.run(sql)
    except Exception as e:
        fix_sql = sql_temizle(extract_text(llm_invoke_tracked(llm,
            f'Hatalı SQL: {sql}\nHata: {e}\nŞema: {state.CACHED_SCHEMA}\nSADECE düzeltilmiş SQL döndür.'
        )))
        return fix_sql, state.db.run(fix_sql)


def db_sonuc_formatla(soru: str, sonuc: str) -> str:
    if not sonuc or str(sonuc).strip() in ('[]', 'None', '', '[()]'):
        return 'Aradığınız kriterlere uygun kayıt bulunamadı.'
    try:
        rows = ast.literal_eval(str(sonuc))
    except:
        return f'Sonuç: {sonuc}'
    if not rows: return 'Kayıt bulunamadı.'
    s = soru.lower()
    if len(rows) == 1 and isinstance(rows[0], tuple) and len(rows[0]) == 1:
        v = rows[0][0]
        if isinstance(v, float): v = round(v, 2)
        if 'ortalama' in s: return f'Ortalama not: **{v}**'
        if 'en yüksek' in s: return f'En yüksek not: **{v}**'
        if 'kaç' in s: return f'Toplam **{v}**.'
        return f'Sonuç: **{v}**'
    lines = []
    for r in rows:
        if isinstance(r, tuple):
            vals = [str(round(v, 2)) if isinstance(v, float) else str(v) for v in r if v is not None]
            sep = ' ' if len(vals) == 2 and all(not v.replace('.','').isdigit() for v in vals) else ' – '
            lines.append('• ' + sep.join(vals))
        else:
            lines.append(f'• {r}')
    if len(lines) > 50:
        lines = lines[:50]
        lines.append('\n⚠️ İlk 50 kayıt gösteriliyor.')
    return '\n'.join(lines)
