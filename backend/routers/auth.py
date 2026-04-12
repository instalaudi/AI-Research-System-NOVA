from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, constr, field_validator
from typing import Optional

from core.database import User, get_db
from core.auth import get_current_user, get_current_admin
from services.auth_service import auth_service
from core.logging_config import get_logger

logger = get_logger("routers.auth")
router = APIRouter(tags=["auth"])

from routers.schemas import validate_email_logic

class UserCreate(BaseModel):
    username: constr(min_length=3, max_length=50) # type: ignore
    password: constr(min_length=8, max_length=128) # type: ignore
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return validate_email_logic(v)

class UserUpdate(BaseModel):
    username: Optional[constr(min_length=3, max_length=50)] = None # type: ignore
    email: Optional[str] = None
    password: Optional[constr(min_length=8, max_length=128)] = None # type: ignore
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is None: return v
        return validate_email_logic(v)

class Token(BaseModel):
    access_token: str
    token_type: str
    is_admin: bool = False

@router.post("/register", response_model=Token)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """Registers a new user."""
    return auth_service.register_user(db, user.username, user.password, user.email)

@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Authenticates a user and returns a token."""
    return auth_service.authenticate_user(db, form_data.username, form_data.password)

@router.get("/admin/users")
async def list_users(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """ADMIN ONLY: List all users."""
    return auth_service.list_all_users(db)

@router.post("/admin/users/{user_id}/toggle-admin")
async def toggle_admin(user_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """ADMIN ONLY: Toggle admin status of a user."""
    return auth_service.toggle_admin_status(db, user_id, admin.id)

@router.put("/admin/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """ADMIN ONLY: Update user profile."""
    return auth_service.update_user_profile(db, user_id, user_data.dict(exclude_unset=True))

@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """ADMIN ONLY: Delete a user."""
    return auth_service.delete_user(db, user_id, admin.id)
