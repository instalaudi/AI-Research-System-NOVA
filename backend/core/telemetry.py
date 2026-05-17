import time
import datetime
import asyncio
import psutil
from typing import Dict, Any
from core.database import SessionLocal, KnowledgeEntry, EvolutionAudit, ResearchJob
from sqlalchemy import func
import sys
import subprocess

def get_hardware_context() -> str:
    """Retorna un string con la configuración real de hardware en tiempo de ejecución."""
    total_ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count()
    
    gpu_info = "sin GPU masiva dedicada"
    try:
        if sys.platform == "win32":
            output = subprocess.check_output(["wmic", "path", "win32_VideoController", "get", "name"], text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if "NVIDIA" in output.upper() or "RTX" in output.upper() or "GTX" in output.upper():
                gpu_info = "con GPU dedicada NVIDIA"
            elif "RADEON RX" in output.upper():
                gpu_info = "con GPU dedicada AMD"
            elif "RADEON" in output.upper() or "INTEL" in output.upper():
                gpu_info = "con gráficos integrados (iGPU)"
        else:
            output = subprocess.check_output(["nvidia-smi", "-L"], text=True)
            if "NVIDIA" in output:
                gpu_info = "con GPU dedicada NVIDIA"
    except Exception:
        pass
        
    return f"{cpu_cores} núcleos físicos, {total_ram_gb} GB RAM total, {gpu_info}"

class NOVATelemetry:
    """Sistema de telemetría y monitoreo de salud de NOVA v11."""
    
    def __init__(self):
        self.start_time = time.time()
        self.llm_metrics = {} # model -> {success, total_latency, count}
        self._cache = None
        self._cache_time = 0
        self._cache_duration = 5.0 # Segundos de vida de la caché (v10.11.0)

    def record_llm_success(self, model: str, latency_ms: float):
        """Registra una llamada exitosa al LLM."""
        if model not in self.llm_metrics:
            self.llm_metrics[model] = {"success": 0, "total_latency": 0.0, "count": 0}
        
        self.llm_metrics[model]["success"] += 1
        self.llm_metrics[model]["total_latency"] += latency_ms
        self.llm_metrics[model]["count"] += 1

    async def get_snapshot(self) -> Dict[str, Any]:
        """v11.3: Devuelve snapshot asíncrono y cacheado."""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_duration:
            return self._cache

        snapshot = await self._fetch_snapshot_async()
        
        self._cache = snapshot
        self._cache_time = now
        return snapshot

    async def _fetch_snapshot_async(self) -> Dict[str, Any]:
        """Recolección asíncrona de datos."""
        from core.llm_client import llm_client
        from core.task_queue import task_queue
        from core.cache import smart_cache
        
        db = SessionLocal()
        try:
            # 1. Conocimiento y Tareas (Ejecutamos en thread pool por ser SQLAlchemy síncrono)
            def _get_db_stats():
                total = db.query(KnowledgeEntry).count()
                avg = db.query(func.avg(KnowledgeEntry.confidence_score)).scalar() or 0.0
                return total, avg

            total_articles, avg_conf = await asyncio.to_thread(_get_db_stats)
            
            # Tareas detalladas (Filtramos por heartbeat reciente para evitar fantasmas)
            timeout_limit = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
            running_jobs_objs = db.query(ResearchJob).filter(
                ResearchJob.status == "running",
                ResearchJob.last_heartbeat > timeout_limit
            ).all()
            
            active_jobs = [
                {"topic": j.topic, "stage": j.stage, "id": j.id, "heartbeat": j.last_heartbeat.isoformat()} 
                for j in running_jobs_objs
            ]

            task_stats = {
                "completed": db.query(ResearchJob).filter(ResearchJob.status == "completed").count(),
                "in_progress": len(active_jobs),
                "pending": db.query(ResearchJob).filter(ResearchJob.status == "pending").count(),
                "failed": db.query(ResearchJob).filter(ResearchJob.status == "failed").count(),
                "live_activity": active_jobs
            }

            # 2. Multi-Engine Probe (v11.3 - Async Optimized)
            from core.llm_router import llm_router
            import httpx
            
            engines_status = {}
            total_active_models = []

            async def _probe_engine(name, engine):
                port_url = engine.base_url.replace("/api/chat", "")
                try:
                    async with httpx.AsyncClient(timeout=1.0) as client:
                        resp_ps = await client.get(f"{port_url}/api/ps")
                        if resp_ps.status_code == 200:
                            ps_data = resp_ps.json()
                            models = [m.get("name") for m in ps_data.get("models", [])]
                            return name, {"status": "ok", "port": port_url.split(":")[-1], "models": models}
                except:
                    pass
                return name, {"status": "offline", "port": port_url.split(":")[-1]}

            # Solo sondeamos si no hay una prioridad alta activa que sature la CPU
            if llm_router._active_high_priority == 0:
                # Ejecutamos sondas en paralelo de forma asíncrona
                probe_tasks = [_probe_engine(n, e) for n, e in llm_router._engines.items()]
                results = await asyncio.gather(*probe_tasks)
                for name, data in results:
                    engines_status[name] = data
                    if "models" in data:
                        total_active_models.extend(data["models"])
            else:
                # En carga alta, reportamos estado previo o simplificado para ahorrar CPU
                engines_status = {"system": {"status": "busy", "message": "Monitoring paused during high load"}}

            llm_models = {}
            relevant_models = set(list(self.llm_metrics.keys()) + total_active_models)
            for m_name in relevant_models:
                m = self.llm_metrics.get(m_name, {"total_latency": 0.0, "count": 0})
                llm_models[m_name] = {
                    "avg_latency_ms": int(m["total_latency"] / m["count"]) if m["count"] > 0 else 0,
                    "calls_total": m["count"],
                    "is_active": m_name in total_active_models
                }

            return {
                "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "uptime": {
                    "uptime_human": str(datetime.timedelta(seconds=int(time.time() - self.start_time)))
                },
                "workers": {
                    "total": task_queue.concurrency,
                    "active": len(task_queue.workers),
                    "busy": max(task_stats["in_progress"], len([w for w in task_queue.workers if not w.done()])),
                    "idle": max(0, task_queue.concurrency - max(task_stats["in_progress"], len([w for w in task_queue.workers if not w.done()]))),
                    "queue_size": task_queue.get_size(),
                },
                "llm": {
                    "total_requests": sum(m["count"] for m in self.llm_metrics.values()),
                    "busy_rate": llm_router._engines["default"].busy_rate,
                    "cache_hit_rate": smart_cache.hit_rate,
                    "models": llm_models,
                    "engines": engines_status
                },
                "knowledge": {
                    "total_articles": total_articles,
                    "avg_confidence_score": round(avg_conf, 3),
                    "tasks": task_stats
                },
                "ollama": {
                    "status": "multi-engine",
                    "engines_count": len(engines_status),
                    "models_loaded": total_active_models
                },
                "hardware": {
                    "cpu_usage": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "memory_used_gb": round(psutil.virtual_memory().used / (1024**3), 2)
                }
            }
        finally:
            db.close()

# Instancia global
nova_telemetry = NOVATelemetry()
