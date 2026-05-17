#!/usr/bin/env python3
"""
Script auxiliar para crear usuario de prueba en NOVA
"""

import sys
import os
from sqlalchemy.orm import Session

# Add backend to path
sys.path.insert(0, "backend")

from core.database import SessionLocal, User
from core.auth import get_password_hash

def create_test_user():
    """Crea o actualiza usuario de prueba"""
    db = SessionLocal()
    try:
        username = "test_user"
        password = "test123"
        
        # Check if user exists
        user = db.query(User).filter(User.username == username).first()
        if user:
            print(f"✅ Usuario '{username}' ya existe")
            # Update password
            user.hashed_password = get_password_hash(password)
            db.commit()
            print(f"🔄 Contraseña actualizada: {password}")
        else:
            # Create new user
            user = User(
                username=username,
                email=f"{username}@test.local",
                hashed_password=get_password_hash(password),
                is_active=True,
                is_admin=False
            )
            db.add(user)
            db.commit()
            print(f"✅ Usuario '{username}' creado")
            print(f"   Contraseña: {password}")
        
        # Also ensure juan_ramon exists
        jr_user = db.query(User).filter(User.username == "juan_ramon").first()
        if not jr_user:
            jr_user = User(
                username="juan_ramon",
                email="juan_ramon@test.local",
                hashed_password=get_password_hash("123456"),
                is_active=True,
                is_admin=True
            )
            db.add(jr_user)
            db.commit()
            print(f"✅ Usuario 'juan_ramon' creado")
            print(f"   Contraseña: 123456")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("Creando usuario de prueba...")
    create_test_user()
