"""LLM çağırma, token/maliyet takibi ve yanıt metni çıkarma yardımcıları."""
import os

from core.state import state


def _get_llm(model_name: str):
    if model_name == 'gemini':
        key = os.environ.get('GOOGLE_API_KEY')
        if not key:
            raise ValueError("Google API anahtarı (GOOGLE_API_KEY) bulunamadı. Lütfen .env dosyasını kontrol edin.")
        return _ChatGoogleGenerativeAI(model='gemini-flash-latest', google_api_key=key, temperature=0)

    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise ValueError("OpenAI API anahtarı (OPENAI_API_KEY) bulunamadı. Lütfen .env dosyasını kontrol edin.")
    return _ChatOpenAI(model='gpt-4o-mini', openai_api_key=key, temperature=0)


def _calculate_cost(model_name: str, tokens: int) -> float:
    mn = model_name.lower()
    if 'gpt-4o-mini' in mn: return (tokens / 1_000_000) * 0.30
    if 'gpt-4o'      in mn: return (tokens / 1_000_000) * 3.75
    if 'gpt'         in mn: return (tokens / 1_000_000) * 0.30
    if 'gemini'      in mn: return (tokens / 1_000_000) * 0.075
    return 0.0


def llm_invoke_tracked(llm, input_data):
    response = llm.invoke(input_data)
    tokens = 0
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        tokens = response.usage_metadata.get('total_tokens', 0)
    if tokens == 0 and hasattr(response, 'response_metadata') and response.response_metadata:
        tu = response.response_metadata.get('token_usage', {})
        tokens = tu.get('total_tokens', 0)
    if tokens > 0:
        state.global_tokens += tokens
        mn = getattr(llm, 'model_name', getattr(llm, 'model', 'unknown'))
        state.global_cost_usd += _calculate_cost(mn, tokens)
    return response


def extract_text(response) -> str:
    if hasattr(response, 'content'):
        c = response.content
        if isinstance(c, str): return c.strip()
        if isinstance(c, list):
            return ''.join(p['text'] if isinstance(p, dict) else str(p) for p in c).strip()
        return str(c).strip()
    return str(response).strip()
