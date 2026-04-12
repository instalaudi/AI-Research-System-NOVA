import json
import re
import asyncio
import time
import datetime
from typing import AsyncGenerator, List, Optional, Any
from fastapi import HTTPException
from core.llm_client import llm_client
from core.intent_classifier import classify_intent
from core.config import COGNITIVE_MODE, LLM_FAST_MODEL
from core.controller import cognitive_controller
from core.sandbox import sandbox
from core.prompts import (
    KNOWLEDGE_QUERY_PROMPT,
    ACTION_AGENT_PROMPT,
    SYSTEM_AUDIT_PROMPT,
    RAG_STREAM_PROMPT,
    RAG_STREAM_PROMPT_BODY,          # FIX: sin identidad duplicada para stream
    VISION_ANALYSIS_PROMPT,
    VISION_ANALYSIS_PROMPT_BODY,     # FIX: sin identidad duplicada para stream
    NOVA_IDENTITY_PROMPT,
)
from core.logging_config import get_logger, request_id_var
from services.memory_service import memory_service
from services.system_service import system_service
from core.cache import smart_cache
from core.guard import prompt_guard
from core.intent_classifier import classify_intent
from core.database import SessionLocal, UserProfile, Feedback

logger = get_logger("services.chat")

class ChatService:
    def __init__(self):
        pass

    async def handle_standard_query(self, query: str, images: Optional[List[str]], files_context: str, user_id: int, db: Any) -> dict:
        """
        Orchestrates a standard (non-streaming) query with Cache, Guard and Personalization.
        """
        start_time = time.time()
        
        # 1. Security Check (Prompt Guard)
        is_safe, reason = prompt_guard.is_safe(query)
        if not is_safe:
            await system_service.track_metric("errors_total")
            return {"query": query, "answer": f"🛡️ {reason}", "mode": "security_blocked"}

        # 1.5 Intent Routing (Vital for Voice Mode)
        intent = await classify_intent(query)
        if intent == "SYSTEM":
             audit_data = await system_service.get_full_system_audit(db)
             audit_json = json.dumps(audit_data, indent=2, ensure_ascii=False)
             system_instruction = SYSTEM_AUDIT_PROMPT.replace("{audit_json}", "Ver Datos de Usuario")
             user_data = f"DATOS DE AUDITORÍA RECIENTES:\n{audit_json}"
             
             llm_answer = await llm_client.chat([
                 {"role": "system", "content": system_instruction},
                 {"role": "user", "content": user_data}
             ], temperature=0.0, priority=0)
             
             answer = llm_answer.strip() if llm_answer else "Lo siento, hubo un error al obtener la auditoría del sistema."
             return {"query": query, "answer": answer, "mode": "system_audit", "needs_research": False}

        if intent == "PROJECT_BUILD":
            try:
                from core.task_queue import task_queue
                from core.database import ChatLog, ResearchJob
                
                # Acknowledge immediately in DB
                ack_msg = (
                    "¡Entendido! He aceptado el desafío. 🏗️\n\n"
                    "He iniciado la **construcción y auditoría de tu proyecto en segundo plano**. "
                    "Este es un proceso intensivo que requiere mi total atención de ingeniería para garantizar código de calidad.\n\n"
                    "**Puedes seguir chateando con otras dudas.** En cuanto el paquete ZIP esté listo y verificado, "
                    "enviaré el enlace de descarga directamente a este chat automáticamente."
                )
                db.add(ChatLog(user_id=user_id, role="assistant", content=ack_msg))
                db.commit()

                # Enqueue the background task
                # Priority 2: High priority for user requests
                await task_queue.add_task(
                    task_type="project_build", 
                    data={"query": query}, 
                    topic="Project Development", 
                    user_id=user_id
                )
                
                return {"query": query, "answer": ack_msg, "mode": "project_build", "needs_research": False}
            except Exception as e:
                err_msg = f"Hubo un error al intentar encolar la construcción: {e}"
                db.add(ChatLog(user_id=user_id, role="assistant", content=err_msg))
                db.commit()
                return {"query": query, "answer": err_msg, "mode": "project_build", "needs_research": False}

        # 2. Personalization (User Profile Injection)
        user_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        profile_context = ""
        if user_profile:
            profile_context = f"\n[PERFIL DEL USUARIO]: Preferences: {user_profile.preferences}, Topics: {user_profile.frequent_topics}\n"

        # 3. Cache Check
        cache_params = {"images": len(images) if images else 0, "personalization": bool(profile_context)}
        cached_res = smart_cache.get(query, llm_client.fast_model, cache_params, str(user_id))
        if cached_res:
            await system_service.track_metric("cache_hits")
            await system_service.track_metric("requests_total")
            return {"query": query, "answer": cached_res, "mode": "knowledge_search", "cached": True}
        
        await system_service.track_metric("cache_misses")

        # 4. Context Building
        context = await memory_service.build_rag_context("KNOWLEDGE", query, files_context, db)
        image_context = ""
        if images:
            image_context = f"\n\nIMÁGENES ADJUNTAS: {images}"
            
        current_time = datetime.datetime.now().strftime("%A %d de %B de %Y, %I:%M %p")
        # Localize manually if needed, but for now we'll use a helper or simple mapping if server is English
        days = {"Monday": "lunes", "Tuesday": "martes", "Wednesday": "miércoles", "Thursday": "jueves", "Friday": "viernes", "Saturday": "sábado", "Sunday": "domingo"}
        months = {"January": "enero", "February": "febrero", "March": "marzo", "April": "abril", "May": "mayo", "June": "junio", "July": "julio", "August": "agosto", "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"}
        for en, es in days.items(): current_time = current_time.replace(en, es)
        for en, es in months.items(): current_time = current_time.replace(en, es)

        prompt = KNOWLEDGE_QUERY_PROMPT.format(
            query=query, 
            context=context + profile_context, 
            image_context=image_context,
            files_context=files_context,
            current_time=current_time
        )
        
        # 5. LLM Execution
        try:
            llm_answer = await llm_client.chat([{"role": "user", "content": prompt}], priority=0)
            if not llm_answer or "INSUFFICIENT_KNOWLEDGE" in llm_answer.upper():
                return await self._format_research_fallback(query, llm_answer)
            
            answer = llm_answer.strip()
            
            # Update Cache (Solo si NO es un timeout alert)
            if "tardó demasiado" not in answer:
                smart_cache.set(query, llm_client.fast_model, cache_params, str(user_id), answer)
            
            latency = (time.time() - start_time) * 1000
            await system_service.track_metric("requests_total", 1)
            await system_service.track_metric("latency_acc", latency)
            
            logger.info({
                "event": "chat_standard",
                "latency_ms": latency,
                "user_id": user_id,
                "cache": "miss"
            })
            
            return {"query": query, "answer": answer, "mode": "knowledge_search", "needs_research": False}
        except Exception as e:
            logger.error(f"Standard query failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error generating response.")

    async def _format_research_fallback(self, query: str, llm_answer: Optional[str]) -> dict:
        short_topic = query[0:60]
        if llm_answer and ":" in llm_answer:
            short_topic = llm_answer.split(":", 1)[1].strip()[:60]
            
        return {
            "query": short_topic,
            "answer": f"No tengo suficiente información. ¿Investigamos sobre **{short_topic}**?",
            "mode": "knowledge_search",
            "needs_research": True
        }

    async def stream_orchestrator(self, query: str, images: Optional[List[str]], files_context: str, user_id: int, db: Any) -> AsyncGenerator[str, None]:
        """
        Main orchestrator for streaming responses with tool-use, intents, Cache and Guard.
        """
        start_time = time.time()
        request_id = request_id_var.get()

        # 1. Security Check
        is_safe, reason = prompt_guard.is_safe(query)
        if not is_safe:
            yield f"data: {json.dumps({'type': 'metadata', 'intent': 'SECURITY', 'request_id': request_id})}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'text': f'🛡️ {reason}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            system_service.track_metric("errors_total")
            return

        intent = await classify_intent(query)
        yield f"data: {json.dumps({'type': 'metadata', 'intent': intent, 'request_id': request_id})}\n\n"

        if intent == "SYSTEM":
             async for chunk in self._handle_system_intent(): yield chunk
             return

        if intent == "PROJECT_BUILD":
             yield f"data: {json.dumps({'type': 'chunk', 'text': '🛠️ Construyendo arquitectura y ejecutando pruebas de QA...'})}\\n\\n"
             try:
                 from agents.developer_agent import developer_agent
                 from core.project_manager import project_manager
                 
                 # Build with standard query context
                 files_dict = await developer_agent.build_project(query)
                 zip_path = project_manager.package_project(files_dict, "nova_project_" + str(user_id))
                 filename = zip_path.replace("\\\\", "/").split("/")[-1]
                 
                 build_msg = (
                     "\\n\\n¡El código ha pasado la fase de Auditoría y QA!\\n\\n"
                     "He empaquetado tu proyecto en formato ZIP. Descárgalo desde este enlace directo o simplemente haz click en él:\\n\\n"
                     f"👉 **[Descargar Proyecto 100% Funcional](/api/chat/download/{filename})**"
                 )
                 yield f"data: {json.dumps({'type': 'chunk', 'text': build_msg})}\\n\\n"
                 
                 # Save to chat log
                 db.add(ChatLog(user_id=user_id, role="assistant", content=build_msg, intent="PROJECT_BUILD"))
                 db.commit()
             except Exception as e:
                 err_msg = f"Inicié la construcción, pero el auditor detectó problemas o hubo un cuelgue matemático: {e}"
                 yield f"data: {json.dumps({'type': 'chunk', 'text': err_msg})}\\n\\n"
                 db.add(ChatLog(user_id=user_id, role="assistant", content=err_msg, intent="PROJECT_BUILD"))
                 db.commit()
             
             yield f"data: {json.dumps({'type': 'done'})}\\n\\n"
             return

        if intent == "RESEARCH":
             # Yield technical wait message ONLY for research
             yield f"data: {json.dumps({'type': 'chunk', 'text': 'Lo siento Ramon, estoy procesando tu peticion mas rapido para ti, dame un segundo...'})}\n\n"
             async for chunk in self._handle_research_intent(query): yield chunk
             return

        # 2. Personalization
        user_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        profile_context = ""
        if user_profile:
            profile_context = f"\n[USER_TRAITS]: {user_profile.persona_summary}\n"

        # 3. Cache Check (Playback enabled in v10.7.5)
        cache_params = {"stream": True, "personalization": bool(profile_context)}
        cached_res = smart_cache.get(query, llm_client.fast_model, cache_params, str(user_id))
        if cached_res:
            await system_service.track_metric("cache_hits")
            await system_service.track_metric("requests_total")
            
            async for chunk in self._playback_cached_response(cached_res):
                yield chunk
            return
        
        await system_service.track_metric("cache_misses")

        # 4. Context build
        knowledge_context = ""
        if intent != "CONVERSATION":
            knowledge_context = await memory_service.build_rag_context(intent, query, files_context, db)
        
        # Merge profile into context
        full_context = knowledge_context + profile_context
        
        # Choose client (Delegated to singleton model selection based on priority)
        # 0 is HIGH (Chat), using LLM_MODEL_NAME. 
        # Agents will use priority 1 or 2 which selects LLM_FAST_MODEL.

        # Time Localization for Stream
        current_time = datetime.datetime.now().strftime("%A %d de %B de %Y, %I:%M %p")
        days = {"Monday": "lunes", "Tuesday": "martes", "Wednesday": "miércoles", "Thursday": "jueves", "Friday": "viernes", "Saturday": "sábado", "Sunday": "domingo"}
        months = {"January": "enero", "February": "febrero", "March": "marzo", "April": "abril", "May": "mayo", "June": "junio", "July": "julio", "August": "agosto", "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"}
        for en, es in days.items(): current_time = current_time.replace(en, es)
        for en, es in months.items(): current_time = current_time.replace(en, es)

        # FIX CRÍTICO: Construir user_prompt SIN duplicar NOVA_IDENTITY_PROMPT.
        # FIX CRÍTICO: Usar _BODY (sin identidad) porque NOVA_IDENTITY_PROMPT
        # ya se envía 1 sola vez como system role abajo.
        prompt_tpl = VISION_ANALYSIS_PROMPT_BODY if images else RAG_STREAM_PROMPT_BODY
        user_prompt = prompt_tpl.format(
            query=query, 
            context=knowledge_context, 
            files_context=files_context,
            image_count=len(images or []) if images else 0,
            current_time=current_time
        )

        full_response = ""  # Inicializado correctamente antes de cualquier lgica pesada
        full_response_prefix = "[VISTO POR NOVA 👁️] " if images else ""
        
        # FIX: System role lleva SOLO la identidad (1 vez). User role lleva la consulta.
        # Esto da separación limpia sin duplicación.
        messages = [
            {"role": "system", "content": NOVA_IDENTITY_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            yield f"data: {json.dumps({'type': 'meta', 'results_count': 1})}\n\n"
            
            async for chunk in llm_client.chat_stream(messages, images=images, priority=0):
                if not full_response and full_response_prefix:
                    full_response = full_response_prefix
                full_response += chunk
                
                # Check for insufficient knowledge early (simple logic)
                if not images and "INSUFFICIENT_KNOWLEDGE" in full_response.upper():
                    async for f_chunk in self._handle_insufficient_knowledge(query, full_response): yield f_chunk
                    return

                # Tool use detection (Regex robusto v10.7.0)
                if re.search(r"</execute_(python|js)>", full_response):
                    full_response = await self._handle_tool_execution(full_response, messages, llm_client)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': full_response})}\n\n"
                    break

                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

            # Reflection (Critic) - Only for serious intents (Skip for pure CONVERSATION)
            if intent in ["RESEARCH", "KNOWLEDGE", "CODE"]:
                reflection = await cognitive_controller.verify_response(full_response, knowledge_context)
                if reflection.get("has_errors") and reflection.get("corrections"):
                    correction = f"\n\n> [!WARNING]\n> **Auto-Corrección**: {reflection['corrections']}"
                    yield f"data: {json.dumps({'type': 'chunk', 'text': correction})}\n\n"
                    full_response += correction

            # Update cache with full response
            smart_cache.set(query, llm_client.fast_model, cache_params, str(user_id), full_response)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
            latency = (time.time() - start_time) * 1000
            await system_service.track_metric("requests_total", 1)
            await system_service.track_metric("latency_acc", latency)
            
            logger.info({
                "event": "chat_stream_complete",
                "latency_ms": latency,
                "intent": intent,
                "user_id": user_id
            })

        except Exception as e:
            logger.error(f"Stream generation error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        finally:
            # Final persistence in the service layer handled here or by router
            # v10.7.0: Wrapper seguro para evitar NameError y asegurar ejecucin
            try:
                if 'full_response' not in locals(): full_response = "Error de generacin"
                asyncio.create_task(self._safe_store_memory(user_id, query, full_response))
            except Exception as e:
                logger.error(f"Failed to launch background storage: {e}")

    async def _safe_store_memory(self, user_id: int, query: str, full_response: str):
        """Wrapper seguro para almacenamiento en segundo plano."""
        try:
            await memory_service.store_chat_message("user", query, user_id)
            await memory_service.store_chat_message("assistant", full_response, user_id)
        except Exception as e:
            logger.error(f"Safe store memory failed: {e}")

    async def _handle_system_intent(self) -> AsyncGenerator[str, None]:
        """
        v10.6.3: High-Precision Self-Awareness Layer. 
        Uses system messages and zero-temperature for data reliability.
        """
        db = SessionLocal()
        try:
            audit_data = await system_service.get_full_system_audit(db)
            audit_json = json.dumps(audit_data, indent=2, ensure_ascii=False)
            
            # v10.6.3: Separation of instruction and data
            # Place the formatting instructions in the "system" role for maximum weight
            system_instruction = SYSTEM_AUDIT_PROMPT.replace("{audit_json}", "Ver Datos de Usuario")
            user_data = f"DATOS DE AUDITORÍA REALES A PROCESAR:\n{audit_json}"
            
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_data}
            ]
            
            # Force temperature=0.0 to prevent any identity-based "fluff" or hallucinations
            async for chunk in llm_client.chat_stream(messages, temperature=0.0, priority=0):
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"System audit failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'text': 'Error en auditoría interna.'})}\n\n"
        finally:
            db.close()

    async def _handle_research_intent(self, query: str) -> AsyncGenerator[str, None]:
        short_topic = query[0:60]
        answer = f"💡 Detecto que esto requiere investigación profunda sobre '{short_topic}'."
        yield f"data: {json.dumps({'type': 'fallback', 'text': answer, 'needs_research': True, 'query': short_topic})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    async def _handle_insufficient_knowledge(self, query: str, full_response: str) -> AsyncGenerator[str, None]:
        short_topic = query[0:40] # Simplification
        answer = f"No tengo suficiente información. ¿Investigamos sobre {short_topic}?"
        yield f"data: {json.dumps({'type': 'fallback', 'text': answer, 'needs_research': True, 'query': short_topic})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    def process_feedback(self, db: Any, user_id: int, message_id: Optional[int], rating: str):
        """
        Stores user feedback and adjusts context weight in the long term.
        """
        try:
            fb = Feedback(user_id=user_id, message_id=message_id, rating=rating)
            db.add(fb)
            db.commit()
            logger.info(f"Feedback {rating} stored for user {user_id}")
            
            if rating == "bad":
                # Logic to penalize context relevance could go here
                logger.info("Feedback was bad. Future context ranking might be adjusted.")
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}")

    def get_consolidated_profile(self, db: Any, user_id: int) -> dict:
        """
        Retrieves the consolidated persistent profile of a user.
        """
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            # Bootstrap if doesn't exist
            profile = UserProfile(user_id=user_id, preferences="[]", frequent_topics="[]")
            db.add(profile)
            db.commit()
            db.refresh(profile)
        
        return {
            "preferences": json.loads(profile.preferences),
            "topics": json.loads(profile.frequent_topics),
            "summary": profile.persona_summary
        }

    async def _handle_tool_execution(self, full_response: str, messages: list, client: Any) -> str:
        # Simplified tool execution logic
        match = re.search(r"<(execute_python|execute_js)>(.*?)</\1>", full_response, re.DOTALL)
        if not match: return full_response
        
        tag, code = match.group(1), match.group(2).strip()
        result = await sandbox.execute_python(code) if "python" in tag else await sandbox.execute_js(code)
        
        obs_prompt = ACTION_AGENT_PROMPT.format(observation=f"SALIDA: {result['stdout']}\nERRORES: {result['stderr']}")
        messages.append({"role": "assistant", "content": full_response})
        messages.append({"role": "user", "content": obs_prompt})
        
        final_response = ""
        async for chunk in client.chat_stream(messages):
            final_response += chunk
        return final_response

    async def _playback_cached_response(self, text: str) -> AsyncGenerator[str, None]:
        """
        Simulates streaming for a cached response to maintain UI flow.
        """
        import random
        # Split into small logical chunks (1-3 words)
        words = text.split(" ")
        i = 0
        while i < len(words):
            chunk_size = random.randint(1, 3)
            chunk = " ".join(words[i:i+chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
            i += chunk_size
            await asyncio.sleep(random.uniform(0.01, 0.03))
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

chat_service = ChatService()
