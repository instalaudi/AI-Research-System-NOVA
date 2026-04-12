import chromadb
from chromadb.config import Settings
import os
from typing import List, Dict, Any

# Setup persistence path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE_DIR, "data", "chroma")

class VectorDB:
    def __init__(self):
        # Ensure data directory exists
        os.makedirs(os.path.dirname(CHROMA_PATH), exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        # Use a collection for our knowledge base
        self.collection = self.client.get_or_create_collection(
            name="research_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        
        # v10.7.5: Semantic memory collection
        self.memory_collection = self.client.get_or_create_collection(
            name="user_memories",
            metadata={"hnsw:space": "cosine"}
        )

    def index_article(self, article_id: str, text: str, metadata: Dict[str, Any]):
        """
        Indexes or updates an article in the knowledge base.
        """
        self.collection.upsert(
            ids=[article_id],
            documents=[text],
            metadatas=[metadata]
        )
        print(f"[VectorDB] Indexed article: {article_id}")

    def index_memory(self, memory_id: str, text: str, user_id: int):
        """
        Indexes a user insight in the semantic memory collection.
        """
        self.memory_collection.upsert(
            ids=[memory_id],
            documents=[text],
            metadatas=[{"user_id": user_id}]
        )

    def search_similar_memory(self, query: str, user_id: int, limit: int = 1) -> List[Dict[str, Any]]:
        """
        Searches for semantically similar memories for a specific user.
        """
        results = self.memory_collection.query(
            query_texts=[query],
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

    def search_similar(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Performs semantic search to find semantically related chunks.
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=limit
        )
        
        # Flatten and format results
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

    def search_similar_batch(self, queries: List[str], limit: int = 1) -> List[List[Dict[str, Any]]]:
        """
        Performs semantic search for multiple queries in a single batch.
        """
        if not queries:
            return []
            
        results = self.collection.query(
            query_texts=queries,
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

    def delete_article(self, article_id: str):
        self.collection.delete(ids=[article_id])

# Global instance for easy access
vector_db = VectorDB()
