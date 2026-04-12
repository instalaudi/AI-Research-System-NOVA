import time
import asyncio
import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from core.database import SessionLocal, KnowledgeEntry, KnowledgeNode, GraphLink, ResearchJob, SystemMetrics, SystemFailure
from core.logger import agent_logger

from core.logging_config import get_logger

logger = get_logger("services.system")

class SystemService:
    def __init__(self):
        # v10.7.0: Lock para asegurar actualizaciones concurrentes seguras
        self._lock = asyncio.Lock()
        # In-memory metrics for fast calculation
        self._metrics = {
            "requests_total": 0,
            "tokens_total": 0,
            "errors_total": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "latency_acc": 0.0,
        }

    async def track_metric(self, metric_type: str, value: Any = 1):
        """
        Updates internal metrics.
        v10.7.0: Ahora asncrono para soportar el Lock.
        """
        async with self._lock:
            if metric_type in self._metrics:
                if isinstance(value, (int, float)):
                    self._metrics[metric_type] += value
            
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
                logger.info("Auto-cleanup: SystemFailure table trimmed to 100 entries.")
                
        except Exception as e:
            logger.error(f"Failed to log system failure: {e}")
            db.rollback()
        finally:
            db.close()

    async def persist_metrics(self):
        """
        Syncs in-memory metrics to the database.
        """
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
        from core.llm_client import llm_client, OLLAMA_URL
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

        # 3. LLM Connectivity (Timeout 2s)
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(OLLAMA_URL.replace("/api/chat", ""))
                status_data["dependencies"]["llm"] = {
                    "status": "ok" if resp.status_code == 200 else "unresponsive",
                    "latency_ms": round((time.time() - start) * 1000, 2),
                    "model": llm_client.model
                }
        except Exception:
            status_data["status"] = "degraded"
            status_data["dependencies"]["llm"] = {"status": "unreachable"}

        status_data["queue_depth"] = task_queue.get_size()
        status_data["workers_active"] = len([w for w in task_queue.workers if not w.done()])
        
        # LLM Industrial Metrics
        status_data["llm_metrics"] = {
            "busy_rate": f"{llm_client.busy_rate:.2%}",
            "avg_latency_ms": round(llm_client.avg_latency, 2),
            "degraded_mode": llm_client.is_degraded,
            "concurrency_limit": LLM_CONCURRENCY
        }
        
        if llm_client.is_degraded:
            status_data["status"] = "degraded"
            # v11.0: Registrar degradación (Throttle: solo si la latencia es realmente preocupante)
            if llm_client.avg_latency > 60000:
                asyncio.create_task(self.log_system_failure(
                    type='DEGRADED_PERFORMANCE',
                    description=f'Latencia LLM crítica detectada: {llm_client.avg_latency/1000:.1f}s. El sistema está bajo carga pesada.',
                    severity='warning'
                ))
            logger.warning(f"System status DEGRADED: LLM Latency too high ({llm_client.avg_latency:.0f}ms)")
        
        if status_data["status"] == "degraded":
             logger.warning(f"System status DEGRADED: {status_data['dependencies']}")
             
        return status_data

    async def get_agent_logs(self) -> Dict[str, Any]:
        return await agent_logger.get_data()

    def get_detailed_stats(self, db: Session) -> Dict[str, Any]:
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
        
        return {
            "knowledge": {
                "total_entries": total_knowledge, 
                "total_nodes": total_nodes, 
                "total_links": total_links, 
                "avg_confidence": round(avg_quality, 2)
            },
            "jobs": {
                **jobs_dict,
                "total": total_jobs,
                "failed": jobs_dict.get("failed", 0) + system_failures_count
            },
            "system": {
                "failures_count": system_failures_count,
                "has_critical": has_critical
            }
        }

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
        """Returns the most recent unresolved system failures."""
        return db.query(SystemFailure).filter(SystemFailure.resolved == False).order_by(SystemFailure.timestamp.desc()).limit(limit).all()

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
