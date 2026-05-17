#!/usr/bin/env python3
import sys
import os

# Configure env
os.environ.setdefault("JWT_SECRET_KEY", "test_key_for_script_only_" + os.urandom(32).hex()[:32])

# Add backend to path - adjust to be from script location
backend_path = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_path)

from core.database import SessionLocal, User

db = SessionLocal()
try:
    users = db.query(User).limit(10).all()
    print(f"\n{'='*60}")
    print("📋 USUARIOS EN LA BASE DE DATOS:") 
    print(f"{'='*60}")
    if users:
        for user in users:
            print(f"  • {user.username} ({user.email}) - ID: {user.id} - Admin: {user.is_admin}")
    else:
        print("  ⚠️ No hay usuarios en la base de datos")
    print(f"{'='*60}\n")
finally:
    db.close()
