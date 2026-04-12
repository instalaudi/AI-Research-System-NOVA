
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database import ResearchJob, Base
import json

engine = create_engine("sqlite:///knowledge.db")
Session = sessionmaker(bind=engine)
session = Session()

print("--- Unfinished or Project Jobs ---")
jobs = session.query(ResearchJob).filter(
    (ResearchJob.status.in_(["pending", "running"])) | 
    (ResearchJob.topic.like("%project%")) |
    (ResearchJob.stage.like("%project%"))
).order_by(ResearchJob.created_at.desc()).all()

for job in jobs:
    print(f"ID: {job.id} | Topic: {job.topic} | Stage: {job.stage} | Status: {job.status} | Created: {job.created_at}")

session.close()
