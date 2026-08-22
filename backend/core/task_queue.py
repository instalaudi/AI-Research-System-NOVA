import asyncio
import json
import datetime
import os
from collections import deque
from pathlib import Path
import threading
from typing import Any, Callable, Optional

try:
    import redis  # type: ignore
except ImportError:
    redis = None  # Redis Optional; fallback to file-backed queue

import fakeredis  # type: ignore

from core.config import DEFAULT_MAX_WORKERS, TASK_DYNAMIC_TIMEOUT_CAP, DATA_DIR # type: ignore
from core.llm_client import llm_client, AbortBackgroundTask

class TaskQueue:
    def __init__(self, concurrency: Optional[int] = None):
        self.storage_dir = Path(DATA_DIR) / "task_queue"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # Thread-safe file lock for synchronous _load_queue / _dump_queue

        redis_url = os.getenv("REDIS_URL", "").strip()
        self.use_redis = False
        if redis_url and redis is not None:
            try:
                self.redis = redis.from_url(redis_url, decode_responses=True)
                self.use_redis = True
                print(f"[TaskQueue] Connected to Redis at {redis_url}")
            except Exception as e:
                print(f"[TaskQueue] Redis connection failed: {e}. Falling back to local persistent queue.")
                self.redis = fakeredis.FakeStrictRedis(decode_responses=True)
        else:
            self.redis = fakeredis.FakeStrictRedis(decode_responses=True)
            if redis_url and redis is None:
                print("[TaskQueue] redis-py library not installed; using local persistence only.")
            else:
                print("[TaskQueue] Inicializado en modo LOCAL (fakeredis) — Sin dependencia de servidor externo.")
            
        # Prioridad de configuración: Argumento > Env Var > System Load > Default(4)
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
        env_workers = os.getenv("MAX_WORKERS")
        if concurrency:
            self.concurrency = concurrency
        elif env_workers:
            self.concurrency = int(env_workers)
        else:
            # Centralized config or Dynamic detection fallback
            # Use DEFAULT_MAX_WORKERS from config.py if it exists, otherwise dynamic
            self.concurrency = DEFAULT_MAX_WORKERS if 'DEFAULT_MAX_WORKERS' in locals() or 'DEFAULT_MAX_WORKERS' in globals() else (6 if ram_gb > 30 else 4 if ram_gb > 14 else 2)
            
        print(f"[TaskQueue] Initialized with {self.concurrency} workers (RAM: {ram_gb:.1f}GB)")
        self.queue_high = "research_tasks_high"
        self.queue_low = "research_tasks_low"
        self.workers = []
        self._counter = 0 

    def _queue_path(self, queue_name: str) -> Path:
        return self.storage_dir / f"{queue_name}.jsonl"

    def _load_queue(self, queue_name: str) -> deque[str]:
        queue_file = self._queue_path(queue_name)
        if not queue_file.exists():
            return deque()
        with queue_file.open("r", encoding="utf-8") as f:
            return deque([line.rstrip("\n") for line in f if line.strip()])

    def _dump_queue(self, queue_name: str, queue: deque[str]) -> None:
        queue_file = self._queue_path(queue_name)
        temp_file = queue_file.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as f:
            for item in queue:
                f.write(f"{item}\n")
        temp_file.replace(queue_file)

    def _llen(self, queue_name: str) -> int:
        if self.use_redis:
            return self.redis.llen(queue_name)
        with self._lock:
            return len(self._load_queue(queue_name))

    def _lpush(self, queue_name: str, payload: str) -> None:
        if self.use_redis:
            self.redis.lpush(queue_name, payload)
            return
        with self._lock:
            q = self._load_queue(queue_name)
            q.appendleft(payload)
            self._dump_queue(queue_name, q)

    def _rpop(self, queue_name: str) -> Optional[str]:
        if self.use_redis:
            return self.redis.rpop(queue_name)
        with self._lock:
            q = self._load_queue(queue_name)
            if not q:
                return None
            item = q.pop()
            self._dump_queue(queue_name, q)
            return item

    def get_size(self) -> int:
        """Returns the current number of tasks in the queue."""
        try:
            return self._llen(self.queue_high) + self._llen(self.queue_low)
        except Exception:
            return 0

    async def add_task(
        self,
        task_type: str,
        data: Any,
        topic: str = "General",
        job_id: int = None,
        user_id: int = None,
        force: bool = False,
    ):
        # ── Priority Assignment ──────────────────────────────────────────────────────────
        PRIORITY_MAP = {
            "distill": 1, "store_knowledge": 2, "verify_result": 2,
            "review_analysis": 3, "analyze_article": 3, "explore_topic": 4,
            "start_research": 4, "swarm_research": 3, "project_build": 2,
            "project_build_init": 2,
        }
        priority = PRIORITY_MAP.get(task_type, 3)

        effective_force = bool(force)
        if isinstance(data, dict) and data.get("user_forced"):
            effective_force = True

        # Panel de control: bloquear encolado autónomo (investigación / destilación en cola)
        if not effective_force:
            from services.system_service import system_service
            swarm_types = {
                "start_research", "explore_topic", "analyze_article", "review_analysis",
                "verify_result", "store_knowledge", "swarm_research",
            }
            if not system_service.is_feature_enabled("swarm_research") and task_type in swarm_types:
                print(f"[PanelControl] swarm_research=OFF — tarea omitida: {task_type}")
                return None
            if not system_service.is_feature_enabled("distillation") and task_type == "distill":
                print(f"[PanelControl] distillation=OFF — tarea omitida: {task_type}")
                return None

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
            self._lpush(self.queue_low, json.dumps(task_payload))
            print(f"[OVERDRIVE] Task delayed → queue_low: {task_type} (usuario activo)")
            return  # ← Salida real. Sin esto, la guardia no tenía efecto.

        target_queue = self.queue_high if priority <= 2 else self.queue_low
        self._lpush(target_queue, json.dumps(task_payload))
        print(f"[TaskQueue] Tarea encolada ({task_type}) en {'HIGH' if priority <= 2 else 'LOW'} prio. Cola total: {self.get_size()}")

    async def recovery_scan(self, handler: Optional[Callable] = None):
        """Finds interrupted tasks and requeues them."""
        print("[TaskQueue] Recovery scan initiated...")
        
        def _sync_recover():
            from core.database import SessionLocal, ResearchJob
            import json
            db = SessionLocal()
            try:
                interrupted_jobs = db.query(ResearchJob).filter(
                    ResearchJob.status.in_(["pending", "running"])
                ).all()
                
                recovered_tasks = []
                for job in interrupted_jobs:
                    print(f"[TaskQueue] Recovering job {job.topic} at stage {job.stage}")
                    job.status = "pending"
                    
                    task_payload = {
                        "priority": 10,
                        "type": job.stage,
                        "data": json.loads(job.data),
                        "job_id": job.id,
                        "user_id": job.user_id,
                        "topic": job.topic
                    }
                    recovered_tasks.append(task_payload)
                
                # FIX m-6 (Auditoría v11.9.18): Un solo commit al final en lugar de N commits en loop
                if interrupted_jobs:
                    db.commit()
                    
                return recovered_tasks
            finally:
                db.close()
                
        try:
            recovered_tasks = await asyncio.to_thread(_sync_recover)
            for task in recovered_tasks:
                self._lpush(self.queue_low, json.dumps(task))
        except Exception as e:
            print(f"[TaskQueue] Error in recovery scan: {e}")

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
                raw_task = await asyncio.to_thread(self._rpop, q)
                if raw_task:
                    source_queue = q
                    break

            if not raw_task:
                await asyncio.sleep(1)
                continue

            task = json.loads(raw_task)
            retry_count = task.get("_retry_count", 0)
            
            # v11.9.0: Timeout por tipo de tarea (más granular que binario LLM/no-LLM)
            TASK_TIMEOUT_MAP = {
                "project_build": 1800,       # 30min: builds incrementales con modelo 3B
                "project_build_init": 1800,
                "analyze_article": TASK_TIMEOUT_LLM_SECONDS,
                "review_analysis": TASK_TIMEOUT_LLM_SECONDS,
                "verify_result": TASK_TIMEOUT_LLM_SECONDS,
                "start_research": TASK_TIMEOUT_LLM_SECONDS,
                "explore_topic": TASK_TIMEOUT_LLM_SECONDS,
            }
            queue_size = self.get_size()
            base_timeout = TASK_TIMEOUT_MAP.get(task.get("type"), TASK_TIMEOUT_SECONDS)
            timeout = base_timeout + min(queue_size * 0.5, TASK_DYNAMIC_TIMEOUT_CAP)
            
            # REGLA INDUSTRIAL: Retries agresivos para IA (MAX_LLM_RETRIES=2)
            limit_retries = MAX_LLM_RETRIES if task.get("type") in LONG_TASK_TYPES else MAX_TASK_RETRIES

            try:
                # OVERDRIVE: Guardia de ejecución última milla
                # v10.9.6: Permitir project_build aunque el usuario esté activo (es petición explícita)
                EXEMPT_TYPES = {"chat", "project_build", "start_research", "explore_topic", "swarm_research"}
                if task.get("type") not in EXEMPT_TYPES and llm_client.is_user_active():
                    print(f"[OVERDRIVE] Task aborted and requeued: {task['type']}")
                    # Re-encolamos al final para dar paso a lo que venga
                    self._lpush(source_queue, json.dumps(task))
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
                        self._lpush(tq, json.dumps(task))
                    except Exception:
                        pass
                else:
                    await self._mark_job_failed(task.get("job_id"), retry_count + 1)
            except AbortBackgroundTask:
                print(f"[OVERDRIVE] Task cancelled mid-execution: {task['type']}")
                # Re-encolamos al final para no perder el progreso (reintentará luego)
                self._lpush(source_queue, json.dumps(task))
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
                        
                    self._lpush(source_queue, json.dumps(task))
                else:
                    await self._mark_job_failed(task.get("job_id"), retry_count + 1)

    async def _update_job_status(self, job_id: int, status: str):
        # FIX-4.6: _update_job_status asíncrono para no bloquear loop
        if not job_id: return
        import asyncio
        await asyncio.to_thread(self._sync_update_job_status, job_id, status)

    def _sync_update_job_status(self, job_id: int, status: str):
        from core.database import SessionLocal, ResearchJob
        import datetime
        with SessionLocal() as db:
            try:
                job = db.query(ResearchJob).get(job_id)
                if job:
                    job.status = status
                    job.last_heartbeat = datetime.datetime.utcnow()
                    db.commit()
            except Exception as e:
                db.rollback()
                print(f"Error in _sync_update_job_status: {e}")

    async def _mark_job_failed(self, job_id: int, retry_count: int = 0):
        """Mark a job as failed in the database (async-safe)."""
        if not job_id: return
        try:
            await asyncio.to_thread(self._sync_mark_job_failed, job_id, retry_count)
        except Exception as e:
            print(f"Error marking job {job_id} as failed: {e}")

    def _sync_mark_job_failed(self, job_id: int, retry_count: int = 0):
        # FIX C-5 (Auditoría v11.9.18): Sincronizar retry_count con la DB
        # para que _check_failed_jobs en proactive.py pueda detectar fallos recurrentes.
        from core.database import SessionLocal, ResearchJob
        import datetime
        with SessionLocal() as db:
            try:
                job = db.query(ResearchJob).get(job_id)
                if job:
                    job.status = "failed"
                    job.retry_count = retry_count
                    job.last_heartbeat = datetime.datetime.utcnow()
                    db.commit()
            except Exception as e:
                db.rollback()
                print(f"Error in _sync_mark_job_failed: {e}")

    def start_workers(self, handler: Callable):
        # 2 workers "High Priority" dedicados a Fast/Chat (revisan solo queue_high)
        # Los demás "Low Priority" dedicados a investigación (revisan queue_low y si no hay nada, queue_high)
        if self.concurrency == 1:
            worker = asyncio.create_task(self.worker("worker-single", handler, [self.queue_high, self.queue_low]))
            self.workers.append(worker)
            return
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
        except Exception as e:
            db.rollback()
            print(f"Error in _sync_persist_job: {e}")
            raise
        finally:
            db.close()

    def push_raw_payload(self, payload: dict):
        """API interna para reencolar desde HealthMonitor/etc"""
        prio = payload.get("priority", 4)
        tq = self.queue_high if prio <= 2 else self.queue_low
        self._lpush(tq, json.dumps(payload))

    async def join(self):
        """Wait until all workers have finished (optional, for graceful shutdown)."""
        if self.workers:
            await asyncio.gather(*self.workers)

# Global instance
task_queue = TaskQueue()
