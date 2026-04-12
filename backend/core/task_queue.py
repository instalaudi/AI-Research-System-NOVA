import asyncio
import json
import datetime
import redis
import fakeredis
import os
from typing import Any, Callable, Optional
from core.config import DEFAULT_MAX_WORKERS, TASK_DYNAMIC_TIMEOUT_CAP # type: ignore
from core.llm_client import llm_client, AbortBackgroundTask

class TaskQueue:
    def __init__(self, concurrency: Optional[int] = None):
        # v11.1.0: Redis removido por solicitud del usuario — Usando fakeredis nativamente
        self.redis = fakeredis.FakeStrictRedis(decode_responses=True)
        print("[TaskQueue] Inicializado en modo LOCAL (fakeredis) — Sin dependencia de servidor externo.")
            
        # Prioridad de configuración: Argumento > Env Var > System Load > Default(4)
        env_workers = os.getenv("MAX_WORKERS")
        if concurrency:
            self.concurrency = concurrency
        elif env_workers:
            self.concurrency = int(env_workers)
        else:
            # Centralized config or Dynamic detection fallback
            import psutil
            ram_gb = psutil.virtual_memory().total / (1024**3)
            # Use DEFAULT_MAX_WORKERS from config.py if it exists, otherwise dynamic
            self.concurrency = DEFAULT_MAX_WORKERS if 'DEFAULT_MAX_WORKERS' in locals() or 'DEFAULT_MAX_WORKERS' in globals() else (6 if ram_gb > 30 else 4 if ram_gb > 14 else 2)
            
        print(f"[TaskQueue] Initialized with {self.concurrency} workers (RAM: {ram_gb:.1f}GB)")
        self.queue_high = "research_tasks_high"
        self.queue_low = "research_tasks_low"
        self.workers = []
        self._counter = 0 

    def get_size(self) -> int:
        """Returns the current number of tasks in the queue."""
        try:
            return self.redis.llen(self.queue_high) + self.redis.llen(self.queue_low)
        except Exception:
            return 0

    async def add_task(self, task_type: str, data: Any, topic: str = "General", job_id: int = None, user_id: int = None):
        # ── Priority Assignment ──────────────────────────────────────────────────────────
        PRIORITY_MAP = {
            "distill": 1, "store_knowledge": 2, "verify_result": 2,
            "review_analysis": 3, "analyze_article": 3, "explore_topic": 4,
            "start_research": 4, "swarm_research": 3, "project_build": 2,
            "project_build_init": 2,
        }
        priority = PRIORITY_MAP.get(task_type, 3)

        # v10.11.0: Ejecución asíncrona de la persistencia en DB para no bloquear
        task_id = await asyncio.to_thread(self._sync_persist_job, task_type, data, topic, job_id, user_id)
        
        task_payload = {
            "priority": priority,
            "type": task_type,
            "data": data,
            "job_id": task_id,
            "user_id": user_id,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        # BUG #5 FIX: Early return — antes la asignación era sobreescrita en línea 115
        if priority > 2 and llm_client.is_user_active():
            task_payload["delayed"] = True
            self.redis.lpush(self.queue_low, json.dumps(task_payload))
            print(f"[OVERDRIVE] Task delayed → queue_low: {task_type} (usuario activo)")
            return  # ← Salida real. Sin esto, la guardia no tenía efecto.

        target_queue = self.queue_high if priority <= 2 else self.queue_low
        self.redis.lpush(target_queue, json.dumps(task_payload))
        print(f"[TaskQueue] Tarea encolada ({task_type}) en {'HIGH' if priority <= 2 else 'LOW'} prio. Cola total: {self.get_size()}")

    async def recovery_scan(self, handler: Callable):
        """Finds interrupted tasks and requeues them."""
        print("[TaskQueue] Recovery scan initiated...")
        from core.database import SessionLocal, ResearchJob
        
        db = SessionLocal()
        try:
            interrupted_jobs = db.query(ResearchJob).filter(
                ResearchJob.status.in_(["pending", "running"])
            ).all()
            
            for job in interrupted_jobs:
                print(f"[TaskQueue] Recovering job {job.topic} at stage {job.stage}")
                job.status = "pending"
                db.commit()
                
                task_payload = {
                    "priority": 10,
                    "type": job.stage,
                    "data": json.loads(job.data),
                    "job_id": job.id,
                    "user_id": job.user_id,
                    "topic": job.topic
                }
                self.redis.lpush(self.queue_low, json.dumps(task_payload))
        finally:
            db.close()

    async def worker(self, name: str, handler: Callable, queues_to_check: list[str]):
        """Worker that processes tasks from a specific set of queues."""
        print(f"Worker {name} started.")
        from core.config import TASK_TIMEOUT_SECONDS, TASK_TIMEOUT_LLM_SECONDS, MAX_TASK_RETRIES, MAX_LLM_RETRIES
        import asyncio

        LONG_TASK_TYPES = {"analyze_article", "review_analysis", "verify_result", "start_research", "explore_topic", "project_build", "project_build_init"}
        while True:
            raw_task = None
            source_queue = None
            
            # Check queues in priority order
            for q in queues_to_check:
                raw_task = await asyncio.to_thread(self.redis.rpop, q)
                if raw_task:
                    source_queue = q
                    break

            if not raw_task:
                await asyncio.sleep(1)
                continue

            task = json.loads(raw_task)
            retry_count = task.get("_retry_count", 0)
            
            # REGLA INDUSTRIAL: Timeout Dinámico con CAP = base + min(queue_size * 0.5, TASK_DYNAMIC_TIMEOUT_CAP)
            queue_size = self.get_size()
            base_timeout = TASK_TIMEOUT_LLM_SECONDS if task.get("type") in LONG_TASK_TYPES else TASK_TIMEOUT_SECONDS
            timeout = base_timeout + min(queue_size * 0.5, TASK_DYNAMIC_TIMEOUT_CAP)
            
            # REGLA INDUSTRIAL: Retries agresivos para IA (MAX_LLM_RETRIES=2)
            limit_retries = MAX_LLM_RETRIES if task.get("type") in LONG_TASK_TYPES else MAX_TASK_RETRIES

            try:
                # OVERDRIVE: Guardia de ejecución última milla
                # v10.9.6: Permitir project_build aunque el usuario esté activo (es petición explícita)
                EXEMPT_TYPES = {"chat", "project_build"}
                if task.get("type") not in EXEMPT_TYPES and llm_client.is_user_active():
                    print(f"[OVERDRIVE] Task aborted and requeued: {task['type']}")
                    # Re-encolamos al final para dar paso a lo que venga
                    self.redis.lpush(source_queue, json.dumps(task))
                    await asyncio.sleep(5) # Pequeña espera para no spammear el loop
                    continue

                print(f"Worker {name} processing {task['type']} (retry {retry_count})")
                
                await asyncio.wait_for(handler(task), timeout=timeout)
            except asyncio.TimeoutError:
                print(f"Error in worker {name}: TIMEOUT for {task['type']} (Dinámico: {timeout}s)")
                if retry_count < limit_retries:
                    task["_retry_count"] = retry_count + 1
                    # Exponential Backoff based on user requirement: 5, 10, 20, 40
                    backoff = [5, 10, 20, 40, 60][min(retry_count, 4)]
                    print(f"Worker {name} backing off for {backoff}s before retry.")
                    await asyncio.sleep(backoff)
                    try:
                        prio = task.get("priority", 4)
                        tq = self.queue_high if prio <= 2 else self.queue_low
                        self.redis.lpush(tq, json.dumps(task))
                    except Exception:
                        pass
                else:
                    await self._mark_job_failed(task.get("job_id"))
            except AbortBackgroundTask:
                print(f"[OVERDRIVE] Task cancelled mid-execution: {task['type']}")
                # Re-encolamos al final para no perder el progreso (reintentará luego)
                self.redis.lpush(source_queue, json.dumps(task))
                continue
            except Exception as e:
                # ENTERPRISE-FIX: Detect LLMBusyError or saturation string
                error_str = str(e)
                is_busy = "LLMBusyError" in error_str or "saturado" in error_str.lower()
                
                print(f"Error in worker {name}: {e}")
                if retry_count < limit_retries:
                    task["_retry_count"] = retry_count + 1
                    
                    if is_busy:
                        # Graduated backoff for saturation
                        backoff = [5, 10, 20, 40, 60][min(retry_count, 4)]
                        print(f"[Saturation] Worker {name} waiting {backoff}s for LLM to breathe.")
                        await asyncio.sleep(backoff)
                    else:
                        await asyncio.sleep(2)
                        
                    self.redis.lpush(source_queue, json.dumps(task))
                else:
                    await self._mark_job_failed(task.get("job_id"))

    async def _update_job_status(self, job_id: int, status: str):
        # FIX-4.6: _update_job_status asíncrono para no bloquear loop
        if not job_id: return
        import asyncio
        await asyncio.to_thread(self._sync_update_job_status, job_id, status)

    def _sync_update_job_status(self, job_id: int, status: str):
        from core.database import SessionLocal, ResearchJob
        import datetime
        with SessionLocal() as db:
            job = db.query(ResearchJob).get(job_id)
            if job:
                job.status = status
                job.last_heartbeat = datetime.datetime.utcnow()
                db.commit()

    async def _mark_job_failed(self, job_id: int):
        """Mark a job as failed in the database (async-safe)."""
        if not job_id: return
        try:
            await asyncio.to_thread(self._sync_mark_job_failed, job_id)
        except Exception as e:
            print(f"Error marking job {job_id} as failed: {e}")

    def _sync_mark_job_failed(self, job_id: int):
        from core.database import SessionLocal, ResearchJob
        import datetime
        db = SessionLocal()
        try:
            job = db.query(ResearchJob).get(job_id)
            if job:
                job.status = "failed"
                job.last_heartbeat = datetime.datetime.utcnow()
                db.commit()
        except Exception as e:
            print(f"Error in _sync_mark_job_failed: {e}")
        finally:
            db.close()

    def start_workers(self, handler: Callable):
        # 2 workers "High Priority" dedicados a Fast/Chat (revisan solo queue_high)
        # Los demás "Low Priority" dedicados a investigación (revisan queue_low y si no hay nada, queue_high)
        high_workers = min(2, max(1, self.concurrency // 3))
        for i in range(self.concurrency):
            if i < high_workers:
                queues = [self.queue_high]
                w_name = f"worker-high-{i}"
            else:
                queues = [self.queue_low, self.queue_high]
                w_name = f"worker-low-{i}"
                
            worker = asyncio.create_task(self.worker(w_name, handler, queues))
            self.workers.append(worker)

    def _sync_persist_job(self, task_type: str, data: Any, topic: str, job_id: int, user_id: int) -> int:
        from core.database import SessionLocal, ResearchJob
        import json
        import datetime
        db = SessionLocal()
        try:
            if job_id:
                job = db.query(ResearchJob).get(job_id)
                if job:
                    job.stage = task_type
                    job.status = "pending"
                    job.data = json.dumps(data)
                    job.last_heartbeat = datetime.datetime.utcnow()
                    db.commit()
                    return job.id
            
            job = ResearchJob(
                topic=topic,
                stage=task_type,
                status="pending",
                data=json.dumps(data),
                user_id=user_id
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job.id
        finally:
            db.close()

    def push_raw_payload(self, payload: dict):
        """API interna para reencolar desde HealthMonitor/etc"""
        prio = payload.get("priority", 4)
        tq = self.queue_high if prio <= 2 else self.queue_low
        self.redis.lpush(tq, json.dumps(payload))

    async def join(self):
        """Wait until all workers have finished (optional, for graceful shutdown)."""
        if self.workers:
            await asyncio.gather(*self.workers)

# Global instance
task_queue = TaskQueue()
