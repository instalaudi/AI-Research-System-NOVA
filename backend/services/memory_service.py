import json
import re
import os
import shutil
import tempfile
import unicodedata
import datetime
from typing import List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_
from core.database import SessionLocal, ChatLog, UserMemory
from core.task_queue import task_queue
from core.llm_client import llm_client
from core.prompts import MEMORY_EXTRACTION_PROMPT
from core.context_manager import context_manager
from core.text_utils import extract_keywords, escape_like
from core.logging_config import get_logger, request_id_var
from core.vector_db import vector_db
import uuid

logger = get_logger("services.memory")

class MemoryService:
    def __init__(self):
        pass

    async def store_chat_message(self, role: str, content: str, user_id: int):
        """
        Stores a chat message in the persistent database and synchronization with Redis.
        """
        db = SessionLocal()
        try:
            new_log = ChatLog(role=role, content=content, user_id=user_id)
            db.add(new_log)
            db.commit()

            # Redis Sync for recent chat history
            try:
                task_queue.redis.rpush("chat_history_recent", json.dumps({
                    "role": role, 
                    "content": content, 
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "request_id": request_id_var.get()
                }))
                task_queue.redis.ltrim("chat_history_recent", -50, -1)
            except Exception as redis_e:
                logger.warning(f"Failed to sync chat to Redis: {redis_e}")

        except Exception as e:
            logger.error(f"Error storing chat message: {e}", exc_info=True)
        finally:
            db.close()

    def normalize_text(self, text: str) -> str:
        """Removes accents, punctuation and converts to lowercase for robust matching."""
        if not text: return ""
        text = text.lower()
        text = re.sub(r'[¿?¡!.,;:]', ' ', text)
        return "".join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        ).strip()

    def get_chat_history_context(self, db: Session, query_text: str, limit: int = 5) -> str:
        """
        Retrieves relevant message history using keyword matching.
        """
        query = self.normalize_text(query_text)
        keywords = extract_keywords(query)
        
        if not keywords:
            recent = db.query(ChatLog).order_by(ChatLog.timestamp.desc()).limit(limit).all()
            recent.reverse()
        else:
            filters = [ChatLog.content.ilike(f"%{escape_like(kw)}%", escape='\\') for kw in keywords]
            matches = db.query(ChatLog).filter(or_(*filters)).order_by(ChatLog.timestamp.desc()).limit(limit).all()
            matches.reverse()
            recent = matches

        if not recent:
            return ""
            
        history_str = "HISTORIAL RELEVANTE DE CONVERSACIÓN (ÚLTIMOS 5):\n"
        for msg in recent:
            role_label = "Usuario" if msg.role == 'user' else "NOVA"
            # Adjust truncation based on content type
            limit_chars = 800 if any(tag in msg.content for tag in ["[VISTO POR NOVA", "[INVESTIGACIÓN DE NOVA"]) else 250
            display_content = msg.content[:limit_chars] + "..." if len(msg.content) > limit_chars else msg.content
            # FIXED: Removed brackets [] to avoid model mimicry
            history_str += f"- {msg.timestamp.strftime('%H:%M')} {role_label}: {display_content}\n"
        
        return history_str + "\n"

    async def extract_and_store_memory(self, user_query: str, user_id: int):
        """
        Background task to extract insights from user messages and store them in memory.
        """
        prompt = MEMORY_EXTRACTION_PROMPT.format(user_query=user_query)
        try:
            messages = [{"role": "user", "content": prompt}]
            insight = await llm_client.chat(messages, priority=1)
            
            if insight and insight.strip() and "NONE" not in insight.upper():
                clean_insight = insight.strip()
                if len(clean_insight) < 10:
                    return

                db = SessionLocal()
                try:
                    # v10.7.5: Semantic Deduplication via ChromaDB
                    # Threshold: 0.15 (Cosine distance) -> Very similar
                    similar = vector_db.search_similar_memory(clean_insight, user_id, limit=1)
                    
                    if similar and similar[0]["distance"] <= 0.15:
                        logger.info(f"Semantic duplicate detected (dist: {similar[0]['distance']:.4f}). Skipping.")
                        return

                    # Create new memory record
                    memory_token = str(uuid.uuid4())[:8]
                    new_memory = UserMemory(insight=clean_insight, importance=1, user_id=user_id)
                    db.add(new_memory)
                    db.commit()
                    db.refresh(new_memory)
                    
                    # Sync with VectorDB for future deduplication
                    vector_db.index_memory(str(new_memory.id), clean_insight, user_id)
                    
                    logger.info(f"Insight stored for user {user_id}: '{clean_insight[:50]}'")
                finally:
                    db.close()
        except Exception as e:
            logger.error(f"Error extracting memory: {e}")

    async def build_rag_context(self, intent: str, query: str, files_context: str, db: Session) -> str:
        """
        Builds the full RAG context using the context manager.
        """
        return await context_manager.build_context(intent, query, files_context, db)

    async def ingest_document(self, file_content: Any, filename: str, user_id: int) -> bool:
        """
        Ingests a document through the Librarian.
        """
        ext = os.path.splitext(filename)[1].lower()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                shutil.copyfileobj(file_content, tmp)
                tmp_path = tmp.name
            
            from core.librarian import librarian
            success = await librarian.ingest_book(tmp_path, filename, user_id=user_id)
            return success
        except Exception as e:
            logger.error(f"Ingestion failed for {filename}: {e}")
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def list_knowledge(self, db: Session, limit: int = 50, offset: int = 0) -> List[dict]:
        """
        Lists knowledge entries with pagination (v10.12.0). 
        Default: 50 most recent items to avoid UI freezing.
        """
        from core.database import KnowledgeEntry
        entries = db.query(KnowledgeEntry).order_by(KnowledgeEntry.date.desc()).offset(offset).limit(limit).all()
        return [
            {
                "id": e.id, 
                "title": e.title, 
                "category": e.category, 
                "content": e.content, 
                "confidence_score": e.confidence_score, 
                "date": e.date.isoformat() if e.date else None, 
                "url": e.url, 
                "concepts": e.concepts
            } for e in entries
        ]

memory_service = MemoryService()
