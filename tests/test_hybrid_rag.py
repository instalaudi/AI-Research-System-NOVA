"""
Pruebas Unitarias Automatizadas para Hybrid RAG & Memoria Jerárquica Episódica (Fase 1)
"""

import pytest
import asyncio
from core.hybrid_retriever import BM25Index, HybridRetriever, tokenize_text
from core.episodic_memory import EpisodicMemory


def test_tokenizer_technical_terms():
    """Valida que el tokenizador preserve identificadores de código y términos técnicos."""
    text = "FastAPI middleware CORS con CVE-2024-38077 y camelCaseIdentifier"
    tokens = tokenize_text(text)
    
    assert "fastapi" in tokens
    assert "middleware" in tokens
    assert "cors" in tokens
    assert "cve-2024-38077" in tokens
    assert "camelcaseidentifier" in tokens


def test_bm25_index_and_search():
    """Valida la indexación y ranking de relevancia léxica con BM25."""
    index = BM25Index()
    docs = [
        {"id": "doc1", "text": "Arquitectura de microservicios con FastAPI y Redis en Docker"},
        {"id": "doc2", "text": "Modelos de lenguaje LLM con Ollama y cuantización GGUF"},
        {"id": "doc3", "text": "Ciberseguridad y prevención de vulnerabilidades CVE-2024-38077"},
    ]
    index.add_documents(docs)

    results = index.search("CVE-2024-38077", top_k=2)
    assert len(results) > 0
    assert results[0]["id"] == "doc3"
    assert results[0]["bm25_score"] > 0

    results_fastapi = index.search("FastAPI Docker", top_k=2)
    assert len(results_fastapi) > 0
    assert results_fastapi[0]["id"] == "doc1"


def test_reciprocal_rank_fusion():
    """Valida el cálculo determinista y la combinación de rankings RRF."""
    retriever = HybridRetriever(dense_weight=0.6, sparse_weight=0.4, rrf_k=60)
    
    dense_results = [
        {"id": "docA", "text": "Concepto A semánticamente similar", "score": 0.95},
        {"id": "docB", "text": "Concepto B semánticamente similar", "score": 0.85},
    ]
    sparse_results = [
        {"id": "docB", "text": "Concepto B semánticamente similar", "bm25_score": 4.2},
        {"id": "docC", "text": "Concepto C con coincidencia léxica", "bm25_score": 3.1},
    ]
    
    fused = retriever.reciprocal_rank_fusion(dense_results, sparse_results, top_k=3)
    
    assert len(fused) == 3
    # docB aparece en ambas ramas (rank 2 en dense, rank 1 en sparse), por lo que debe recibir un impulso sinérgico
    doc_ids = [d["id"] for d in fused]
    assert "docB" in doc_ids
    assert fused[0]["rrf_score"] > 0


@pytest.mark.asyncio
async def test_hybrid_retrieve_async():
    """Valida la función asíncrona retrieve con función de búsqueda densa mockeada."""
    retriever = HybridRetriever()
    retriever.index_documents([
        {"id": "lex1", "text": "Configuración de PostgreSQL con SQLAlchemy AsyncSession"}
    ])

    async def mock_dense(q: str, top_k: int = 5):
        return [{"id": "dense1", "text": "Bases de datos relacionales y transacciones ACID"}]

    results = await retriever.retrieve("PostgreSQL SQLAlchemy", dense_search_fn=mock_dense, top_k=2)
    assert len(results) >= 1
    ids = [r["id"] for r in results]
    assert "lex1" in ids


def test_episodic_memory_lifecycle(tmp_path):
    """Valida el ciclo de vida de la memoria episódica, hitos y hechos de usuario."""
    mem_file = tmp_path / "test_episodic_memory.json"
    mem = EpisodicMemory(storage_path=mem_file)

    # 1. Registrar turnos de sesión
    mem.record_turn("user", "¿Cómo optimizar SQLite?", intent="RESEARCH")
    mem.record_turn("assistant", "Usa WAL mode y PRAGMA synchronous = NORMAL.")
    session = mem.get_recent_session(2)
    assert len(session) == 2
    assert session[0]["role"] == "user"

    # 2. Registrar episodio
    mem.record_episode(
        topic="Optimización de Base de Datos SQLite",
        summary="Se implementó WAL mode para soportar múltiples lectores concurrentes.",
        category="research",
        key_learnings=["WAL mode", "PRAGMA synchronous = NORMAL"]
    )
    assert len(mem.episodes) == 1

    # 3. Recuperar episodio relevante
    recalled = mem.recall_relevant_episodes("SQLite WAL optimización", limit=1)
    assert len(recalled) == 1
    assert recalled[0]["topic"] == "Optimización de Base de Datos SQLite"

    # 4. Registrar hecho semántico del usuario
    mem.record_fact("lenguaje_preferido", "Python 3.12")
    facts_str = mem.get_facts_context()
    assert "lenguaje_preferido" in facts_str
    assert "Python 3.12" in facts_str

    # 5. Validar recarga desde disco
    mem_reloaded = EpisodicMemory(storage_path=mem_file)
    assert len(mem_reloaded.episodes) == 1
    assert mem_reloaded.user_facts.get("lenguaje_preferido", {}).get("value") == "Python 3.12"
