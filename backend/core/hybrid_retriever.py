"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v14.0 — Motor de Recuperación Híbrida (Hybrid RAG)     ║
║  Archivo: core/hybrid_retriever.py                           ║
║  Combina búsqueda léxica (BM25) con búsqueda semántica      ║
║  densa (ChromaDB) mediante Reciprocal Rank Fusion (RRF).     ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import math
import logging
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("core.hybrid_retriever")

# Constante de amortiguación para Reciprocal Rank Fusion
RRF_K_DEFAULT = 60

# Stopwords comunes en español e inglés
STOPWORDS = {
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las", "por", "un", "para", "con",
    "no", "una", "su", "al", "lo", "como", "mas", "pero", "sus", "le", "ya", "o", "este", "si",
    "porque", "esta", "entre", "cuando", "muy", "sin", "sobre", "tambien", "me", "hasta", "hay",
    "donde", "quien", "desde", "todo", "nos", "durante", "todos", "uno", "les", "ni", "contra",
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "about",
    "against", "between", "into", "through", "during", "before", "after", "above", "below", "from",
    "up", "down", "in", "out", "off", "over", "under", "again", "further", "then", "once", "is",
    "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did"
}


def tokenize_text(text: str) -> List[str]:
    """
    Tokenizador especializado para términos técnicos, código y lenguaje natural.
    Preserva identificadores como camelCase, snake_case, guiones y números de versión.
    """
    if not text:
        return []
    
    # 1. Normalizar minúsculas preservando símbolos técnicos relevantes
    raw_tokens = re.findall(r'[a-zA-Z0-9_\-\.\:\@\#]+', text.lower())
    
    tokens = []
    for token in raw_tokens:
        # Descartar puntuación pura
        clean = token.strip(".-_:")
        if not clean:
            continue
        
        # Agregar el token completo (ej: "fastapi.middleware.cors" o "cve-2024-38077")
        if clean not in STOPWORDS and len(clean) > 1:
            tokens.append(clean)
            
        # Si tiene separadores internos, agregar sub-términos
        sub_terms = re.split(r'[\.\-\_\:]+', clean)
        if len(sub_terms) > 1:
            for sub in sub_terms:
                if sub not in STOPWORDS and len(sub) > 1 and sub != clean:
                    tokens.append(sub)
                    
    return tokens


