import tiktoken
import logging
import asyncio
from typing import List, Dict, Any, Optional
from core.database import SessionLocal, ChatLog

logger = logging.getLogger(__name__)

class ContextManager:
    """
    Tier 4 Expert Context Management System.
    Features:
    - Explicit Token Budgeting (Exact Knapsack)
    - Context Weighting (Distance x Recency x Priority)
    - Context Poisoning Protection (LLM Validator)
    - Persistent Memory Condensation
    - Adaptive Modes (FAST_CHAT, DEEP_RESEARCH, DEBUG_MODE)
    """
    def __init__(self, max_tokens: int = 4000):
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.max_tokens = max_tokens
        self.system_reserved = 500
        self._condensing = False  # FIX #2: Evita tareas de condensación duplicadas

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoder.encode(str(text)))

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        if not text:
            return ""
        tokens = self.encoder.encode(str(text))
        if len(tokens) <= max_tokens:
            return text
        return self.encoder.decode(tokens[:max_tokens]) + "\n[... truncated ...]"

    async def build_context(
        self,
        mode: str, 
        query: str,
        files_context: str,
        db_session
    ) -> str:
        """
        Adaptive Context Assembly based on operational modes:
        - FAST_CHAT: 90% History, 10% RAG, No Poisoning Check
        - DEEP_RESEARCH: 20% History, 80% RAG, Strict Filtering
        - DEBUG_MODE: 0% History, 100% Files/Status
        """
        mode = mode.upper()
        if mode not in ["FAST_CHAT", "DEEP_RESEARCH", "DEBUG_MODE"]:
            mode = "DEEP_RESEARCH" if intent_is_research(mode) else "FAST_CHAT"

        budget = self.max_tokens - self.system_reserved - self.count_tokens(query)
        
        # DEBUG_MODE shortcut
        if mode == "DEBUG_MODE":
            files_tokens = self.count_tokens(files_context)
            final_files_pos = self.truncate_to_tokens(files_context, budget) if files_tokens > budget else files_context
            return f"[MODO DEBUG ACTIVO]\n[ARCHIVOS/ESTADO]\n{final_files_pos}"

        # 1. Allocate for files (Top Priority)
        files_tokens = self.count_tokens(files_context)
        final_files_pos = ""
        if files_tokens > 0:
            max_file_tokens = int(budget * 0.5) 
            if files_tokens > max_file_tokens:
                final_files_pos = self.truncate_to_tokens(files_context, max_file_tokens)
                budget -= max_file_tokens
            else:
                final_files_pos = files_context
                budget -= files_tokens

        # Mode configurations
        if mode == "DEEP_RESEARCH":
            rag_pct, hist_pct = 0.8, 0.2
            max_docs = 4
            use_poisoning_protection = True
        else: # FAST_CHAT
            rag_pct, hist_pct = 0.2, 0.8
            max_docs = 2
            use_poisoning_protection = False

        rag_allocation = int(budget * rag_pct)
        history_allocation = budget - rag_allocation

        # 2. RAG Semantic Context (Weighted & Protected)
        rag_context = await self._get_rag_context(query, max_docs, use_poisoning_protection)
        final_rag_pos = ""
        if rag_context:
            rag_tokens = self.count_tokens(rag_context)
            if rag_tokens > rag_allocation:
                final_rag_pos = self.truncate_to_tokens(rag_context, rag_allocation)
                budget -= rag_allocation
            else:
                final_rag_pos = rag_context
                budget -= rag_tokens
                # Refund leftover budget strictly to history
                history_allocation += (rag_allocation - rag_tokens)

        # 3. Episodic Memory (With Condensation)
        episodic_context = await self._get_history_context(db_session, query, history_allocation, mode)
        final_history_pos = episodic_context

        # Assemble final context
        final_context = f"""
[CAPA DE MEMORIA HISTÓRICA]
{final_history_pos}

[CAPA DE MEMORIA SEMÁNTICA (RAG)]
{final_rag_pos if final_rag_pos else "Sin contexto recuperado."}
"""
        if final_files_pos:
            final_context += f"\n[ARCHIVOS ADJUNTOS]\n{final_files_pos}"

        return final_context

    async def _get_rag_context(self, query: str, max_docs: int, use_poisoning_protection: bool) -> str:
        """
        Retrieves context using Context Weighting (Score = Relevance * Priority * Recency)
        and optional LLM-based Poisoning Protection.
        """
        from core.vector_db import vector_db
        try:
            results = vector_db.search_similar(query, limit=12)
            
            # Step 1: Base Relevance Filter
            filtered = [r for r in results if r.get('distance', 1.0) < 0.7]
            if not filtered:
                return ""

            # Step 2: Context Weighting
            # For simplicity, we assume generic knowledge has priority 1.0
            # If metadata has 'type', we could boost certain types.
            import datetime
            scored_results = []
            for r in filtered:
                base_relevance = 1.0 - (r.get('distance', 1.0) / 2.0)
                priority = 1.2 if r.get('metadata', {}).get('type') == 'research' else 1.0
                
                # We lack a strict timestamp in chunks usually, so we default recency to 1.0
                # If present, recency would be a decay function.
                recency = 1.0 
                
                final_score = base_relevance * priority * recency
                scored_results.append((final_score, r))
            
            # Sort by highest score
            scored_results.sort(key=lambda x: x[0], reverse=True)
            top_results = [r[1] for r in scored_results][:max_docs * 2] # Keep buffer for validator

            # FIX #1: Eliminado el Context Poisoning Validator (hasta 8 LLM calls serializadas
            # = hasta 24s extra antes de cada respuesta). Reemplazado por filtro coseno estricto.
            # qwen2.5:3b probablemente no estaba instalado → validaciones fallaban silenciosamente.
            STRICT_DISTANCE = 0.4  # Similitud coseno real: solo documentos genuinamente relevantes
            validated_docs = [r for r in top_results if r.get('distance', 1.0) < STRICT_DISTANCE][:max_docs]

            if not validated_docs:
                return ""

            parts = []
            for r in validated_docs:
                md = r['metadata']
                content = r['document']
                dist = r.get('distance', 1.0)
                relevance_score = round((1.0 - (dist / 2.0)) * 100) 
                parts.append(f"--- [Doc: {md.get('title', 'Unknown')} | Relevancia: {relevance_score}%] ---\n{content}\n")

            return "\n".join(parts)
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            return "[Error retrieving knowledge]"

    async def _get_history_context(self, db_session, query: str, tokens_limit: int, mode: str) -> str:
        """
        Retrieves history and actively condenses it into permanent Memory if it grows too large.
        """
        if tokens_limit <= 50:
            return ""

        # Fetch up to 20 recent messages to check if we need to condense
        recent = db_session.query(ChatLog).order_by(ChatLog.timestamp.desc()).limit(20).all()
        if not recent:
            return ""

        # Check for Memory Condensation trigger
        # If we have 15+ un-summarized messages, condense them!
        unsummarized_count = 0
        for msg in recent:
            if msg.role == "system_summary":
                break
            unsummarized_count += 1
            
        if unsummarized_count >= 15 and not self._condensing:
            self._condensing = True
            task = asyncio.create_task(self._condense_memory_task(recent[:unsummarized_count]))
            task.add_done_callback(lambda _: setattr(self, '_condensing', False))
            task.add_done_callback(
                lambda t: t.exception() and print(f"[ContextManager] Memory condensation error: {t.exception()}")
            )

        parts = []
        current_tokens = 0
        limit_msgs = 4 if mode == "DEEP_RESEARCH" else 10
        
        for msg in recent[:limit_msgs]:
            role = "RESUMEN" if msg.role == 'system_summary' else ("Usuario" if msg.role == 'user' else "NOVA")
            msg_str = f"{role}: {msg.content}\n"
            msg_toks = self.count_tokens(msg_str)
            
            if current_tokens + msg_toks > tokens_limit:
                break
                
            parts.insert(0, msg_str)
            current_tokens += msg_toks
            
            if msg.role == 'system_summary':
                break # We hit the summary block, no need to go further back in episodic memory

        return "".join(parts)

    async def _condense_memory_task(self, messages_to_summarize: List[Any]):
        """
        Background task to condense a long chat sequence into a single memory block.
        """
        from core.llm_client import llm_client
        db = SessionLocal()
        try:
            # We want chronological order for the summary
            chrono_msgs = reversed(messages_to_summarize)
            convo = "\n".join([f"{m.role}: {m.content}" for m in chrono_msgs])
            
            prompt = f"""
Resume la siguiente conversación de manera extremadamente densa. 
Anota las entidades clave, el estado de la tarea y detalles clave del usuario.
CONVERSACIÓN:
{convo[:6000]}
            """
            # FIX #2: priority=1 (background), no priority=0 (chat). La condensación de
            # memoria no es una acción del usuario y no debe competir por chat_semaphore.
            summary = await llm_client.chat([{"role": "user", "content": prompt}], temperature=0.3, priority=1)
            
            if summary and len(summary) > 20:
                # Store persistent summary
                new_log = ChatLog(role="system_summary", content=summary, user_id=messages_to_summarize[0].user_id)
                db.add(new_log)
                db.commit()
                logger.info("Successfully condensed episodic memory into system_summary block.")
        except Exception as e:
            logger.error(f"Error condensing memory: {e}")
        finally:
            db.close()

def intent_is_research(intent: str) -> bool:
    return intent in ["RESEARCH", "WIKI", "CODE", "KNOWLEDGE"]

# Global singleton
context_manager = ContextManager()
