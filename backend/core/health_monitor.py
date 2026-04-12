import asyncio
import datetime
import json
from core.database import SessionLocal, ResearchJob
from services.system_service import system_service

# Threshold: si un job stuck ya ha sido reintentado N veces, se considera "muerto"
MAX_HEALTH_RETRIES = 2

async def run_health_monitor():
    """Watchdog process to recover stuck jobs with tiered retry logic."""
    print("[HealthMonitor] Iniciando proceso de monitoreo en background...")
    while True:
        try:
            await asyncio.sleep(60)
            db = SessionLocal()
            try:
                # Find jobs running for more than 15 minutes without heartbeats
                stuck_threshold = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
                stuck_jobs = db.query(ResearchJob).filter(
                    ResearchJob.status == "running",
                    ResearchJob.last_heartbeat < stuck_threshold
                ).all()
                
                recovered = 0
                killed = 0

                for job in stuck_jobs:
                    retry_count = getattr(job, "retry_count", 0) or 0

                    if retry_count < MAX_HEALTH_RETRIES:
                        # RECUPERABLE: reencolar con backoff de 30s
                        print(f"[HealthMonitor] Job {job.id} atascado (retry {retry_count}/{MAX_HEALTH_RETRIES}). Reencolando con backoff 30s...")
                        job.status = "pending"
                        job.retry_count = retry_count + 1
                        job.last_heartbeat = datetime.datetime.utcnow()

                        # Reencolar en Redis para que el worker lo retome
                        try:
                            from core.task_queue import task_queue  # type: ignore
                            task_payload = {
                                "priority": 3,  # Prioridad media
                                "type": job.stage,
                                "data": json.loads(job.data) if job.data else {},
                                "job_id": job.id,
                                "user_id": job.user_id,
                                "topic": job.topic,
                                "_retry_count": retry_count + 1,
                                "_health_requeued": True
                            }
                            # Backoff de 30s: no empujar inmediatamente
                            asyncio.get_event_loop().call_later(
                                30,
                                lambda p=task_payload: task_queue.push_raw_payload(p)
                            )
                            recovered += 1
                        except Exception as queue_err:
                            print(f"[HealthMonitor] Error reencolando job {job.id}: {queue_err}")
                            job.status = "failed"
                    else:
                        # MUERTO: demasiados reintentos, marcar como terminal
                        print(f"[HealthMonitor] Job {job.id} marcado como DEAD (retry_count={retry_count}). Tema: {job.topic}")
                        job.status = "dead"
                        killed += 1
                        # v11.0: Registrar como fallo interno para visibilidad
                        asyncio.create_task(system_service.log_system_failure(
                            type='INTERNAL_ERROR',
                            description=f'Tarea atascada y cancelada: {job.topic} (ID: {job.id})',
                            severity='warning'
                        ))
                
                if stuck_jobs:
                    db.commit()
                    print(f"[HealthMonitor] Resumen: {recovered} reencolados, {killed} marcados como dead.")
            except Exception as e:
                print(f"[HealthMonitor] Error en escaneo de base de datos: {e}")
            finally:
                db.close()
                
        except asyncio.CancelledError:
            print("[HealthMonitor] Detenido.")
            break
        except Exception as e:
            print(f"[HealthMonitor] Error inesperado: {e}")
            await asyncio.sleep(10)

