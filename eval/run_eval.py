"""RAGAS tabanli LLM eval harness'inin calistirilabilir betigi.

Bu betik GERCEK OpenAI API cagrilari yapar (hem chatbot pipeline'i hem RAGAS'in
kendi degerlendirme metrikleri icin) ve UCRETLIDIR. pytest suite'inin bir
parcasi DEGILDIR, CI'da otomatik calismaz — elle `python eval/run_eval.py` ile
calistirilir. OPENAI_API_KEY .env dosyasindan okunur.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# `python eval/run_eval.py` seklinde dogrudan calistirildiginda proje koku
# sys.path'te olmuyor (pytest'te pytest.ini'deki pythonpath=. bunu hallediyor,
# burada elle eklememiz gerekiyor).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    """RAGAS'in evaluate() API'siyle RAG orneklerini skorlar. ragas 0.4.3'e
    karsi dogrulandi: EvaluationDataset.from_list kolonlari user_input/response/
    retrieved_contexts/reference (0.1.x'teki question/answer/contexts/
    ground_truth semasi degil). ragas.metrics'ten dogrudan import 0.4.3'te
    calisiyor ama gelecekte kaldirilacak (DeprecationWarning: ragas.metrics.
    collections'a tasinacak) — ileri bir surumde import hatasi alinirsa oradan
    tasi."""
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
