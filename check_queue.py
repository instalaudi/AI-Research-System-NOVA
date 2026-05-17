from core.database import SessionLocal, ResearchJob

db = SessionLocal()
try:
    total_jobs = db.query(ResearchJob).count()
    pending = db.query(ResearchJob).filter(ResearchJob.status == 'pending').count()
    running = db.query(ResearchJob).filter(ResearchJob.status == 'running').count()
    failed = db.query(ResearchJob).filter(ResearchJob.status == 'failed').count()
    completed = db.query(ResearchJob).filter(ResearchJob.status == 'completed').count()

    print('=== ESTADO DE LA COLA DE TAREAS ===')
    print(f'Total de trabajos: {total_jobs}')
    print(f'Pendientes: {pending}')
    print(f'En ejecución: {running}')
    print(f'Completados: {completed}')
    print(f'Fallidos: {failed}')

    if running > 0:
        print()
        print('Trabajos en ejecución:')
        running_jobs = db.query(ResearchJob).filter(ResearchJob.status == 'running').limit(5).all()
        for job in running_jobs:
            print(f'- {job.topic} (ID: {job.id})')

    if failed > 10:
        print()
        print('Últimos trabajos fallidos:')
        failed_jobs = db.query(ResearchJob).filter(ResearchJob.status == 'failed').order_by(ResearchJob.created_at.desc()).limit(3).all()
        for job in failed_jobs:
            error_msg = job.error_message[:100] if job.error_message else "None"
            print(f'- {job.topic} (ID: {job.id}, Error: {error_msg})')

finally:
    db.close()