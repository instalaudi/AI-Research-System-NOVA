import json
import re
import asyncio
import time
import datetime
import hashlib
from typing import AsyncGenerator, List, Optional, Any
from fastapi import HTTPException, BackgroundTasks
from core.llm_client import llm_client
from core.llm_gateway import llm_gateway
from core.intent_classifier import classify_intent
from core.config import COGNITIVE_MODE, LLM_FAST_MODEL
from core.controller import cognitive_controller
from core.sandbox import sandbox
from core.tts_engine import nova_voice
from core.prompts import (
    KNOWLEDGE_QUERY_PROMPT_BODY,     # v12.1.6: Sin identidad redundante
    ACTION_AGENT_PROMPT,
    SYSTEM_AUDIT_PROMPT,
    RAG_STREAM_PROMPT,
    RAG_STREAM_PROMPT_BODY,          # FIX: sin identidad duplicada para stream
    VISION_ANALYSIS_PROMPT,
    VISION_ANALYSIS_PROMPT_BODY,     # FIX: sin identidad duplicada para stream
    NOVA_IDENTITY_PROMPT,
    NOVA_IDENTITY_COMPACT,
    NOVA_LEARNING_SUMMARY_PROMPT,
)

from core.logging_config import get_logger, request_id_var
from services.memory_service import memory_service
from services.system_service import system_service
from core.task_queue import task_queue
from core.cache import smart_cache
from core.guard import prompt_guard
from core.intent_classifier import classify_intent
from core.database import SessionLocal, UserProfile, Feedback, ChatLog, ApprovalRequest, KnowledgeEntry
from core.project_manager import project_manager
from core.config import ENABLE_AUTO_GIT_VERSIONING
from core.git_versioning import git_versioning
from core.skill_manager import skill_manager
from core.tool_executor import tool_executor

# v13.9.1 CRÍTICO FIX: State global reemplazado por BD con transacciones ACID
# El diccionario global causaba race conditions en multi-usuario
# AHORA: Usar tabla ApprovalRequest en SQLite



logger = get_logger("services.chat")

