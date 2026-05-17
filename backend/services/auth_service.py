from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from core.database import User
from core.auth import get_password_hash, verify_password, create_access_token
from core.logging_config import get_logger

logger = get_logger("services.auth")

class AuthService:
    def __init__(self):
        pass

    def register_user(self, db: Session, username: str, password: str, email: str) -> Dict[str, Any]:
        """
        Registers a new user and returns a bearer token.
        """
        if db.query(User).filter(User.username == username).first():
            raise HTTPException(status_code=400, detail="Username already registered")
        
        # Bootstrap: first user is admin
        is_admin = db.query(User).count() == 0
        
        hashed_password = get_password_hash(password)
        new_user = User(
            username=username, 
            email=email, 
            hashed_password=hashed_password,
            is_admin=is_admin
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"New user registered: {username} (admin: {is_admin})")
        access_token = create_access_token(data={"sub": new_user.username, "admin": new_user.is_admin})
        return {"access_token": access_token, "token_type": "bearer"}

    def authenticate_user(self, db: Session, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticates a user and returns a bearer token.
        """
        user = db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.hashed_password):
            logger.warning(f"Failed login attempt for user: {username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = create_access_token(data={"sub": user.username, "admin": user.is_admin})
        return {"access_token": access_token, "token_type": "bearer", "is_admin": user.is_admin}

    def list_all_users(self, db: Session) -> List[Dict[str, Any]]:
        users = db.query(User).all()
        return [{"id": u.id, "username": u.username, "email": u.email, "is_admin": u.is_admin, "is_active": u.is_active} for u in users]

    def toggle_admin_status(self, db: Session, user_id: int, admin_id: int) -> Dict[str, Any]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        if user.id == admin_id:
            raise HTTPException(status_code=400, detail="No puedes quitarte permisos de admin a ti mismo")
            
        # v10.7.0: Seguridad para no quedarse sin administradores activos
        if user.is_admin:
            active_admins = db.query(User).filter(User.is_admin == True, User.is_active == True).count()
            if active_admins <= 1:
                raise HTTPException(status_code=400, detail="No se puede remover al ltimo administrador activo del sistema.")

        user.is_admin = not user.is_admin
        db.commit()
        logger.info(f"User {user.username} admin status toggled to {user.is_admin} by {admin_id}")
        return {"status": "success", "is_admin": user.is_admin}

    def update_user_profile(self, db: Session, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        if "username" in data and data["username"]:
            existing = db.query(User).filter(User.username == data["username"], User.id != user_id).first()
            if existing: raise HTTPException(status_code=400, detail="Nombre de usuario ya en uso")
            user.username = data["username"]
        
        if "email" in data and data["email"]:
            user.email = data["email"]
        
        if "password" in data and data["password"]:
            user.hashed_password = get_password_hash(data["password"])
        
        if "is_active" in data and data["is_active"] is not None:
            # v10.7.0: No permitir desactivar al último administrador
            if data["is_active"] is False and user.is_admin:
                active_admins = db.query(User).filter(User.is_admin == True, User.is_active == True).count()
                if active_admins <= 1:
                    raise HTTPException(status_code=400, detail="No se puede desactivar al ltimo administrador activo.")
            user.is_active = data["is_active"]
            
        db.commit()
        logger.info(f"User profile updated: {user.username}")
        return {"status": "success", "message": "Usuario actualizado"}

    def delete_user(self, db: Session, user_id: int, admin_id: int) -> Dict[str, Any]:
        """v10.7.0: Borrado lgico por defecto para mantener trazabilidad."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        if user.id == admin_id:
            raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")
            
        # v13.9.5: Seguridad para no quedarse sin administradores activos
        if user.is_admin:
            active_admins = db.query(User).filter(User.is_admin == True, User.is_active == True).count()
            if active_admins <= 1:
                raise HTTPException(status_code=400, detail="No se puede eliminar al último administrador activo.")
            
        user.is_active = False
        db.commit()
        logger.info(f"User deactivated (logical delete): {user.username} by admin {admin_id}")
        return {"status": "success", "message": "Usuario desactivado correctamente (borrado lgico)"}

    def delete_user_permanent(self, db: Session, user_id: int, admin_id: int) -> Dict[str, Any]:
        """v10.7.0: Borrado fsico permanente con limpieza en cascada manual."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        if user.id == admin_id:
            raise HTTPException(status_code=400, detail="No puedes eliminarte permanentemente a ti mismo")

        # Seguridad extra para administradores
        if user.is_admin:
            active_admins = db.query(User).filter(User.is_admin == True, User.is_active == True).count()
            if active_admins <= 1:
                raise HTTPException(status_code=400, detail="No se puede eliminar al ltimo administrador activo.")

        # Limpieza en cascada manual de tablas relacionadas (Previene rfos)
        from core.database import ChatLog, UserMemory, Feedback, KnowledgeEntry, UserSession
        db.query(ChatLog).filter(ChatLog.user_id == user_id).delete()
        db.query(UserMemory).filter(UserMemory.user_id == user_id).delete()
        # db.query(Feedback).filter(Feedback.user_id == user_id).delete() # Si existe
        db.query(KnowledgeEntry).filter(KnowledgeEntry.user_id == user_id).delete()
        db.query(UserSession).filter(UserSession.user_id == user_id).delete()

        db.delete(user)
        db.commit()
        logger.warning(f"PERMANENT DELETE: User {user.username} and all related data removed by admin {admin_id}")
        return {"status": "success", "message": "Usuario y todos sus datos relacionados eliminados permanentemente"}

auth_service = AuthService()
