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
