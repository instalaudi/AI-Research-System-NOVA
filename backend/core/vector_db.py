import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Union
import datetime
import asyncio

# Setup persistence path
from core.config import DATA_DIR
CHROMA_PATH = os.path.join(DATA_DIR, "chroma")

class VectorDB:
    def __init__(self):
        # Ensure data directory exists
        os.makedirs(os.path.dirname(CHROMA_PATH), exist_ok=True)
        
        # v12.0.2: Disable telemetry explicitly to avoid "capture() takes 1 argument" errors
        self.client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # v11.8.2: Iniciamos colecciones SIN función de embedding interna.
        # NOVA pasará los vectores manualmente (Control Total de RAM).
        self.collection = self.client.get_or_create_collection(
            name="research_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        
        self.memory_collection = self.client.get_or_create_collection(
            name="user_memories",
            metadata={"hnsw:space": "cosine"}
        )

        self.code_history_collection = self.client.get_or_create_collection(
            name="code_history",
            metadata={"hnsw:space": "cosine"}
        )

    async def index_article(self, article_id: str, text: str, metadata: Dict[str, Any]):
        from core.llm_client import llm_client
        embeddings = await llm_client.get_embeddings(text)
        if not embeddings: return
        
        # v13.9.1 CRÍTICO FIX: Agregar timeout para evitar bloqueos indefinidos de ChromaDB
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    self.collection.upsert,
                    ids=[article_id],
                    embeddings=[embeddings],
                    documents=[text],
                    metadatas=[metadata]
                ),
                timeout=30.0  # 30 segundos máximo
            )
        except asyncio.TimeoutError:
            print(f"[VectorDB] WARNING: index_article timeout para {article_id} - ChromaDB bloqueado")

    async def upsert_batch(self, ids: List[str], documents: List[str], metadatas: List[Dict[str, Any]]):
        if not ids: return
        from core.llm_client import llm_client
        
        # Generación masiva de vectores (Optimizado v11.8.1 batching)
        embeddings = await llm_client.get_embeddings(documents)
        
        await asyncio.to_thread(
            self.collection.upsert,
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        print(f"[VectorDB] Batch indexed {len(ids)} chunks (Manual Vectors).")

    async def index_memory(self, memory_id: str, text: str, user_id: int):
        from core.llm_client import llm_client
        embeddings = await llm_client.get_embeddings(text)
        if not embeddings: return

        await asyncio.to_thread(
            self.memory_collection.upsert,
            ids=[memory_id],
            embeddings=[embeddings],
            documents=[text],
            metadatas=[{"user_id": user_id}]
        )

    async def search_similar_memory(self, query: str, user_id: int, limit: int = 1) -> List[Dict[str, Any]]:
        from core.llm_client import llm_client
        embeddings = await llm_client.get_embeddings(query)
        if not embeddings: return []

        results = await asyncio.to_thread(
            self.memory_collection.query,
            query_embeddings=[embeddings],
            where={"user_id": user_id},
            n_results=limit
        )
        
        formatted = []
        if results['ids']:
            for i in range(len(results['ids'][0])):
                formatted.append({
                    "id": results['ids'][0][i],
                    "document": results['documents'][0][i],
                    "distance": results['distances'][0][i] if 'distances' in results else 1.0
                })
        return formatted

    async def search_similar(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        from core.llm_client import llm_client
        embeddings = await llm_client.get_embeddings(query)
        if not embeddings: return []

        results = await asyncio.to_thread(
            self.collection.query,
            query_embeddings=[embeddings],
            n_results=limit
        )
        
        formatted = []
        if results['ids']:
            for i in range(len(results['ids'][0])):
                formatted.append({
                    "id": results['ids'][0][i],
                    "document": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i] if 'distances' in results else 0
                })
        return formatted

    async def search_similar_batch(self, queries: List[str], limit: int = 1) -> List[List[Dict[str, Any]]]:
        if not queries: return []
        from core.llm_client import llm_client
        
        embeddings = await llm_client.get_embeddings(queries)
            
        results = await asyncio.to_thread(
            self.collection.query,
            query_embeddings=embeddings,
            n_results=limit
        )
        
        batch_formatted = []
        if results['ids']:
            for query_idx in range(len(results['ids'])):
                query_results = []
                for i in range(len(results['ids'][query_idx])):
                    query_results.append({
                        "id": results['ids'][query_idx][i],
                        "document": results['documents'][query_idx][i],
                        "metadata": results['metadatas'][query_idx][i],
                        "distance": results['distances'][query_idx][i] if 'distances' in results else 0
                    })
                batch_formatted.append(query_results)
        return batch_formatted

    async def delete_article(self, article_id: str):
        await asyncio.to_thread(self.collection.delete, ids=[article_id])

    async def index_code_history(
        self,
        history_id: str,
        user_id: int,
        code: str,
        description: str,
        project_name: str,
        context: str = ""
    ) -> None:
        from core.llm_client import llm_client
        document = f"{description}\n{context}\n{code}".strip()
        embeddings = await llm_client.get_embeddings(document)
        if not embeddings: return

        metadata = {
            "user_id": int(user_id),
            "description": description or "",
            "project_name": project_name or "",
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        await asyncio.to_thread(
            self.code_history_collection.upsert,
            ids=[history_id],
            embeddings=[embeddings],
            documents=[document],
            metadatas=[metadata]
        )

    async def search_code_history(self, query: str, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        from core.llm_client import llm_client
        embeddings = await llm_client.get_embeddings(query)
        if not embeddings: return []

        results = await asyncio.to_thread(
            self.code_history_collection.query,
            query_embeddings=[embeddings],
            n_results=limit,
            where={"user_id": int(user_id)}
        )

        formatted: List[Dict[str, Any]] = []
        if results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                formatted.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if results.get("distances") else 0
                })
        return formatted

    def get_document_count(self) -> Dict[str, int]:
        """Returns the count of documents in each ChromaDB collection."""
        return {
            "research_knowledge": self.collection.count(),
            "user_memories": self.memory_collection.count(),
            "code_history": self.code_history_collection.count(),
        }

    async def cleanup_orphans(self) -> Dict[str, Any]:
        """
        FIX M-4 (Auditoría v11.9.18): Limpia documentos huérfanos en ChromaDB.

        Sincroniza la colección 'research_knowledge' con los KnowledgeEntry IDs
        activos en SQLite. Elimina documentos fantasma dejados por graph_pruning
        (merge_similar_nodes, prune_isolated_noise_nodes) que nunca limpiaban ChromaDB.

        Se ejecuta en batches de 100 para evitar picos de memoria.
        """
        from core.database import SessionLocal, KnowledgeEntry
        import logging
        _logger = logging.getLogger("core.vector_db")

        db = SessionLocal()
        try:
            # 1. Obtener todos los IDs activos en SQLite
            active_titles = set(
                row[0] for row in db.query(KnowledgeEntry.title).all()
            )

            # 2. Obtener todos los IDs en ChromaDB
            chroma_count = await asyncio.to_thread(self.collection.count)
            if chroma_count == 0:
                return {"status": "ok", "orphans_deleted": 0, "chroma_total": 0, "db_total": len(active_titles)}

            # ChromaDB get() con limit para no cargar todo en RAM de golpe
            BATCH_SIZE = 100
            orphan_ids: List[str] = []
            offset = 0

            while offset < chroma_count:
                batch = await asyncio.to_thread(
                    self.collection.get,
                    limit=BATCH_SIZE,
                    offset=offset,
                    include=["metadatas"]  # Solo necesitamos IDs
                )
                batch_ids = batch.get("ids", [])
                if not batch_ids:
                    break

                for doc_id in batch_ids:
                    if doc_id not in active_titles:
                        orphan_ids.append(doc_id)

                offset += len(batch_ids)

            # 3. Eliminar huérfanos en batches
            deleted = 0
            for i in range(0, len(orphan_ids), BATCH_SIZE):
                batch_to_delete = orphan_ids[i:i + BATCH_SIZE]
                await asyncio.to_thread(self.collection.delete, ids=batch_to_delete)
                deleted += len(batch_to_delete)
                _logger.info(f"[VectorDB] Cleanup: eliminados {len(batch_to_delete)} documentos huérfanos (batch {i // BATCH_SIZE + 1})")

            result = {
                "status": "ok",
                "orphans_deleted": deleted,
                "chroma_total_before": chroma_count,
                "chroma_total_after": self.collection.count(),
                "db_active_entries": len(active_titles),
            }

            if deleted > 0:
                _logger.info(f"[VectorDB] Cleanup completado: {deleted} documentos huérfanos eliminados de ChromaDB")
            else:
                _logger.info("[VectorDB] Cleanup: no se encontraron documentos huérfanos")

            return result

        except Exception as e:
            _logger.error(f"[VectorDB] Error en cleanup_orphans: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            db.close()

# Global instance
vector_db = VectorDB()