class BM25Index:
    """
    Índice BM25 ligero y eficiente en memoria para búsqueda léxica exacta.
    Implementa el algoritmo BM25 Okapi estándar con normalización de longitud.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids: List[str] = []
        self.doc_contents: Dict[str, str] = {}
        self.doc_metadatas: Dict[str, Dict[str, Any]] = {}
        self.doc_lengths: Dict[str, int] = {}
        self.avg_doc_len: float = 0.0
        self.doc_freqs: Dict[str, int] = defaultdict(int)  # término -> cantidad de docs donde aparece
        self.term_freqs: Dict[str, Counter] = {}          # doc_id -> Counter(términos)
        self.total_docs: int = 0

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        Indexa una lista de documentos.
        Cada documento debe ser un dict con: 'id', 'text', opcional 'metadata'.
        """
        for doc in documents:
            doc_id = str(doc.get("id", f"doc_{len(self.doc_ids)}"))
            text = doc.get("text", "")
            metadata = doc.get("metadata", {})
            
            tokens = tokenize_text(text)
            tf = Counter(tokens)
            doc_len = len(tokens)
            
            if doc_id not in self.doc_contents:
                self.doc_ids.append(doc_id)
                self.total_docs += 1
            
            # Si el documento ya existía, restar frecuencias previas
            if doc_id in self.term_freqs:
                old_tf = self.term_freqs[doc_id]
                for term in old_tf:
                    self.doc_freqs[term] = max(0, self.doc_freqs[term] - 1)
            
            self.doc_contents[doc_id] = text
            self.doc_metadatas[doc_id] = metadata
            self.doc_lengths[doc_id] = doc_len
            self.term_freqs[doc_id] = tf
            
            for term in tf.keys():
                self.doc_freqs[term] += 1
                
        if self.total_docs > 0:
            self.avg_doc_len = sum(self.doc_lengths.values()) / self.total_docs

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Realiza búsqueda BM25 y retorna los top_k documentos ordenados por score."""
        query_tokens = tokenize_text(query)
        if not query_tokens or self.total_docs == 0:
            return []

        scores: Dict[str, float] = defaultdict(float)
        
        for term in query_tokens:
            df = self.doc_freqs.get(term, 0)
            if df == 0:
                continue
                
            # Cálculo de IDF con suavizado Okapi
            idf = math.log(1.0 + (self.total_docs - df + 0.5) / (df + 0.5))
            if idf <= 0:
                idf = 0.05  # Evitar puntuación nula o negativa para términos muy frecuentes
                
            for doc_id, tf_map in self.term_freqs.items():
                tf = tf_map.get(term, 0)
                if tf == 0:
                    continue
                    
                doc_len = self.doc_lengths.get(doc_id, self.avg_doc_len)
                num = tf * (self.k1 + 1)
                den = tf + self.k1 * (1 - self.b + self.b * (doc_len / (self.avg_doc_len or 1.0)))
                scores[doc_id] += idf * (num / den)

        if not scores:
            return []

        ranked_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        results = []
        for doc_id, score in ranked_docs:
            results.append({
                "id": doc_id,
                "text": self.doc_contents[doc_id],
                "metadata": self.doc_metadatas.get(doc_id, {}),
                "bm25_score": round(score, 4),
                "source": "bm25"
            })
            
        return results


class HybridRetriever:
    """
    Recuperador híbrido unificado para el sistema RAG de NOVA.
    Combina:
    1. Búsqueda Vectorial Densa (ChromaDB / Embeddings)
    2. Búsqueda Léxica Exacta (BM25 Index)
    3. Fusión por Reciprocal Rank Fusion (RRF)
    """
    def __init__(self, dense_weight: float = 0.6, sparse_weight: float = 0.4, rrf_k: int = RRF_K_DEFAULT):
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.rrf_k = rrf_k
        self.bm25_index = BM25Index()

    def index_documents(self, documents: List[Dict[str, Any]]):
        """Indexa documentos en el índice léxico BM25."""
        self.bm25_index.add_documents(documents)

    def reciprocal_rank_fusion(
        self,
        dense_results: List[Dict[str, Any]],
        sparse_results: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Aplica la fórmula estándar de Reciprocal Rank Fusion:
        RRF_Score(d) = sum_m [ weight_m / (k + rank_m(d)) ]
        """
        rrf_scores: Dict[str, float] = defaultdict(float)
        doc_store: Dict[str, Dict[str, Any]] = {}

        # 1. Puntuación de la rama Densa
        for rank, doc in enumerate(dense_results, start=1):
            doc_id = str(doc.get("id", f"dense_{rank}"))
            doc_store[doc_id] = doc
            rrf_scores[doc_id] += self.dense_weight / (self.rrf_k + rank)

        # 2. Puntuación de la rama Dispersa (BM25)
        for rank, doc in enumerate(sparse_results, start=1):
            doc_id = str(doc.get("id", f"sparse_{rank}"))
            if doc_id not in doc_store:
                doc_store[doc_id] = doc
            rrf_scores[doc_id] += self.sparse_weight / (self.rrf_k + rank)

        if not rrf_scores:
            return []

        # 3. Ordenar por puntuación RRF combinada
        sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        fused_results = []
        for doc_id, rrf_score in sorted_docs:
            doc_info = dict(doc_store[doc_id])
            doc_info["rrf_score"] = round(rrf_score, 6)
            fused_results.append(doc_info)

        return fused_results

    async def retrieve(
        self,
        query: str,
        dense_search_fn: Optional[Any] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta la recuperación híbrida completa (Dense + BM25) para una consulta.
        Si dense_search_fn se proporciona, se invoca asíncronamente.
        """
        # Rama 1: BM25 Léxico
        sparse_results = self.bm25_index.search(query, top_k=top_k * 2)

        # Rama 2: Búsqueda Densa
        dense_results = []
        if dense_search_fn is not None:
            try:
                import inspect
                if inspect.iscoroutinefunction(dense_search_fn):
                    dense_results = await dense_search_fn(query, top_k=top_k * 2)
                else:
                    dense_results = dense_search_fn(query, top_k=top_k * 2)
            except Exception as e:
                logger.error(f"[HybridRetriever] Error en búsqueda densa: {e}")

        # Fusión RRF
        return self.reciprocal_rank_fusion(dense_results, sparse_results, top_k=top_k)


# Instancia global del recuperador híbrido
hybrid_retriever = HybridRetriever()
