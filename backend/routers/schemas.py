from pydantic import BaseModel, constr, field_validator
from typing import List, Optional
import re

# Constants used in models
MAX_QUERY_LENGTH = 10000

class FileContent(BaseModel):
    name: str
    content: str

class QueryRequest(BaseModel):
    query: constr(min_length=1, max_length=MAX_QUERY_LENGTH) # type: ignore
    images: Optional[List[str]] = None
    files: Optional[List[FileContent]] = None

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

def validate_email_logic(v: str) -> str:
    if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
        raise ValueError("Email invlido")
    return v
