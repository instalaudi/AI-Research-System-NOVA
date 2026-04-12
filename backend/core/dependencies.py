from fastapi import Request, Depends
from typing import Any
from core.database import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_llm(request: Request) -> Any:
    return request.app.state.llm_client

def get_context_manager(request: Request) -> Any:
    return request.app.state.context_manager

def get_vector_db(request: Request) -> Any:
    return request.app.state.vector_db

def get_cognitive_controller(request: Request) -> Any:
    return request.app.state.cognitive_controller

def get_stt_model(request: Request) -> Any:
    return request.app.state.stt_model

def get_sandbox(request: Request) -> Any:
    return request.app.state.sandbox

def get_orchestrator(request: Request) -> Any:
    return request.app.state.orchestrator
