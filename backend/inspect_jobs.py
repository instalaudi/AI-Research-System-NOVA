
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database import ResearchJob, Base
import json

engine = create_engine("sqlite:///knowledge.db")
Session = sessionmaker(bind=engine)
session = Session()

print("--- Recent Research Jobs ---")
jobs = session.query(ResearchJob).order_by(ResearchJob.created_at.desc()).limit(10).all()
for job in jobs:
    print(f"ID: {job.id} | Topic: {job.topic} | Stage: {job.stage} | Status: {job.status} | Created: {job.created_at}")
    # print(f"Data: {job.data[:100]}...")

session.close()
