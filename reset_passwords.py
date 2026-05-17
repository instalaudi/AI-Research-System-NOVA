#!/usr/bin/env python3
"""Resetea contraseñas de usuarios para pruebas"""
import sys
import os

# Configure env
os.environ.setdefault("JWT_SECRET_KEY", "test_key_for_script_only_" + os.urandom(32).hex()[:32])

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_path)

from core.database import SessionLocal, User
from core.auth import get_password_hash

db = SessionLocal()
try:
    # Update passwords for test users
    users_to_update = [
        ("Juan Ramon", "123456"),
        ("test_nexus", "test123"),
        ("admin", "admin123"),
    ]
    
    print(f"\n{'='*60}")
    print("🔑 RESETEANDO CONTRASEÑAS DE USUARIOS")
    print(f"{'='*60}\n")
    
    for username, new_password in users_to_update:
        user = db.query(User).filter(User.username == username).first()
        if user:
            user.hashed_password = get_password_hash(new_password)
            db.commit()
            print(f"✅ {username}: {new_password}")
        else:
            print(f"⚠️ {username}: No encontrado")
    
    print(f"\n{'='*60}\n")
    
finally:
    db.close()