class ChatService:
    def __init__(self):
        pass

    async def handle_standard_query(self, query: str, images: Optional[List[str]], files_context: str, user_id: int, db: Any, mode: str = "auto", background_tasks: Optional[BackgroundTasks] = None) -> dict:
        """
        Orchestrates a standard (non-streaming) query with Cache, Guard and Personalization.
        """
        system_service.record_user_activity()
        start_time = time.time()
        
        # v11.9.7: Background Memory Extraction (Goldfish Fix)
        # Removido (v13.9.5): Se causaba doble extracción porque ya se extrae al final de la función
        if background_tasks:
            request_id = request_id_var.get()

        # v11.9.23: Human-in-the-Loop para Standard Query (Aprobación de herramientas)
        pending_req = db.query(ApprovalRequest).filter_by(user_id=user_id).first()
        if pending_req:
            approval_query = query.lower().strip()
            if any(x in approval_query for x in ["si", "yes", "aceptar", "dale", "autorizo", "procede"]):
                # Para consultas standard (no stream), usamos un generador interno y capturamos el resultado final
                answer = ""
                async for chunk in self._execute_pending_tool(user_id, db):
                    try:
                        data_chunk = json.loads(chunk.replace("data: ", ""))
                        if data_chunk.get("type") == "chunk":
                            answer += data_chunk.get("text", "")
                    except: continue
                return {"query": query, "answer": answer.strip(), "mode": "tool_execution", "needs_research": False}
            elif any(x in approval_query for x in ["no", "cancelar", "detente", "abortar"]):
                db.delete(pending_req)
                db.commit()
                return {"query": query, "answer": "Entendido. He cancelado la ejecución de la herramienta.", "mode": "chat"}

        # 1. Security Check (Prompt Guard)
        is_safe, reason = prompt_guard.is_safe(query)
        if not is_safe:
            await system_service.track_metric("errors_total")
            return {"query": query, "answer": f"🛡️ {reason}", "mode": "security_blocked"}

        # 1.5 Intent Routing (Vital para Voice Mode)
        if mode == "auto":
            intent = await classify_intent(query)
        else:
            intent = mode.upper()
            if intent == "BUILD": intent = "PROJECT_BUILD"

        if intent == "CONVERSATION" and images:
            intent = "KNOWLEDGE"
        if intent == "SYSTEM":
             audit_data = await system_service.get_full_system_audit(db)
             audit_json = json.dumps(audit_data, indent=2, ensure_ascii=False)
             system_instruction = SYSTEM_AUDIT_PROMPT.replace("{audit_json}", "Ver Datos de Usuario")
             user_data = f"DATOS DE AUDITORÍA RECIENTES:\n{audit_json}"
             
             llm_answer = await llm_gateway.chat([
                 {"role": "system", "content": system_instruction},
                 {"role": "user", "content": user_data}
             ], lane="realtime", temperature=0.0, priority=0)
             
             answer = llm_answer.strip() if llm_answer else "Lo siento, hubo un error al obtener la auditoría del sistema."
             return {"query": query, "answer": answer, "mode": "system_audit", "needs_research": False}

        # 1.6 Identity Query Check (v13.9.2: Responder directamente a "¿Quién eres?")
        query_lower = query.lower()
        identity_patterns = [
            r"quie?n\s+(?:eres|es|soy)",
            r"qui[eé]n\s+te\s+cre[oó]",
            r"qu[eé]\s+eres",
            r"tu\s+identidad",
            r"cu[ée]l\s+es\s+tu\s+nombre"
        ]
        if any(re.search(pat, query_lower) for pat in identity_patterns):
            identity_answer = (
                "Soy **NOVA**, un Sistema Autónomo de IA para Investigación (Autonomous Research AI System).\n\n"
                "**Creador:** Juan Ramón\n"
                "**Versión:** v13.9.1 - \"Sensory Awareness & Neural Voice\"\n"
                "**Stack:** FastAPI + Next.js + ChromaDB + Ollama + LightRAG\n\n"
                "Mi propósito es colaborar contigo en investigación autónoma, desarrollo de proyectos y análisis profundo. "
                "Tengo acceso a múltiples agentes especializados: Planner, Explorer, Analyzer, Critic, Verifier, Librarian y Browser.\n\n"
                "¿Qué necesitas que investiguemos hoy?"
            )
            return {"query": query, "answer": identity_answer, "mode": "identity_query"}
        
        # 1.7 Tool Use Prevention (v13.6.4: Protejer contra mal uso en saludos)
        general_query_patterns = [
            "que sabes", "que has aprendido", "dime que aprendiste", "hola",
            "quien eres", "quien soy", "en que estamos trabajando",
            "cual es mi nombre", "que estamos haciendo", "como estas",
            "qué tal", "buenos dias", "saludos"
        ]
        is_social_only = len(query.split()) <= 12 and any(x in query_lower for x in ["hola", "buenos dias", "quien eres", "como estas", "qué tal", "saludos"])
        is_general_query = any(x in query_lower for x in general_query_patterns) or (intent == "CONVERSATION")

        # ── INTENCIÓN VISION (Cámara web / Pantalla) ──
        if intent == "VISION" or any(kw in query_lower for kw in ["webcam", "web cam", "cámara", "camara"]):
            try:
                from services.vision_service import vision_service
                import asyncio
                
                is_screen = "pantalla" in query_lower
                if is_screen:
                    cap_res = await asyncio.to_thread(vision_service.capture_screen)
                else:
                    cap_res = await asyncio.to_thread(vision_service.capture_webcam)

                if cap_res.get("b64"):
                    b64_img = cap_res.get("b64")
                    v_prompt = f"Describe what is shown in this {'screen' if is_screen else 'webcam'} image in detail. Identify any people, expressions, objects, text, and surroundings."
                    raw_vision = await llm_gateway.chat(
                        [{"role": "user", "content": v_prompt}],
                        lane="realtime",
                        images=[b64_img],
                        priority=0,
                        agent_name="vision"
                    )
                    v_answer = raw_vision.strip() if raw_vision else "Capturé la imagen de la cámara web, pero el modelo de visión no generó una respuesta."
                    if raw_vision and len(raw_vision.strip()) > 5:
                        try:
                            translation = await llm_gateway.chat(
                                [
                                    {"role": "system", "content": "Eres el asistente de visión de NOVA. Transmite en español natural, fluido y conciso lo que se ve en la cámara web a partir del análisis visual."},
                                    {"role": "user", "content": f"El usuario preguntó: '{query}'. Análisis visual: '{raw_vision}'. Respóndele en español."}
                                ],
                                lane="fast",
                                priority=0,
                                agent_name="planner"
                            )
                            if translation and len(translation.strip()) > 5:
                                v_answer = translation.strip()
                        except Exception:
                            pass
                    
                    db.add(ChatLog(user_id=user_id, role="assistant", content=v_answer, intent="VISION"))
                    db.commit()
                    return {"query": query, "answer": v_answer, "mode": "vision", "needs_research": False}

                else:
                    v_err = "No pude acceder a la cámara web en este momento. Asegúrate de que no esté siendo utilizada por otra aplicación."
                    db.add(ChatLog(user_id=user_id, role="assistant", content=v_err, intent="VISION"))
                    db.commit()
                    return {"query": query, "answer": v_err, "mode": "vision", "needs_research": False}
            except Exception as e:
                logger.error(f"[ChatService] Error procesando intención VISION: {e}")

        if intent == "PROJECT_BUILD":

            try:
                # v11.9.18: Removed brevity check. We now trust the smarter IntentClassifier 
                # to distinguish between social chat and direct action commands.
                # v11.9.24: Check for active builds to prevent resource exhaustion
                if system_service.has_active_builds(window_minutes=15):
                    busy_msg = (
                        "⚠️ Ya tengo una tarea de construcción o auditoría pesada en progreso.\n\n"
                        "Para no saturar el sistema y mantener mi velocidad de respuesta, por favor espera a que termine "
                        "la tarea actual antes de iniciar una nueva. ¡Gracias por tu paciencia!"
                    )
                    return {"query": query, "answer": busy_msg, "mode": "system_busy", "needs_research": False}

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

                # Register build activity to block others
                system_service.record_build_activity()

                # Enqueue the background task
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
        
        # v13.0: Inyección de Memoria Persistente JSON
        json_memory_context = memory_service.get_formatted_json_memory()
        profile_context += f"\n{json_memory_context}\n"

        # 3. Cache Check (Bypass for attachments)
        has_attachments = bool(images) or bool(files_context)
        
        # v12.1.6: Patrones que NUNCA deben usar cache para evitar "ecos" de alucinaciones
        no_cache_keywords = ["qué has aprendido", "que sabes", "resumen de lo aprendido", "conocimiento acumulado"]
        skip_cache = any(kw in query.lower() for kw in no_cache_keywords)

        if has_attachments or skip_cache:
            cached_res = None
            cache_params = {}
        else:
            cache_params = {"images": 0, "personalization": bool(profile_context)}
            cached_res = smart_cache.get(query, llm_client.fast_model, cache_params, str(user_id))
            
        if cached_res:
            await system_service.track_metric("cache_hits")
            await system_service.track_metric("requests_total")
            return {"query": query, "answer": cached_res, "mode": "knowledge_search", "cached": True}
        
        if not has_attachments:
            await system_service.track_metric("cache_misses")

        # v11.8.0: FAST LANE en Standard Query
        # v13.9.5 FIX: Usar NOVA_IDENTITY_COMPACT para CONVERSATION para liberar tokens
        system_id = NOVA_IDENTITY_COMPACT if intent == "CONVERSATION" else NOVA_IDENTITY_PROMPT
        
        # v12.1.6: Usar prompt de resumen de aprendizaje cuando el usuario pregunta qué ha aprendido
        _LEARNING_SUMMARY_PATTERNS = [
            r"qu[ée]\s+.*(?:has|as|sabes|aprendiste|aprendido|nuevo|conocimiento)",
            r"resume\s+lo\s+(que|aprendido|acumulado)",
            r"cu[ée]ntame\s+(que|lo que)\s+(?:has|as)\s+aprendido",
            r"qu[ée]\s+conocimiento\s+tienes",
            r"aprendido\s+hoy",
            r"qu[eé]\s+nuevas?\s+cosas",
            r"que\s+hay\s+de\s+nuevo"
        ]
        
        is_learning_summary = any(re.search(pat, query, re.I) for pat in _LEARNING_SUMMARY_PATTERNS)
        if is_learning_summary:
            # Para resumen de aprendizaje, usar prompt especializado
            system_id = NOVA_LEARNING_SUMMARY_PROMPT


        # Omitir RAG pesado si es chat social
        context = ""
        if intent != "CONVERSATION" or is_learning_summary:
            context = await memory_service.build_rag_context("KNOWLEDGE", query, files_context, db)
            if is_learning_summary:
                # Recuperar temas recientes para responder con total precisión
                try:
                    recent_entries = db.query(KnowledgeEntry).order_by(KnowledgeEntry.created_at.desc()).limit(5).all()
                    if recent_entries:
                        topics_list = "\n".join([f"- **{e.topic}** (Confianza: {int((e.confidence_score or 0.8)*100)}%): {e.summary[:180]}..." for e in recent_entries])
                        context += f"\n\n### INVESTIGACIONES Y CONOCIMIENTO RECIENTE APRENDIDO:\n{topics_list}\n"
                except Exception:
                    pass

            
        current_time = datetime.datetime.now().strftime("%A %d de %B de %Y, %I:%M %p")
        # Localize manually 
        days = {"Monday": "lunes", "Tuesday": "martes", "Wednesday": "miércoles", "Thursday": "jueves", "Friday": "viernes", "Saturday": "sábado", "Sunday": "domingo"}
        months = {"January": "enero", "February": "febrero", "March": "marzo", "April": "abril", "May": "mayo", "June": "junio", "July": "julio", "August": "agosto", "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"}
        for en, es in days.items(): current_time = current_time.replace(en, es)
        for en, es in months.items(): current_time = current_time.replace(en, es)
 
        # v11.9.22: Skill Injection (Universal para que NOVA no alucine sobre su entorno)
        active_skills = ["terminal_skill", "browser_navigation_skill"]
        skills_context = ""
        if intent != "CONVERSATION":
            skills_context = skill_manager.get_active_skills_context(active_skills)
 
        # v13.9.5 FIX CRÍTICO: Inyectar historial de conversación previa
        chat_history = memory_service.get_recent_chat_history(user_id, db, num_turns=5)
        
        # Construcción de mensajes final
        if intent == "CONVERSATION":
            # v13.8.16: Incluir contexto de archivos incluso en charla social para evitar que NOVA ignore adjuntos
            user_content = query
            if files_context:
                user_content = f"{files_context}\n\nMENSAJE DEL USUARIO: {query}"
            
            messages = [
                {"role": "system", "content": system_id + skills_context}
            ]
            # Inyectar historial
            messages.extend(chat_history)
            messages.append({"role": "user", "content": user_content})
        else:
            prompt = KNOWLEDGE_QUERY_PROMPT_BODY.format(
                query=query, 
                context=context + profile_context + skills_context, 
                image_context="", 
                files_context=files_context,
                current_time=current_time
            )
            messages = [{"role": "system", "content": system_id}]
            # Inyectar historial
            messages.extend(chat_history)
            messages.append({"role": "user", "content": prompt})
        
        # 5. LLM Execution
        try:
            # v11.9.7: Pasamos images=images nativamente para que Llava funcione
            llm_answer = await llm_gateway.chat(messages, lane="realtime", priority=0, images=images)
            
            # v11.9.23: Detect Tool Call in Standard Chat
            if llm_answer:
                # Extraer bloque JSON asumiendo que el LLM puede incluir explicaciones antes
                
                # Buscar cualquier cosa que parezca un JSON de tool
                if '"tool"' in llm_answer:
                    json_match = re.search(r'\{[\s\S]*?"tool"\s*:\s*"([^"]+)"[\s\S]*?\}', llm_answer)
                    if json_match:
                        try:
                            # Limpiar posibles comillas de markdown
                            raw_json = json_match.group()
                            tool_data = json.loads(raw_json, strict=False)
                            tool_name = tool_data.get("tool")
                            text_before = llm_answer[:json_match.start()].replace('```json', '').replace('```', '').strip()
                            
                            # 1. Detect Terminal
                            if tool_name == "terminal" and "command" in tool_data:
                                command = tool_data["command"]
                                db.query(ApprovalRequest).filter_by(user_id=user_id).delete()
                                new_req = ApprovalRequest(
                                    user_id=user_id,
                                    tool="terminal",
                                    data=json.dumps({"command": command}),
                                    original_query=query
                                )
                                db.add(new_req)
                                db.commit()
                                msg = f"{text_before}\n\n" if text_before else ""
                                formatted_command = "\n".join(f"> {line}" for line in str(command).splitlines())
                                msg += (
                                    f"> [!CAUTION]\n"
                                    f"> **NOVA solicita ejecutar un comando de terminal:**\n"
                                    f">\n"
                                    f"> ```bash\n"
                                    f"{formatted_command}\n"
                                    f"> ```\n"
                                    f">\n"
                                    f"> *¿Autorizas esta acción? (Escribe **Sí** para proceder o **No** para cancelar)*"
                                )
                                return {"query": query, "answer": msg, "mode": "tool_approval", "needs_research": False}
                            
                            # 2. Detect Browser
                            elif tool_name == "browser" and "objective" in tool_data:
                                objective = tool_data["objective"]
                                db.query(ApprovalRequest).filter_by(user_id=user_id).delete()
                                new_req = ApprovalRequest(
                                    user_id=user_id,
                                    tool="browser",
                                    data=json.dumps({"objective": objective}),
                                    original_query=query
                                )
                                db.add(new_req)
                                db.commit()
                                msg = f"{text_before}\n\n" if text_before else ""
                                msg += (
                                    f"> [!IMPORTANT]\n"
                                    f"> **NOVA solicita usar el Navegador Autónomo:**\n"
                                    f"> **Objetivo:** {objective}\n"
                                    f"> *¿Autorizas esta acción? (Escribe **Sí** para proceder o **No** para cancelar)*"
                                )
                                return {"query": query, "answer": msg, "mode": "tool_approval", "needs_research": False}
                        except Exception as e:
                            pass # Fallback a texto plano si falla el parseo

            # v11.9.8: Explicit Memory Confirmation (moved to background to avoid blocking)
            memory_confirmed = ""
            # Buscamos patrones de memoria en la query original para encolar extracción en background
            from core.intent_classifier import _MEMORY_TRIGGERS
            if any(re.search(pat, query, re.I) for pat in _MEMORY_TRIGGERS) or intent == "KNOWLEDGE":
                try:
                    if background_tasks:
                        background_tasks.add_task(memory_service.extract_and_store_memory, query, user_id)
                    else:
                        asyncio.create_task(memory_service.extract_and_store_memory(query, user_id))
                except Exception:
                    # Fallback silencioso: si no podemos encolar, no bloqueamos la respuesta
                    pass

            if not llm_answer or "INSUFFICIENT_KNOWLEDGE" in llm_answer.upper():
                return await self._format_research_fallback(query, llm_answer)
            
            answer = llm_answer.strip() + memory_confirmed
            
            # Update Cache (Solo si NO es un timeout alert y no hay adjuntos)
            if "tardó demasiado" not in answer and not has_attachments:
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

    async def stream_orchestrator(self, query: str, images: Optional[List[str]], files_context: str, user_id: int, db: Any, mode: str = "auto", background_tasks: Optional[BackgroundTasks] = None) -> AsyncGenerator[str, None]:
        """
        Main orchestrator for streaming responses with tool-use, intents, Cache and Guard.
        """
        system_service.record_user_activity()
        start_time = time.time()
        request_id = request_id_var.get()

        # v11.9.7: Background Memory Extraction (Goldfish Fix)
        # Removido (v13.9.5): Se extrae explícitamente al final del stream

        # v11.9.22: Human-in-the-Loop - Verificar si el usuario respondió a una aprobación pendiente
        pending_req = db.query(ApprovalRequest).filter_by(user_id=user_id).first()
        if pending_req:
            approval_query = query.lower().strip()
            if any(x in approval_query for x in ["si", "yes", "aceptar", "dale", "autorizo", "procede"]):
                async for chunk in self._execute_pending_tool(user_id, db): yield chunk
                return
            elif any(x in approval_query for x in ["no", "cancelar", "detente", "abortar"]):
                db.delete(pending_req)
                db.commit()
                yield f"data: {json.dumps({'type': 'chunk', 'text': '❌ Acción cancelada por el usuario. ¿En qué más puedo ayudarte?'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

        # 1. Security Check
        is_safe, reason = prompt_guard.is_safe(query)
        if not is_safe:
            yield f"data: {json.dumps({'type': 'metadata', 'intent': 'SECURITY', 'request_id': request_id})}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'text': f'🛡️ {reason}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            await system_service.track_metric("errors_total")
            return

        # 1.5 Intent Classification
        if mode == "auto":
            intent = await classify_intent(query)
        else:
            intent = mode.upper()
            if intent == "BUILD": intent = "PROJECT_BUILD"
            
        if intent == "CONVERSATION" and images:
            intent = "KNOWLEDGE"
        yield f"data: {json.dumps({'type': 'metadata', 'intent': intent, 'request_id': request_id})}\n\n"

        if intent == "SYSTEM":
             async for chunk in self._handle_system_intent(): yield chunk
             return

        if intent == "PROJECT_BUILD":
             yield f"data: {json.dumps({'type': 'chunk', 'text': '🛠️ Construyendo arquitectura y ejecutando pruebas de QA...'})}\n\n"

             try:
                 from agents.developer_agent import developer_agent
                 # Build with standard query context
                 files_dict = await developer_agent.build_project(query, user_id=user_id, db_session=db)
                 snapshot_path = project_manager.save_project_snapshot(
                     files_dict,
                     project_name=f"snapshot_user_{user_id}"
                 )
                 zip_path = project_manager.package_project(files_dict, "nova_project_" + str(user_id))
                 filename = zip_path.replace("\\\\", "/").split("/")[-1]
                 
                 # Extract project name for display
                 project_display_name = filename.replace('.zip', '').replace(f'nova_project_{user_id}_', '')
                 
                 build_msg = (
                     "\n\n¡El código ha pasado la fase de Auditoría y QA!\n\n"
                     f"✅ Proyecto '{project_display_name}' creado exitosamente.\n\n"
                     "👉 **Ve a la pestaña 'Proyectos' para descargarlo.**\n\n"
                     f"📁 Archivo: {filename}"
                 )

                 if ENABLE_AUTO_GIT_VERSIONING:
                     git_result = git_versioning.auto_commit_paths(
                         paths=[snapshot_path],
                         message=f"auto(project): stream snapshot user {user_id} - {query[:72]}"
                     )
                     if git_result.get("status") == "committed":
                         build_msg += "\n\n🧾 Snapshot versionado automáticamente en Git."
 
                 yield f"data: {json.dumps({'type': 'chunk', 'text': build_msg})}\n\n"
                 
                 # Save to chat log
                 db.add(ChatLog(user_id=user_id, role="assistant", content=build_msg, intent="PROJECT_BUILD"))
                 db.commit()
             except Exception as e:
                 err_msg = f"Inicié la construcción, pero el auditor detectó problemas o hubo un cuelgue matemático: {e}"
                 yield f"data: {json.dumps({'type': 'chunk', 'text': err_msg})}\n\n"
                 db.add(ChatLog(user_id=user_id, role="assistant", content=err_msg, intent="PROJECT_BUILD"))
                 db.commit()
             
             yield f"data: {json.dumps({'type': 'done'})}\n\n"
             return


        if intent == "RESEARCH":
             # Yield technical wait message ONLY for research
             yield f"data: {json.dumps({'type': 'chunk', 'text': 'Lo siento Ramon, estoy procesando tu peticion mas rapido para ti, dame un segundo...'})}\n\n"
             async for chunk in self._handle_research_intent(query): yield chunk
             return

        # 2. Personalization
        word_count = len(query.split())
        user_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        profile_context = ""
        if user_profile:
            profile_context = f"\n[USER_TRAITS]: {user_profile.persona_summary}\n"
        
        # v13.0: Inyección de Memoria Persistente JSON (Stream)
        json_memory_context = memory_service.get_formatted_json_memory()
        profile_context += f"\n{json_memory_context}\n"

        # 3. Cache Check (Playback enabled in v10.7.5, bypass for attachments)
        has_attachments = bool(images) or bool(files_context)
        
        # v12.1.5: Patrones que NUNCA deben usar cache para evitar "ecos" de alucinaciones
        no_cache_keywords = ["qué has aprendido", "que sabes", "resumen de lo aprendido", "conocimiento acumulado"]
        skip_cache = any(kw in query.lower() for kw in no_cache_keywords)

        if has_attachments or skip_cache:
            cached_res = None
            cache_params = {}
        else:
            cache_params = {"stream": True, "personalization": bool(profile_context)}
            cached_res = smart_cache.get(query, llm_client.fast_model, cache_params, str(user_id))
            
        if cached_res:
            await system_service.track_metric("cache_hits")
            await system_service.track_metric("requests_total")
            
            async for chunk in self._playback_cached_response(cached_res):
                yield chunk
            return
        
        if not has_attachments:
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
        
        # v11.8.0: FAST LANE - Usar identidad minimalista para conversaciones sociales
        # para reducir el tiempo de respuesta en CPU.
        # v13.9.5 FIX: Aplicar NOVA_IDENTITY_COMPACT también para CONVERSATION intent
        # para liberar tokens para historial y RAG
        system_id = NOVA_IDENTITY_COMPACT if intent == "CONVERSATION" else NOVA_IDENTITY_PROMPT
        
        # v12.1.6: Usar prompt de resumen de aprendizaje cuando el usuario pregunta qué ha aprendido
        _LEARNING_SUMMARY_PATTERNS = [
            r"qu[ée]\s+.*(?:has|as|sabes|aprendiste|aprendido|nuevo|conocimiento)",
            r"resume\s+lo\s+(que|aprendido|acumulado)",
            r"cu[ée]ntame\s+(que|lo que)\s+(?:has|as)\s+aprendido",
            r"qu[ée]\s+conocimiento\s+tienes",
            r"aprendido\s+hoy",
            r"qu[eé]\s+nuevas?\s+cosas",
            r"que\s+hay\s+de\s+nuevo"
        ]
        
        is_learning_summary = any(re.search(pat, query, re.I) for pat in _LEARNING_SUMMARY_PATTERNS)
        if is_learning_summary:
            # Para resumen de aprendizaje, usar prompt especializado
            system_id = NOVA_LEARNING_SUMMARY_PROMPT
            try:
                recent_entries = db.query(KnowledgeEntry).order_by(KnowledgeEntry.created_at.desc()).limit(5).all()
                if recent_entries:
                    topics_list = "\n".join([f"- **{e.topic}** (Confianza: {int((e.confidence_score or 0.8)*100)}%): {e.summary[:200]}..." for e in recent_entries])
                    knowledge_context += f"\n\n### INVESTIGACIONES Y CONOCIMIENTO RECIENTE APRENDIDO POR TI (NOVA):\n{topics_list}\n(Explica a Juan Ramón estos temas que tú como NOVA has aprendido e investigado recientemente)."
            except Exception:
                pass

        # Re-construir user_prompt con el knowledge_context enriquecido
        prompt_tpl = VISION_ANALYSIS_PROMPT_BODY if images else RAG_STREAM_PROMPT_BODY
        user_prompt = prompt_tpl.format(
            query=query, 
            context=knowledge_context, 
            files_context=files_context,
            image_count=len(images or []) if images else 0,
            current_time=current_time
        )

        
        # En el carril rápido, enviamos la query cruda sin el template largo de RAG
        # para ahorrar otros ~200 tokens de prefill.
        # v13.8.16: Incluir contexto de archivos incluso en charla social
        final_user_content = query
        if intent == "CONVERSATION" and not is_learning_summary:
            if files_context:
                final_user_content = f"{files_context}\n\nMENSAJE DEL USUARIO: {query}"
        else:
            final_user_content = user_prompt


        # v11.9.22: Skill Injection en Stream (Universal)
        active_skills = ["terminal_skill", "browser_navigation_skill"]
        skills_context = ""
        if intent != "CONVERSATION":
            skills_context = skill_manager.get_active_skills_context(active_skills)

        # v13.9.5 FIX CRÍTICO: Inyectar historial de conversación previa
        # En lugar de solo [system, user], ahora usamos [system, ...history, user]
        chat_history = memory_service.get_recent_chat_history(user_id, db, num_turns=5)
        
        messages = [
            {"role": "system", "content": system_id + skills_context}
        ]
        # Inyectar historial previo (evitar duplicar el último turno si está en cache)
        messages.extend(chat_history)
        # Finalmente, añadir el mensaje actual del usuario
        messages.append({"role": "user", "content": final_user_content})
        
        try:
            yield f"data: {json.dumps({'type': 'meta', 'results_count': 1})}\n\n"
            
            # v13.7.2: Buffers para Audio Streaming (Fase 2)
            sentence_buffer = ""
            
            async for chunk in llm_gateway.chat_stream(messages, lane="realtime", images=images, priority=0):
                if not full_response and full_response_prefix:
                    full_response = full_response_prefix
                full_response += chunk
                
                # --- Lógica de Audio Streaming (Sentencia por Sentencia) ---
                sentence_buffer += chunk
                # Detectar fin de frase: punto, exclamación o interrogación seguidos de espacio o fin de línea
                if any(punct in sentence_buffer for punct in [". ", "! ", "? ", ".\n", "!\n", "?\n"]):
                    # Dividir buffer en sentencias completas
                    parts = re.split(r'(?<=[.!?])\s+', sentence_buffer)
                    if len(parts) > 1:
                        to_speak = parts[:-1]
                        sentence_buffer = parts[-1]
                        for s in to_speak:
                            s_clean = s.strip()
                            if len(s_clean) > 10: # Evitar ruidos o fragmentos demasiado cortos
                                # Generar MD5 para la caché
                                from core.config import DATA_DIR
                                # Simular parámetros de tts_engine para el hash
                                cache_key = hashlib.md5(f"{s_clean}{1.0}{0}{nova_voice._model_name}{nova_voice.engine}".encode()).hexdigest()
                                
                                # Disparar síntesis en segundo plano (Fire and Forget)
                                asyncio.create_task(nova_voice.synthesize(s_clean))
                                
                                # Notificar al frontend que hay un audio listo/preparándose
                                yield f"data: {json.dumps({'type': 'audio', 'key': cache_key})}\n\n"
                # -----------------------------------------------------------

                # Check for insufficient knowledge early (simple logic)
                if not images and "INSUFFICIENT_KNOWLEDGE" in full_response.upper():
                    async for f_chunk in self._handle_insufficient_knowledge(query, full_response): yield f_chunk
                    return

                # v12.1.3: Tool use detection (Regex robusto y flexible)
                if '"tool"' in full_response:
                    query_lower = query.lower()
                    is_social_only = word_count <= 12 and any(x in query_lower for x in ["hola", "buenos dias", "quien eres", "como estas", "qué tal", "saludos"])
                    is_meta_only = any(x in query_lower for x in ["que sabes", "que has aprendido", "quién eres", "quien soy", "en que estamos trabajando", "cual es mi nombre", "que estamos haciendo"])
                    is_general_query = is_social_only or is_meta_only or (intent == "CONVERSATION")
                    
                    # Interceptor Genérico (v13.0)
                    async for tool_chunk in self._intercept_tool_generic(user_id, full_response, query, db, is_general_query): 
                        yield tool_chunk
                    if db.query(ApprovalRequest).filter_by(user_id=user_id).first(): return # Detener stream si se interceptó

                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
                
            # Flush final del buffer de audio para asegurar que lea la última oración
            if sentence_buffer.strip() and len(sentence_buffer.strip()) > 10:
                s_clean = sentence_buffer.strip()
                from core.config import DATA_DIR
                cache_key = hashlib.md5(f"{s_clean}{1.0}{0}{nova_voice._model_name}{nova_voice.engine}".encode()).hexdigest()
                asyncio.create_task(nova_voice.synthesize(s_clean))
                yield f"data: {json.dumps({'type': 'audio', 'key': cache_key})}\n\n"
                sentence_buffer = ""

            # Reflection (Critic) - Only for serious intents (Skip for pure CONVERSATION)
            if intent in ["RESEARCH", "KNOWLEDGE", "CODE"]:
                reflection = await cognitive_controller.verify_response(full_response, knowledge_context)
                if reflection.get("has_errors") and reflection.get("corrections"):
                    correction = f"\n\n> [!WARNING]\n> **Auto-Corrección**: {reflection['corrections']}"
                    yield f"data: {json.dumps({'type': 'chunk', 'text': correction})}\n\n"
                    full_response += correction

            # Update cache with full response (Bypass if attachments present)
            if "tardó demasiado" not in full_response and not has_attachments:
                smart_cache.set(query, llm_client.model, cache_params, str(user_id), full_response)

            # v11.9.8: Explicit Memory Confirmation (moved to background to avoid blocking)
            from core.intent_classifier import _MEMORY_TRIGGERS
            if any(re.search(pat, query, re.I) for pat in _MEMORY_TRIGGERS) or intent == "KNOWLEDGE":
                try:
                    if background_tasks:
                        background_tasks.add_task(memory_service.extract_and_store_memory, query, user_id)
                    else:
                        asyncio.create_task(memory_service.extract_and_store_memory(query, user_id))
                except Exception:
                    pass

            # Save to chat history DB
            try:
                db.add(ChatLog(user_id=user_id, role="assistant", content=full_response, intent=intent))
                db.commit()
            except:
                pass
            
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
            async for chunk in llm_gateway.chat_stream(messages, lane="realtime", temperature=0.0, priority=0):
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

    async def _intercept_tool_generic(self, user_id: int, full_text: str, original_query: str, db: Any, is_general: bool = False) -> AsyncGenerator[str, None]:
        """Interceptor universal para herramientas en formato JSON."""
        try:
            match = re.search(r'\{.*"tool":\s*"([^"]+)".*\}', full_text, re.DOTALL)
            if not match: return
            try:
                json_str = match.group(0)
                json_str = json_str.replace("<execute_tool>", "").replace("</execute_tool>", "").strip()
                
                # v13.5.6: Fix para JSON sucio (barras invertidas sin escapar en rutas de Windows)
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    # Intento de reparación: Escapar barras invertidas que no estén ya escapadas
                    # Pero solo si parecen rutas (ej: C:\ o \Users)
                    repaired_json = re.sub(r'(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', json_str)
                    data = json.loads(repaired_json)
                    logger.info(f"JSON reparado exitosamente: {json_str[:50]}...")
            except Exception as e:
                logger.warning(f"Error parseando JSON de herramienta: {e} | Texto: {json_str[:100]}")
                return 
            if is_general: return
            tool = data.get("tool")
            # v13.6.4: Evitar literal 'undefined' de alucinaciones del LLM
            desc = data.get("description")
            if not desc or str(desc).lower() == "undefined":
                desc = f"Acción de {tool}"
                
            db.query(ApprovalRequest).filter_by(user_id=user_id).delete()
            new_req = ApprovalRequest(
                user_id=user_id,
                tool=tool,
                data=json.dumps(data),
                original_query=original_query
            )
            db.add(new_req)
            db.commit()
            icons = {"terminal": "💻", "browser": "🌐", "gws": "📅", "vision": "👁️"}
            icon = icons.get(tool, "🛠️")
            msg = f"\n\n> [!IMPORTANT]\n> {icon} **NOVA solicita usar la herramienta: {tool.upper()}**\n> **Acción:** {desc}\n"

            if tool == "terminal":
                cmd_str = str(data.get('command') or '')
                formatted_cmd = "\n".join(f"> {line}" for line in cmd_str.splitlines())
                msg += f">\n> ```bash\n{formatted_cmd}\n> ```\n>\n"
            elif tool == "gws": msg += f"> **Módulo:** {data.get('action')} | **Comando:** {data.get('command')}\n"
            elif tool == "vision":
                msg += f"> **Operación:** {data.get('action')}\n"
                if data.get("x") is not None: msg += f"> **Coordenadas:** ({data.get('x')}, {data.get('y')})\n"
            msg += f">\n> *¿Autorizas esta acción? (Escribe **Sí** para proceder o **No** para cancelar)*"
            yield f"data: {json.dumps({'type': 'chunk', 'text': msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Error intercepting tool generic: {e}")

    async def _execute_pending_tool(self, user_id: int, db: Any) -> AsyncGenerator[str, None]:
        """Ejecuta la herramienta aprobada y re-alimenta a NOVA."""
        pending_req = db.query(ApprovalRequest).filter_by(user_id=user_id).first()
        if not pending_req: return
        
        pending_data = {
            "tool": pending_req.tool,
            "original_query": pending_req.original_query
        }
        pending_data.update(json.loads(pending_req.data))
        
        db.delete(pending_req)
        db.commit()
        
        tool = pending_data.get("tool")
        observation = ""
        
        if tool == "terminal":
            command = pending_data.get("command")
            if not command:
                yield f"data: {json.dumps({'type': 'chunk', 'text': '❌ Error: Comando no encontrado.'})}\n\n"
                return
            yield f"data: {json.dumps({'type': 'chunk', 'text': '⚙️ Ejecutando comando de terminal...'})}\n\n"
            result = await tool_executor.execute_terminal(command)
            observation = (
                f"\n[RESULTADO DEL COMANDO]\n"
                f"STDOUT: {result['stdout']}\n"
                f"STDERR: {result['stderr']}\n"
                f"STATUS: {result['status']}"
            )
        elif tool == "browser":
            objective = pending_data.get("objective")
            yield f"data: {json.dumps({'type': 'chunk', 'text': '🌐 Navegando por la web...'})}\n\n"
            from agents.browser_agent import browser_agent
            result = await browser_agent.run_task(objective)
            observation = f"\n[RESULTADO DE NAVEGACIÓN]\n{result['result'] if result['success'] else result['error']}"
        
        elif tool == "gws":
            action = pending_data.get("action")
            command = pending_data.get("command")
            yield f"data: {json.dumps({'type': 'chunk', 'text': f'📅 Accediendo a Google Workspace ({action})...'})}\n\n"
            from services.gws_service import gws_service
            if action == "agenda":
                res = await gws_service.get_agenda()
                observation = f"\n[AGENDA DE GWS]\n{res}"
            elif action == "gmail":
                if command == "triage":
                    res = await gws_service.get_gmail_triage()
                    observation = f"\n[TRIAJE DE GMAIL]\n{res}"
                else: observation = f"\n[GWS] Comando {command} no implementado."
            else: observation = f"\n[GWS] Acción {action} no soportada."

        elif tool == "vision":
            action = pending_data.get("action")
            yield f"data: {json.dumps({'type': 'chunk', 'text': f'👁️ Ejecutando acción visual ({action})...'})}\n\n"
            from services.vision_service import vision_service
            if action == "capture":
                res = vision_service.capture_screen()
                observation = f"\n[VISIÓN] Captura realizada en {res['path']}."
            elif action == "find":
                res = await vision_service.find_element_on_screen(pending_data.get("description", ""))
                observation = f"\n[VISIÓN] Elemento localizado: {res}"
            elif action == "click":
                success = vision_service.click(pending_data.get("x"), pending_data.get("y"), clicks=pending_data.get("clicks", 2))
                observation = f"\n[VISIÓN] Clic ejecutado en ({pending_data.get('x')}, {pending_data.get('y')}). Éxito: {success}"
            elif action == "type":
                success = vision_service.type_text(pending_data.get("text", ""))
                observation = f"\n[VISIÓN] Texto escrito: {pending_data.get('text')}. Éxito: {success}"
            elif action == "press":
                success = vision_service.press_key(pending_data.get("key", "enter"))
                observation = f"\n[VISIÓN] Tecla presionada: {pending_data.get('key')}. Éxito: {success}"
            elif action == "calibrate":
                res = vision_service.calibrate()
                observation = f"\n[VISIÓN] {res}"
            else: observation = f"\n[VISIÓN] Acción {action} no soportada."

        else:
            yield f"data: {json.dumps({'type': 'chunk', 'text': '❌ Herramienta desconocida.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        
        # Re-alimentar al modelo
        messages = [
            {"role": "system", "content": NOVA_IDENTITY_PROMPT},
            {"role": "user", "content": pending_data["original_query"]},
            {"role": "assistant", "content": f"Solicité usar {tool}: {pending_data.get('command') or pending_data.get('objective') or pending_data.get('action')}"},
            {"role": "user", "content": observation}
        ]
        
        async for chunk in llm_gateway.chat_stream(messages, lane="realtime", priority=0):
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
             
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

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


