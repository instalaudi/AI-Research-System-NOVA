import time
import asyncio
import datetime
import threading
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from core.database import (
    SessionLocal,
    KnowledgeEntry,
    KnowledgeNode,
    GraphLink,
    ResearchJob,
    SystemMetrics,
    SystemFailure,
    SystemSetting,
)
from core.logger import agent_logger

from core.logging_config import get_logger

logger = get_logger("services.system")

# Flags gobernados por el Panel de control (persistidos en system_settings)
FEATURE_FLAG_KEYS: tuple[str, ...] = (
    "distillation",
    "self_evolution",
    "proactive",
    "swarm_research",
)
FEATURE_KEY_PREFIX = "automation."


class SystemService:
    def __init__(self):
        # v10.7.0: Lock para asegurar actualizaciones concurrentes seguras
        self._lock = asyncio.Lock()
        # Nuevo lock para persist_metrics
        self._persist_lock = asyncio.Lock()
        # In-memory metrics for fast calculation
        self._metrics = {
            "requests_total": 0,
            "tokens_total": 0,
            "errors_total": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "latency_acc": 0.0,
        }
        self._feature_lock = threading.RLock()
        self._features: Dict[str, bool] = {k: True for k in FEATURE_FLAG_KEYS}
        # v11.8.1: Caché simple para aliviar presión en SQLite por el Dashboard
        self._stats_cache = None
        self._stats_cache_time = 0.0
        self._failures_cache = None
        self._failures_cache_time = 0.0
        
        # v11.9.18: Rastreo de actividad para Prioridad Inteligente
        self._last_user_activity = 0.0
        # v11.9.20: Rastreo de builds activas para bloquear evolución/destilación
        self._last_build_activity = 0.0
        # v13.6.3: Rastreo de latencia para autorregulación
        self._last_chat_latency = 0.0
        
        # Cargar métricas históricas
        self._load_metrics()

    def _load_metrics(self):
        """v13.9.5: Carga valores históricos desde la BD al iniciar el sistema."""
        try:
            db = SessionLocal()
            metrics_entry = db.query(SystemMetrics).order_by(SystemMetrics.id.desc()).first()
            if metrics_entry:
                self._metrics["requests_total"] = getattr(metrics_entry, "requests_total", 0) or 0
                self._metrics["tokens_total"] = getattr(metrics_entry, "tokens_total", 0) or 0
                self._metrics["errors_total"] = getattr(metrics_entry, "errors_total", 0) or 0
                self._metrics["cache_hits"] = getattr(metrics_entry, "cache_hits", 0) or 0
                self._metrics["cache_misses"] = getattr(metrics_entry, "cache_misses", 0) or 0
                
                avg_lat = getattr(metrics_entry, "avg_latency_ms", 0.0) or 0.0
                if self._metrics["requests_total"] > 0 and avg_lat > 0:
                    self._metrics["latency_acc"] = avg_lat * self._metrics["requests_total"]
            db.close()
        except Exception as e:
            logger.error(f"Failed to load historical metrics: {e}")


    def record_user_activity(self):
        """Registra una interacción del usuario (chat, voz, etc)."""
        self._last_user_activity = time.time()
        logger.debug("[System] Actividad del usuario registrada.")

    def is_user_active(self, window_minutes: int = 20) -> bool:
        """Determina si el usuario ha interactuado recientemente."""
        idle_time = time.time() - self._last_user_activity
        return idle_time < (window_minutes * 60)

    def is_cpu_resource_reserved(self) -> bool:
        """
        Determina si el CPU debe reservarse para el usuario.
        Criterio: El usuario habló hace menos de 20 min O hay builds activas O latencia > 15s.
        """
        # Reservar si hay actividad de usuario, builds o si el sistema está degradado por latencia
        is_degraded = self._last_chat_latency > 15.0
        if is_degraded:
            logger.warning(f"[System] Reservando CPU: Latencia crítica detectada ({self._last_chat_latency:.1f}s)")
            
        return self.is_user_active(window_minutes=20) or self.has_active_builds() or is_degraded


    def record_build_activity(self):
        """v11.9.20: Registra que hay una build en progreso."""
        self._last_build_activity = time.time()
        logger.debug("[System] Build activity registrada.")

    def has_active_builds(self, window_minutes: int = 35) -> bool:
        """
        v11.9.20: Determina si hay builds activas recientes.
        Window de 35 min porque builds complejas pueden tardar hasta 30 min.
        """
        if self._last_build_activity == 0.0:
            return False
        idle_time = time.time() - self._last_build_activity
        return idle_time < (window_minutes * 60)

    def load_feature_flags_from_db(self) -> Dict[str, bool]:
        """Carga flags desde SQLite; valores desconocidos usan True (comportamiento legacy)."""
        db = SessionLocal()
        try:
            merged = {k: True for k in FEATURE_FLAG_KEYS}
            rows = db.query(SystemSetting).filter(
                SystemSetting.setting_key.in_([f"{FEATURE_KEY_PREFIX}{k}" for k in FEATURE_FLAG_KEYS])
            ).all()
            for row in rows:
                sk = row.setting_key
                if not sk.startswith(FEATURE_KEY_PREFIX):
                    continue
                name = sk[len(FEATURE_KEY_PREFIX) :]
                if name in merged:
                    merged[name] = str(row.value).strip().lower() in ("1", "true", "yes", "on")
            with self._feature_lock:
                self._features = merged
            return dict(merged)
        except Exception as e:
            logger.error(f"load_feature_flags_from_db: {e}")
            return self.get_feature_flags()
        finally:
            db.close()

    def get_feature_flags(self) -> Dict[str, bool]:
        with self._feature_lock:
            return dict(self._features)

    def is_feature_enabled(self, name: str) -> bool:
        with self._feature_lock:
            return bool(self._features.get(name, True))

    def _persist_feature_row(self, db: Session, name: str, enabled: bool) -> None:
        key = f"{FEATURE_KEY_PREFIX}{name}"
        row = db.query(SystemSetting).filter(SystemSetting.setting_key == key).first()
        val = "true" if enabled else "false"
        if row:
            row.value = val
        else:
            db.add(SystemSetting(setting_key=key, value=val))
        db.commit()

    def set_feature_flag(self, name: str, enabled: bool) -> Dict[str, bool]:
        if name not in FEATURE_FLAG_KEYS:
            raise ValueError(f"Unknown feature flag: {name}")
        db = SessionLocal()
        try:
            self._persist_feature_row(db, name, enabled)
        finally:
            db.close()
        with self._feature_lock:
            self._features = {**self._features, name: bool(enabled)}
        logger.info(f"[PanelControl] {name}={'on' if enabled else 'off'}")
        return self.get_feature_flags()

    def patch_feature_flags(self, updates: Dict[str, Optional[bool]]) -> Dict[str, bool]:
        """Actualiza solo claves presentes y no-None."""
        to_write: Dict[str, bool] = {}
        for k, v in updates.items():
            if k in FEATURE_FLAG_KEYS and v is not None:
                to_write[k] = bool(v)
        if not to_write:
            return self.get_feature_flags()
        db = SessionLocal()
        try:
            for name, enabled in to_write.items():
                self._persist_feature_row(db, name, enabled)
        finally:
            db.close()
        with self._feature_lock:
            self._features = {**self._features, **to_write}
        logger.info(f"[PanelControl] patch {to_write}")
        return self.get_feature_flags()

    def apply_feature_preset_focus(self) -> Dict[str, bool]:
        """Modo piloto: solo interacción (chat, voz, proyectos); sin autonomía pesada."""
        return self.patch_feature_flags({k: False for k in FEATURE_FLAG_KEYS})

    def apply_feature_preset_full(self) -> Dict[str, bool]:
        return self.patch_feature_flags({k: True for k in FEATURE_FLAG_KEYS})

    async def track_metric(self, metric_type: str, value: Any = 1):
        """
        Updates internal metrics.
        v10.7.0: Ahora asncrono para soportar el Lock.
        """
        async with self._lock:
            if metric_type in self._metrics:
                if isinstance(value, (int, float)):
                    self._metrics[metric_type] += value
            if metric_type == "latency_acc":
                # v13.6.3: Actualizar la última latencia conocida para autorregulación
                self._last_chat_latency = value / 1000.0  # Convertir ms a s
                
            # Periodic flush to DB if needed

            if self._metrics["requests_total"] > 0 and self._metrics["requests_total"] % 50 == 0:
                asyncio.create_task(self.persist_metrics())

    async def log_system_failure(self, type: str, description: str, severity: str = 'warning'):
        """
        Logs a critical system failure to the database with auto-cleanup (keep last 100).
        """
        db = SessionLocal()
        try:
            # 1. Insert new failure
            failure = SystemFailure(
                type=type, 
                description=description, 
                severity=severity,
                resolved=False
            )
            db.add(failure)
            db.commit()
            
            # 2. Auto-cleanup: keep only last 100
            total = db.query(SystemFailure).count()
            if total > 100:
                # Find IDs to delete (those older than the 100th most recent)
                subquery = db.query(SystemFailure.id).order_by(SystemFailure.timestamp.desc()).limit(100).all()
                kept_ids = [i[0] for i in subquery]
                
                db.query(SystemFailure).filter(SystemFailure.id.not_in(kept_ids)).delete(synchronize_session=False)
                db.commit()
                logger.debug("Auto-cleanup: SystemFailure table trimmed to 100 entries.")
                
        except Exception as e:
            logger.error(f"Failed to log system failure: {e}")
            db.rollback()
        finally:
            db.close()

    async def persist_metrics(self):
        """
        Syncs in-memory metrics to the database.
        """
        async with self._persist_lock:  # Nuevo lock para evitar escrituras concurrentes
            db = SessionLocal()
            try:
                # We use order_by(desc) to get the latest record or create a new one
                metrics_entry = db.query(SystemMetrics).order_by(SystemMetrics.id.desc()).first()
                if not metrics_entry:
                    metrics_entry = SystemMetrics()
                    db.add(metrics_entry)
                
                metrics_entry.requests_total = self._metrics["requests_total"]
                metrics_entry.tokens_total = self._metrics["tokens_total"]
                metrics_entry.errors_total = self._metrics["errors_total"]
                metrics_entry.cache_hits = self._metrics["cache_hits"]
                metrics_entry.cache_misses = self._metrics["cache_misses"]
                if self._metrics["requests_total"] > 0:
                    metrics_entry.avg_latency_ms = self._metrics["latency_acc"] / self._metrics["requests_total"]
                
                metrics_entry.last_updated = datetime.datetime.utcnow()
                db.commit()
                logger.info("System metrics persisted to DB.")
            except Exception as e:
                logger.error(f"Failed to persist metrics: {e}")
            finally:
                db.close()

    async def get_health_status(self) -> Dict[str, Any]:
        """
        Deep Health Check with timeouts and fault tolerance.
        Ensures the endpoint doesn't return 500 even if dependencies are failing.
        """
        from core.llm_router import llm_router
        from core.config import LLM_CONCURRENCY
        from core.vector_db import vector_db
        from core.task_queue import task_queue  # v11.0.1: Fix circular import
        import httpx
        
        status_data = {
            "status": "healthy",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "dependencies": {}
        }
        
        # 1. Database Check (Timeout 3s)
        try:
            start = time.time()
            db = SessionLocal()
            # Wrap query in wait_for to prevent lock hangs from blocking health
            await asyncio.wait_for(asyncio.to_thread(db.execute, text("SELECT 1")), timeout=3.0)
            db.close()
            status_data["dependencies"]["database"] = {
                "status": "ok",
                "latency_ms": round((time.time() - start) * 1000, 2)
            }
        except Exception as e:
            status_data["status"] = "degraded"
            status_data["dependencies"]["database"] = {"status": "error", "message": "Connection timeout or lock"}
            logger.warning(f"Health: DB connection issue: {e}")

        # 2. Vector DB Check (Timeout 3s)
        try:
            start = time.time()
            count = await asyncio.wait_for(asyncio.to_thread(vector_db.collection.count), timeout=3.0)
            status_data["dependencies"]["vector_db"] = {
                "status": "ok", 
                "count": count,
                "latency_ms": round((time.time() - start) * 1000, 2)
            }
        except Exception as e:
            status_data["status"] = "degraded"
            status_data["dependencies"]["vector_db"] = {"status": "error", "message": "VDB unresponsive"}

        # 3. Multi-LLM Connectivity (Timeout 2s per engine)
        status_data["llm_engines"] = {}
        for name, engine in llm_router._engines.items():
            try:
                start = time.time()
                async with httpx.AsyncClient(timeout=1.5) as client:
                    target_url = engine.base_url.replace("/api/chat", "")
                    resp = await client.get(target_url)
                    status_data["llm_engines"][name] = {
                        "status": "ok" if resp.status_code == 200 else "unresponsive",
                        "latency_ms": round((time.time() - start) * 1000, 2),
                        "model": engine.model,
                        "busy_rate": f"{engine.busy_rate:.2%}"
                    }
                    if resp.status_code != 200: 
                        status_data["status"] = "degraded"
            except Exception:
                status_data["status"] = "degraded"
                status_data["llm_engines"][name] = {"status": "unreachable", "model": engine.model}

        status_data["queue_depth"] = task_queue.get_size()
        status_data["workers_active"] = len([w for w in task_queue.workers if not w.done()])
        status_data["concurrency_limit"] = LLM_CONCURRENCY
        
        main_engine = llm_router._engines["default"]
        if main_engine.is_degraded:
            status_data["status"] = "degraded"
            # v11.0: Registrar degradación (Throttle: solo si la latencia es realmente preocupante)
            if main_engine.avg_latency > 60000:
                async def _safe_log():
                    try:
                         await self.log_system_failure(
                             type='DEGRADED_PERFORMANCE',
                             description=f'Latencia LLM crítica detectada en Chat Engine: {main_engine.avg_latency/1000:.1f}s.',
                             severity='warning'
                        )
                    except Exception as e:          
                        logger.warning(f"Failed to log system failure: {e}")
                asyncio.create_task(_safe_log()) 
            logger.warning(f"System status DEGRADED: Chat Engine Latency too high ({main_engine.avg_latency:.0f}ms)")

        if status_data["status"] == "degraded":
            logger.warning(f"System status DEGRADED: {status_data['dependencies']}")
           
        return status_data

    async def get_agent_logs(self) -> Dict[str, Any]:
        return await agent_logger.get_data()

    def get_detailed_stats(self, db: Session) -> Dict[str, Any]:
        """v10.7.0: Heavy DB summary for Dashboard."""
        # v11.8.1: Caché de 30 segundos para el Dashboard
        now = time.time()
        if self._stats_cache and (now - self._stats_cache_time < 30):
            return self._stats_cache


        total_knowledge = db.query(KnowledgeEntry).count()
        total_nodes = db.query(KnowledgeNode).count()
        total_links = db.query(GraphLink).count()
        
        jobs_stats = db.query(
            ResearchJob.status, func.count(ResearchJob.id)
        ).group_by(ResearchJob.status).all()
        
        jobs_dict = {status: count for status, count in jobs_stats}
        total_jobs = sum(jobs_dict.values())
        
        # System Failures Metrics
        system_failures_count = db.query(SystemFailure).filter(SystemFailure.resolved == False).count()
        has_critical = db.query(SystemFailure).filter(
            SystemFailure.resolved == False, 
            SystemFailure.severity == 'critical'
        ).count() > 0
        
        avg_val = db.query(func.avg(KnowledgeEntry.confidence_score)).scalar()
        avg_quality = float(avg_val) if avg_val is not None else 0.0
        
        # v11.4.3: Cálculo global de calidad (cuántos superan el umbral de 0.55)
        QUALITY_THRESHOLD = 0.55
        high_quality_count = db.query(KnowledgeEntry).filter(KnowledgeEntry.confidence_score >= QUALITY_THRESHOLD).count()
        quality_ratio = (high_quality_count / total_knowledge) if total_knowledge > 0 else 0.0
        
        failed_jobs = jobs_dict.get("failed", 0)
        result = {
            "knowledge": {
                "total_entries": total_knowledge, 
                "total_nodes": total_nodes, 
                "total_links": total_links, 
                "avg_confidence": round(avg_quality, 2),
                "quality_ratio": round(quality_ratio, 2)
            },
            "jobs": {
                **jobs_dict,
                "total": total_jobs,
                "failed": failed_jobs + system_failures_count
            },
            "system": {
                "failures_count": system_failures_count,
                "has_critical": has_critical
            }
        }
        self._stats_cache = result
        self._stats_cache_time = now
        return result

    def clear_failed_jobs(self, db: Session) -> bool:
        try:
            # Phase 1: Clear research jobs
            db.query(ResearchJob).filter(ResearchJob.status == "failed").delete()
            # Phase 2: Clear system failures (mark as resolved)
            db.query(SystemFailure).filter(SystemFailure.resolved == False).update({"resolved": True})
            db.commit()
            logger.info("Failed jobs and system failures cleared (purged) from database.")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to clear jobs: {e}")
            return False

    def get_system_failures(self, db: Session, limit: int = 10):
        """Returns the most recent unresolved system failures with simple caching."""
        now = time.time()
        if self._failures_cache and (now - self._failures_cache_time < 30):
            return self._failures_cache
            
        result = db.query(SystemFailure).filter(SystemFailure.resolved == False).order_by(SystemFailure.timestamp.desc()).limit(limit).all()
        self._failures_cache = result
        self._failures_cache_time = now
        return result

    async def test_embeddings(self, model_name: str) -> Dict[str, Any]:
        """Diagnostic: Tests embedding generation and fallback."""
        from core.llm_client import llm_client
        start = time.time()
        # Attempt to get embeddings with the provided model (which might be invalid)
        vec = await llm_client.get_embeddings("Test diagnostic string", model=model_name)
        latency = (time.time() - start) * 1000
        
        return {
            "success": len(vec) > 0,
            "vector_dim": len(vec),
            "latency_ms": round(latency, 2),
            "fallback_used": model_name != "all-minilm" and len(vec) > 0 # Simple heuristic
        }

    async def test_search_cache(self, topic: str) -> Dict[str, Any]:
        """Diagnostic: Tests search cache hit/miss."""
        from agents.explorer import ExplorerAgent
        start = time.time()
        async with ExplorerAgent() as explorer:
            # We check the cache manually using the explorer's internal cache object
            cached_results = explorer.cache.get(topic, "test_source")
            if cached_results:
                return {
                    "cached": True,
                    "results_count": len(cached_results),
                    "latency_ms": round((time.time() - start) * 1000, 2)
                }
            
            # Simulate a search and set cache
            results = [{"title": "Cache Test Result", "url": "http://test.com", "summary": "Sample"}]
            explorer.cache.set(topic, "test_source", results)
            return {
                "cached": False,
                "latency_ms": round((time.time() - start) * 1000, 2)
            }

    async def get_full_system_audit(self, db: Session) -> Dict[str, Any]:
        """
        Consolidates ALL system metrics (Health, Jobs, Knowledge, LLM) 
        into a single audit object for LLM analysis.
        """
        health = await self.get_health_status()
        stats = self.get_detailed_stats(db)
        
        # Add basic hardware info if possible
        import psutil
        hardware = {
            "cpu_usage_percent": psutil.cpu_percent(),
            "ram_usage_percent": psutil.virtual_memory().percent,
            "available_ram_gb": round(psutil.virtual_memory().available / (1024**3), 2)
        }
        
        return {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "health": health,
            "statistics": stats,
            "hardware": hardware,
            "version": "10.6.0 (Self-Awareness Layer)",
            "uptime_reference": "Backend Cluster Online"
        }

system_service = SystemService()
