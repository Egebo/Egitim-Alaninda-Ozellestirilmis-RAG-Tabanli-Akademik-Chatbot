"""Yüklenen belgeler üzerinde RAG (Retrieval-Augmented Generation) sorgulama."""
import os
import shutil

from core.state import state
from core.llm import llm_invoke_tracked, extract_text

SIMILARITY_THRESHOLD = 0.45
MAX_TOTAL_CHUNKS = 20
FALLBACK_THRESHOLD = 0.1

# multilingual-e5-small'in max_seq_length'i 512 token; 400/80 güvenli pay birakiyor
# (özel token'lar + olasi kirpma icin), karakter degil GERCEK model token sayisiyla olculuyor.
CHUNK_SIZE_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 80


def _k_per_doc(n_docs: int) -> int:
    return max(1, MAX_TOTAL_CHUNKS // n_docs)


class RagManager:
    def __init__(self, cache_dir='./chroma_db'):
        self.cache_dir = cache_dir
        self.documents = {}
        self.db = None

    @property
    def embeddings(self):
        return state.embedding_model

    def add_document(self, path: str) -> str:
        doc_name = os.path.basename(path)
        ext = path.rsplit('.', 1)[-1].lower()
        if doc_name in self.documents:
            return doc_name

        if ext == 'pdf':
            loader = _PyPDFLoader(path)
        elif ext in ('xlsx', 'xls'):
            df = _pandas.read_excel(path)
            tmp = path + '.txt'
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(df.to_string())
            loader = _TextLoader(tmp, encoding='utf-8')
        elif ext == 'txt':
            loader = _TextLoader(path, encoding='utf-8')
        else:
            raise ValueError(f'Desteklenmeyen dosya türü: {ext}')

        docs = loader.load()
        try:
            tokenizer = self.embeddings.client.tokenizer
            length_function = lambda text: len(tokenizer.encode(text, add_special_tokens=False))
            chunk_size, chunk_overlap = CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS
        except Exception:
            # Tokenizer'a erişilemezse eski karakter-tabanlı davranışa geri dön
            length_function = len
            chunk_size, chunk_overlap = 1000, 200
        splitter = _RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=length_function
        )
        splits = splitter.split_documents(docs)

        safe = doc_name.replace('.', '_').replace(' ', '_')
        doc_persist_dir = os.path.join(self.cache_dir, safe)
        vs = _Chroma.from_documents(splits, self.embeddings, persist_directory=doc_persist_dir)
        self.documents[doc_name] = {'vector_store': vs}
        return doc_name

    def remove_document(self, doc_name: str):
        if doc_name in self.documents:
            del self.documents[doc_name]
            safe = doc_name.replace('.', '_').replace(' ', '_')
            doc_persist_dir = os.path.join(self.cache_dir, safe)
            try:
                if os.path.exists(doc_persist_dir):
                    shutil.rmtree(doc_persist_dir)
            except:
                pass

    def list_documents(self):
        return list(self.documents.keys())

    def ask_all(self, question: str, llm=None):
        llm = llm or state.llm_default
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

        sorted_docs = all_docs[:MAX_TOTAL_CHUNKS]
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
