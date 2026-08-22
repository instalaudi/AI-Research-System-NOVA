from pydantic import BaseModel, constr, field_validator, model_validator
from typing import List, Optional
import re

# Constants used in models
MAX_QUERY_LENGTH = 10000

class FileContent(BaseModel):
    name: str
    content: str

class QueryRequest(BaseModel):
    query: Optional[str] = None
    images: Optional[List[str]] = None
    files: Optional[List[FileContent]] = None
    mode: Optional[str] = "auto" # auto, chat, research, build, knowledge

    @model_validator(mode="before")
    @classmethod
    def fill_query_for_attachments(cls, values):
        if not isinstance(values, dict):
            return values
        query = values.get("query")
        images = values.get("images")
        files = values.get("files")

        if isinstance(query, str) and query.strip():
            return values
        if images or files:
            values["query"] = "Analiza este contenido adjunto"
        return values


    @field_validator("query")
    def validate_query(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("La consulta no puede estar vacía")
        if len(value) > MAX_QUERY_LENGTH:
            raise ValueError(f"La consulta no puede exceder {MAX_QUERY_LENGTH} caracteres")
        return value.strip()

class ExecuteCodeRequest(BaseModel):
    code: str
    language: str = "python" # python, javascript, typescript, rust

class GameRequest(BaseModel):
    idea: constr(min_length=3, max_length=500) # type: ignore
    genre: str = "auto"
    complexity: str = "medium"

class ResearchRequest(BaseModel):
    interest_areas: List[str]

class ManualStoreRequest(BaseModel):
    content: dict

class ApproveProposalRequest(BaseModel):
    proposal_id: str


class FeatureFlagsUpdate(BaseModel):
    """Actualización parcial de flags del Panel de control."""
    distillation: Optional[bool] = None
    self_evolution: Optional[bool] = None
    proactive: Optional[bool] = None
    swarm_research: Optional[bool] = None

def validate_email_logic(v: str) -> str:
    if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
        raise ValueError("Email invlido")
    return v
