import asyncio
import copy
from typing import Dict, Any, List, Optional
from core.task_queue import task_queue # type: ignore
from core.logger import agent_logger # type: ignore
from core.config import QUEUE_BACKPRESSURE_THRESHOLD, QUEUE_HIGH_PRIORITY_THRESHOLD # type: ignore
from agents.planner import PlannerAgent # type: ignore
from agents.explorer import ExplorerAgent # type: ignore
from agents.analyzer import AnalyzerAgent # type: ignore
from agents.critic import CriticAgent # type: ignore
from agents.verifier import VerifierAgent # type: ignore
from agents.librarian import LibrarianAgent # type: ignore
from core.swarm_controller import swarm_controller # type: ignore
from core.prompts import VISION_AGENT_PROMPT # type: ignore

class Orchestrator:
    def __init__(self):
        # Hallazgo B: Registry based pipeline
        self.agents = {
            "start_research": {"agent": PlannerAgent(), "next": "explore_topic", "key": "interest_areas"},
            "explore_topic": {"agent": ExplorerAgent(), "next": "analyze_article", "key": "topic"},
            "analyze_article": {"agent": AnalyzerAgent(), "next": "review_analysis", "key": "article"},
            "review_analysis": {"agent": CriticAgent(), "next": "verify_result", "key": "analysis"},
            "verify_result": {"agent": VerifierAgent(), "next": "store_knowledge", "key": "critique"},
            "store_knowledge": {"agent": LibrarianAgent(), "next": None, "key": "content"},
            "swarm_research": {"agent": None, "next": None, "key": "topic"} # Dynamic Swarm
        }

    async def handle_task(self, task: Dict[str, Any]):
        task_type = task["type"]
        data = task["data"]
        
        # v10.7.0: Normalizacin de tipos para recuperacin de jobs
        NORMALIZED_TASK_MAP = {
            "project_build_init": "project_build",
        }
        task_type = NORMALIZED_TASK_MAP.get(task_type, task_type)

        if task_type == "swarm_research":
            await self.handle_swarm_task(task)
            return

        if task_type == "project_build":
            await self.handle_project_build(task)
            return

        if task_type not in self.agents:
            print(f"Unknown task type: {task_type}")
            return

        config = self.agents[task_type]
        agent = config["agent"]
        input_key = config["key"]
        
        # EMG-Persistence: Update Job Status
        job_id = task.get("job_id")
        from core.database import SessionLocal, ResearchJob # type: ignore
        import datetime
        
        async def update_job(status=None, stage=None):
            if not job_id: return
            db = SessionLocal()
            try:
                job = db.query(ResearchJob).get(job_id)
                if job:
                    if status: job.status = status
                    if stage: job.stage = stage
                    job.last_heartbeat = datetime.datetime.utcnow()
                    db.commit()
            finally:
                db.close()

        await update_job(status="running")
        agent_name = getattr(agent, "name", "Orchestrator")
        await agent_logger.set_state(agent_name, "working")
        await agent_logger.log(agent_name, f"Ejecutando tarea: {task_type}")
        
        depth = task.get("depth", 0)
        topic = task.get("topic", "General")
        
        # FIX-6.4: Set de conceptos explorados para evitar loops
        user_id = task.get("user_id")
        # FIX-6.4: Loop prevention (Memory-based fallback since Redis is missing)
        # Using job state for deduplication if needed, but for now skipping redis check
        # topic_key = f"explored_{job_id}:{topic}"
        
        try:
            # Polymorphic execution via BaseAgent.execute
            if agent:
                if task_type == "analyze_article":
                    from core.knowledge_base import knowledge_base # type: ignore
                    context = await knowledge_base.get_recent_titles(limit=10)
                    result = await agent.execute(data.get(input_key), context=context, user_id=user_id) # type: ignore
                else:
                    result = await agent.execute(data.get(input_key), user_id=user_id) # type: ignore
            else:
                result = "No agent available for this task type."
            
            if config["next"]:
                from core.task_queue import task_queue as tq # type: ignore
                from core.llm_client import llm_client # type: ignore
                queue_size = tq.get_size()
                busy_rate = llm_client.busy_rate
                
                # REGLA INDUSTRIAL: Si la saturación > 50%, bloqueamos tareas no críticas
                NON_CRITICAL_TASKS = ["explore_topic", "analyze_article", "swarm_research", "distill"]
                is_non_critical = config["next"] in NON_CRITICAL_TASKS or task_type == "store_knowledge" # Distill part
                
                if busy_rate > 0.5 and is_non_critical:
                    print(f"[Orchestrator] LLM Saturated ({busy_rate:.1%}): Rejecting non-critical task {config['next']}")
                    await agent_logger.log("Orchestrator", f"Saturación detectada ({busy_rate:.1%}). Tarea {config['next']} omitida.")
                    await update_job(status="failed", stage="llm_saturated")
                    return

                if queue_size > QUEUE_BACKPRESSURE_THRESHOLD:
                    print(f"[Orchestrator] Backpressure active: queue at {queue_size}/{QUEUE_BACKPRESSURE_THRESHOLD}, skipping downstream task")
                    await update_job(status="failed", stage="queue_full")
                    return
                safe_result = copy.deepcopy(result)

                if isinstance(safe_result, list):
                    for item in safe_result:
                        await task_queue.add_task(config["next"], {self.agents[config["next"]]["key"]: item, "depth": depth}, topic=topic, job_id=job_id, user_id=user_id) # type: ignore
                else:
                    if task_type == "verify_result":
                        # FIX-3: ALWAYS execute store_knowledge, even if Verifier rejected
                        # Add flag to indicate if it passed verification
                        is_valid = safe_result
                        content_to_store = data[input_key].copy() if isinstance(data[input_key], dict) else {"content": data[input_key]}
                        content_to_store["quality_flag"] = "verified" if is_valid else "unverified_but_stored"  # type: ignore
                        await task_queue.add_task(config["next"], {"content": content_to_store, "depth": depth}, topic=topic, job_id=job_id, user_id=user_id)
                    else:
                        await task_queue.add_task(config["next"], {self.agents[config["next"]]["key"]: safe_result, "depth": depth}, topic=topic, job_id=job_id, user_id=user_id) # type: ignore
            
            # Senior Improv 3: Iterative Deep Exploration
            if task_type == "store_knowledge" and depth < 1:
                from core.task_queue import task_queue as tq
                cur_exp_size = tq.get_size()
                if cur_exp_size < QUEUE_HIGH_PRIORITY_THRESHOLD: # Solo si hay espacio holgado
                    knowledge_content = data.get("content", {})
                    concepts = knowledge_content.get("concepts", [])
                    if concepts and knowledge_content.get("confidence_score", 0) > 0.8:
                        sub_topic = concepts[0]
                        print(f"[Orchestrator] Deep Exploration: Triggering sub-task for '{sub_topic}' (depth {depth+1})")
                        await task_queue.add_task("explore_topic", {"topic": sub_topic, "depth": depth + 1}, topic=sub_topic, user_id=user_id)
                else:
                    print(f"[Orchestrator] Deep Exploration SKIPPED: Queue busy ({cur_exp_size}/{QUEUE_HIGH_PRIORITY_THRESHOLD})")

            # DOBLE APRENDIZAJE: cuando se guarda conocimiento nuevo,
            # disparar destilación del mismo tema en paralelo
            # GUARD: Solo si la cola tiene espacio suficiente (evitar Auto-DDOS)
            if task_type == "store_knowledge":
                from core.task_queue import task_queue as tq
                knowledge_content = data.get("content", {})
                topic_to_distill  = (
                    knowledge_content.get("research_topic") or
                    knowledge_content.get("title", "")
                )
                cur_size = tq.get_size()
                if topic_to_distill and len(topic_to_distill) > 5 and cur_size < QUEUE_HIGH_PRIORITY_THRESHOLD:
                    try:
                        from core.distillation import nova_distillation # type: ignore
                        # Fire and forget — no bloqueamos el pipeline
                        asyncio.create_task(
                            nova_distillation.distill_session(
                                domain               = topic_to_distill[:100],
                                questions_per_domain = 2,  # ligero
                            )
                        )
                        await agent_logger.log(
                            "Librarian",
                            f"Destilación paralela iniciada: {topic_to_distill[:50]}"
                        )
                    except Exception as distill_err:
                        print(f"[Orchestrator] Error destilación paralela: {distill_err}")
                elif topic_to_distill and cur_size >= QUEUE_HIGH_PRIORITY_THRESHOLD:
                    print(f"[Orchestrator] Destilación paralela OMITIDA: cola en {cur_size}/{QUEUE_HIGH_PRIORITY_THRESHOLD}")

            await update_job(status="completed")
            if agent:
                await agent_logger.log(agent.name, f"Completado: {task_type}") # type: ignore
        except Exception as e:
            import traceback
            full_trace = traceback.format_exc()
            from core.llm_client import LLMBusyError, AbortBackgroundTask
            err_name = getattr(agent, "name", "Orchestrator")

            # BUG #4 FIX: Overdrive abort — no es fallo, es pausa controlada
            if isinstance(e, AbortBackgroundTask):
                print(f"[OVERDRIVE] Task aborted mid-execution in {err_name}: {task_type} → re-queued as pending")
                await update_job(status="pending")  # No corromper el estado en BD
                raise e  # Re-lanzar para que task_queue lo re-encole limpiamente

            if isinstance(e, LLMBusyError) or "saturado" in str(e).lower():
                print(f"[Orchestrator] Saturación detectada en {err_name}. Delegando reintento Enterprise...")
                # Re-lanzamos para que el worker en task_queue aplique el backoff exponencial
                raise e

            print(f"Error in orchestrator for {err_name}: {e}")
            print(f"[TRACEBACK] {full_trace}") # Full error logging
            await update_job(status="failed")
        finally:
            if agent:
                await agent_logger.set_state(agent.name, "idle") # type: ignore

    def start(self):
        task_queue.start_workers(self.handle_task)

    async def handle_swarm_task(self, task: Dict[str, Any]):
        """
        Dynamic Swarm Execution Loop.
        """
        data = task["data"]
        topic = data.get("topic")
        job_id = task.get("job_id")
        user_id = task.get("user_id")
        
        from core.database import SessionLocal, ResearchJob
        import datetime
        
        async def update_job(status=None, stage=None):
            if not job_id: return
            db = SessionLocal()
            try:
                job = db.query(ResearchJob).get(job_id)
                if job:
                    if status: job.status = status
                    if stage: job.stage = stage
                    job.last_heartbeat = datetime.datetime.utcnow()
                    db.commit()
            finally:
                db.close()

        await update_job(status="running")
        
        context = {
            "topic": topic,
            "findings": "",
            "history": [],
            "job_id": job_id,
            "user_id": user_id
        }
        
        from core.llm_client import llm_client # type: ignore
        from core.prompts import ( # type: ignore
            RESEARCHER_AGENT_PROMPT, 
            CODER_AGENT_PROMPT, 
            VALIDATOR_AGENT_PROMPT, 
            SYNTHESIS_AGENT_PROMPT,
            VISION_AGENT_PROMPT
        )
        
        try:
            for step in range(swarm_controller.max_steps):
                next_agent = await swarm_controller.decide_next_agent(context)
                if next_agent == "end": break
                
                print(f"[Orchestrator] Swarm Step {step+1}: Delegating to {next_agent.upper()}")
                await agent_logger.log("Swarm", f"Paso {step+1}: Delegando a {next_agent.upper()}")
                await update_job(stage=f"swarm_{next_agent}")
                
                if next_agent == "researcher":
                    prompt = RESEARCHER_AGENT_PROMPT.format(topic=topic)
                    result = await llm_client.chat([{"role": "user", "content": prompt}], priority=1)
                    context["findings"] = str(context.get("findings", "")) + f"\n[Hallazgos Investigador]: {result or ''}" # type: ignore
                    
                elif next_agent == "vision":
                    images = context.get("images", [])
                    vision_findings = ""
                    for img in images[0:2]: # type: ignore
                        prompt = VISION_AGENT_PROMPT.format(image_url=img["url"], context=topic)
                        result = await llm_client.chat([{"role": "user", "content": prompt}], images=[img["url"]], priority=1)
                        vision_findings += f"\n- [Análisis Imagen ({img['alt']})]: {result or ''}"
                    context["findings"] = str(context.get("findings", "")) + f"\n[Hallazgos Visuales]: {vision_findings}"
                    
                elif next_agent == "coder":
                    prompt = CODER_AGENT_PROMPT.format(findings=context["findings"], task=topic)
                    result = await llm_client.chat([{"role": "user", "content": prompt}], priority=1)
                    context["findings"] = str(context.get("findings", "")) + f"\n[Resultado Código]: {result or ''}"
                    
                elif next_agent == "validator":
                    prompt = VALIDATOR_AGENT_PROMPT.format(results=context["findings"])
                    result = await llm_client.chat([{"role": "user", "content": prompt}], priority=1)
                    context["validator_critique"] = result
                    context["findings"] = str(context.get("findings", "")) + f"\n[Crítica Validador]: {result or ''}"
                    
                elif next_agent == "synthesis":
                    prompt = SYNTHESIS_AGENT_PROMPT.format(swarm_data=context["findings"])
                    final_report = await llm_client.chat([{"role": "user", "content": prompt}], priority=1)
                    final_report = f"[INVESTIGACIÓN DE NOVA 🔎]\n\n{final_report}"
                    
                    from core.knowledge_base import knowledge_base # type: ignore
                    await knowledge_base.add_entry({
                        "title": f"Reporte Swarm: {topic}",
                        "content": final_report,
                        "category": "Swarm Analytics",
                        "concepts": [topic, "Swarm"],
                        "confidence_score": 0.95
                    }, user_id=user_id)
                    break
                
                context["history"].append({"step": step, "agent": str(next_agent)}) # type: ignore
            
            await update_job(status="completed")
        except Exception as e:
            await agent_logger.log("Swarm", f"Error en Swarm: {e}")
            await update_job(status="failed")

    async def handle_project_build(self, task: Dict[str, Any]):
        """
        v10.18.0: Background Project Builder.
        Executes the heavy generation + audit phase and delivers the ZIP to chat.
        """
        data = task.get("data", {})
        query = data.get("query")
        user_id = task.get("user_id")
        job_id = task.get("job_id")
        
        from agents.developer_agent import developer_agent
        from core.project_manager import project_manager
        from core.database import SessionLocal, ChatLog, ResearchJob
        import datetime

        async def update_job(status=None, stage=None):
            if not job_id: return
            db = SessionLocal()
            try:
                job = db.query(ResearchJob).get(job_id)
                if job:
                    if status: job.status = status
                    if stage: job.stage = stage
                    job.last_heartbeat = datetime.datetime.utcnow()
                    db.commit()
            finally:
                db.close()

        try:
            await update_job(status="running", stage="project_build_init")
            await agent_logger.log("Developer", f"Iniciando construcción asíncrona: {query[:50]}...")
            
            # Heavy lifting (Generation + Audit)
            files_dict = await developer_agent.build_project(query)
            
            # Packaging
            zip_path = project_manager.package_project(files_dict, f"nova_project_{user_id}_{int(datetime.datetime.utcnow().timestamp())}")
            filename = zip_path.replace("\\", "/").split("/")[-1]
            
            success_msg = (
                "✅ **¡Proyecto Finalizado con Éxito!**\n\n"
                "He terminado de construir y auditar tu solicitud de software. El código ha pasado todos los controles de calidad.\n\n"
                f"📦 **Descarga tu proyecto aquí:** [Descargar Zip](/api/chat/download/{filename})\n\n"
                "Este paquete incluye todos los archivos estructurados y listos para ejecutar."
            )
            
            with SessionLocal() as db:
                db.add(ChatLog(user_id=user_id, role="assistant", content=success_msg))
                db.commit()
            
            await update_job(status="completed")
            await agent_logger.log("Developer", "Proyecto entregado al chat exitosamente.")
            
        except Exception as e:
            error_msg = f"❌ **Fallo en la construcción asíncrona**: {str(e)}\n\n"
            if "5 intentos" in str(e):
                error_msg += "El modelo no logró generar una estructura JSON válida tras múltiples reintentos. Esto puede ocurrir si el proyecto solicitado es extremadamente complejo para el modelo actual. Intenta desglosar tu solicitud en partes más pequeñas o usar un modelo más potente."
            
            with SessionLocal() as db:
                db.add(ChatLog(user_id=user_id, role="assistant", content=error_msg))
                db.commit()
            await update_job(status="failed")
            await agent_logger.log("Developer", f"Error en build asíncrona: {e}")

orchestrator = Orchestrator()
