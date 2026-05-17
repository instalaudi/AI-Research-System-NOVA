import asyncio
import datetime
import json
from core.database import SessionLocal, ResearchJob, ChatLog
from services.system_service import system_service

# Threshold: si un job stuck ya ha sido reintentado N veces, se considera "muerto"
MAX_HEALTH_RETRIES = 2

async def run_health_monitor():
    """Watchdog process to recover stuck jobs with tiered retry logic."""
    print("[HealthMonitor] Iniciando proceso de monitoreo en background...")
    
    # v11.9.20: Tipos de tarea con threshold extendido (builds tardan 20-30 min en CPU)
    LONG_RUNNING_STAGES = {"project_build", "project_build_init"}
    
    while True:
        try:
            await asyncio.sleep(60)
            db = SessionLocal()
            try:
                # Find jobs running for too long without heartbeats
                # v11.9.20: Threshold diferenciado por tipo de tarea
                stuck_threshold_default = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
                stuck_threshold_build = datetime.datetime.utcnow() - datetime.timedelta(minutes=35)
                
                # Obtener todos los jobs en estado "running"
                all_running = db.query(ResearchJob).filter(
                    ResearchJob.status == "running"
                ).all()
                
                # Filtrar: builds usan threshold largo, el resto usa el corto
                stuck_jobs = []
                for job in all_running:
                    stage = getattr(job, "stage", "") or ""
                    threshold = stuck_threshold_build if stage in LONG_RUNNING_STAGES else stuck_threshold_default
                    if job.last_heartbeat and job.last_heartbeat < threshold:
                        stuck_jobs.append(job)
                
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
                            try:
                                from core.task_queue import task_queue  # type: ignore
                            except ImportError:
                                task_queue = None

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
                            if task_queue:
                                loop = asyncio.get_running_loop()
                                loop.call_later(
                                    30,
                                    lambda p=task_payload: task_queue.push_raw_payload(p)
                                )
                                recovered += 1
                            else:
                                print(f"[HealthMonitor] Error reencolando job {job.id}: module core.task_queue not found")
                                job.status = "failed"
                        except Exception as queue_err:
                            print(f"[HealthMonitor] Error reencolando job {job.id}: {queue_err}")
                            job.status = "failed"
                    else:
                        # MUERTO: demasiados reintentos, marcar como terminal
                        stuck_minutes = (datetime.datetime.utcnow() - job.last_heartbeat).total_seconds() / 60
                        print(f"[HealthMonitor] Job {job.id} marcado como DEAD (retry_count={retry_count}). Tema: {job.topic}")
                        job.status = "dead"
                        killed += 1

                        # v11.9.0: Notificar al usuario via ChatLog para que vea el fallo en su chat
                        if job.user_id:
                            fail_msg = (
                                f"⚠️ **Tarea cancelada automáticamente**\n\n"
                                f"La tarea **\"{job.topic}\"** no pudo completarse tras "
                                f"{retry_count} reintentos automáticos "
                                f"(atascada ~{stuck_minutes:.0f} min).\n\n"
                                f"💡 **Recomendación**: Intenta dividir la solicitud en partes más simples "
                                f"o reformular el requerimiento con menos complejidad."
                            )
                            db.add(ChatLog(
                                user_id=job.user_id,
                                role="assistant",
                                content=fail_msg
                            ))

                        # v11.0: Registrar como fallo interno para visibilidad
                        asyncio.create_task(system_service.log_system_failure(
                            type='INTERNAL_ERROR',
                            description=f'Tarea atascada y cancelada: {job.topic} (ID: {job.id}, retries: {retry_count})',
                            severity='warning'
                        ))
                
                if stuck_jobs:
                    db.commit()
                    print(f"[HealthMonitor] Resumen: {recovered} reencolados, {killed} marcados como dead.")
            except Exception as e:
                db.rollback()
                print(f"[HealthMonitor] Error en escaneo de base de datos: {e}")
            finally:
                db.close()
                
        except asyncio.CancelledError:
            print("[HealthMonitor] Detenido.")
            break
        except Exception as e:
            print(f"[HealthMonitor] Error inesperado: {e}")
            await asyncio.sleep(10)

