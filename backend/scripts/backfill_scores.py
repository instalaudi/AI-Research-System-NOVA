import asyncio
import os
import sys
from sqlalchemy.orm import Session
from datetime import datetime

# Add project paths to import core modules
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.database import SessionLocal, KnowledgeEntry
from core.llm_client import llm_client
from core.config import RELEVANCE_THRESHOLD, LLM_EMBED_MODEL

async def backfill_knowledge_scores():
    """
    Recalculates relevance scores for old entries without confidence_score
    or with default values, using the new specialized embedding model.
    """
    db = SessionLocal()
    try:
        # Fetch entries without confidence_score or defaults (< 0.5)
        entries = db.query(KnowledgeEntry).filter(KnowledgeEntry.confidence_score <= 0.8).all()
        print(f"[Backfill] Encontradas {len(entries)} entradas para re-evaluar.")
        
        for entry in entries:
            # We use the concepts or title to find a 'topic' reference
            target_topic = entry.concepts.split(",")[0] if entry.concepts else entry.category
            if not target_topic:
                target_topic = entry.title
                
            print(f"[Backfill] Evaluando: {entry.title} contra TEMA: {target_topic}...")
            
            # Use Explorer's logic (cosine similarity)
            from agents.explorer import ExplorerAgent
            agent = ExplorerAgent()
            
            topic_vec = await llm_client.get_embeddings(target_topic)
            content_to_score = f"{entry.title} {entry.content[:500]}"
            content_vec = await llm_client.get_embeddings(content_to_score)
            
            if topic_vec and content_vec:
                similarity = agent._cosine_similarity(topic_vec, content_vec)
                old_score = entry.confidence_score
                entry.confidence_score = round(float(similarity), 3)
                print(f"  -> Score actualizado: {old_score:.2f} -> {entry.confidence_score:.2f}")
            else:
                print(f"  -> Fallo al obtener embeddings para {entry.title}")
            
            await agent.close()
            
        db.commit()
        print("[Backfill] Proceso completado exitosamente.")
    except Exception as e:
        print(f"[Backfill] Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print(f"Iniciando Backfill de Scores usando {LLM_EMBED_MODEL}...")
    asyncio.run(backfill_knowledge_scores())
