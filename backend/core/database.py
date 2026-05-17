import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "knowledge.db")

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class UserSession(Base):
    __tablename__ = 'user_sessions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    token_id = Column(String, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class KnowledgeEntry(Base):
    __tablename__ = 'knowledge_entries'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True) # Linked to user
    title = Column(String, unique=True)
    category = Column(String)
    score = Column(Float)
    content = Column(Text)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    url = Column(String)
    quality_flag = Column(String, default="full_pipeline")
    is_fallback = Column(Integer, default=0)
    concepts = Column(String)
    # Senior Improv 2: Scoring System
    confidence_score = Column(Float, default=0.0)
    source_count = Column(Integer, default=1)
    source_urls = Column(Text, default="[]") # FIX-6.5: JSON provenance
    consensus_label = Column(String, default="pending")
    # v11.4.2: Huella digital de contenido para evitar duplicados
    content_hash = Column(String, index=True, nullable=True)
    
    __table_args__ = (
        Index('ix_knowledge_concepts', 'concepts'),
        Index('ix_knowledge_category', 'category'),
        Index('ix_knowledge_user', 'user_id'),
        Index('ix_knowledge_content_hash', 'content_hash'),
    )

class KnowledgeNode(Base):
    __tablename__ = 'knowledge_nodes'
    # Senior Improv 1: Entities as unique concepts
    id = Column(String, primary_key=True) 
    group = Column(Integer)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class GraphLink(Base):
    __tablename__ = 'graph_links'
    id = Column(Integer, primary_key=True) # Changed from Integer in audit (Wait, actually user said BigInteger, keeping Integer for SQLite compatibility but mentioning it if needed - actually SQLite handles Integer as 64-bit anyway, but let's use BigInteger to be explicit if available)
    source = Column(String, ForeignKey('knowledge_nodes.id'))
    target = Column(String, ForeignKey('knowledge_nodes.id'))
    relation = Column(String, default="related_to")
    value = Column(Integer)
    
    __table_args__ = (
        Index('ix_graphlink_source', 'source'),
        Index('ix_graphlink_target', 'target'),
    )

class ResearchJob(Base):
    __tablename__ = 'research_jobs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True) # Linked to user
    topic = Column(String)
    stage = Column(String) # current agent/task type
    status = Column(String, default="pending") # pending, running, completed, failed
    retry_count = Column(Integer, default=0)
    last_heartbeat = Column(DateTime, default=datetime.datetime.utcnow)
    data = Column(Text) # JSON blob for payload state
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (
        Index('ix_researchjob_status', 'status'),
    )

class UserMemory(Base):
    __tablename__ = 'user_memories'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True) # Linked to user
    insight = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    importance = Column(Integer, default=1)

class ChatLog(Base):
    __tablename__ = 'chat_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True) # Linked to user
    role = Column(String) # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (
        Index('ix_chatlog_user', 'user_id'),
    )

class Feedback(Base):
    __tablename__ = 'feedbacks'
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('chat_logs.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    rating = Column(String) # 'good', 'bad'
    comment = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class SystemMetrics(Base):
    __tablename__ = 'system_metrics'
    id = Column(Integer, primary_key=True)
    requests_total = Column(Integer, default=0)
    tokens_total = Column(Integer, default=0)
    errors_total = Column(Integer, default=0)
    cache_hits = Column(Integer, default=0)
    cache_misses = Column(Integer, default=0)
    avg_latency_ms = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

class UserProfile(Base):
    __tablename__ = 'user_profiles'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    preferences = Column(Text, default="[]") # JSON list
    frequent_topics = Column(Text, default="[]") # JSON list
    persona_summary = Column(Text, nullable=True)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

class GraphAuditLog(Base):
    __tablename__ = 'graph_audit_logs'
    id = Column(Integer, primary_key=True)
    action = Column(String) # 'DELETE_NODE', 'DELETE_EDGE', 'MERGE_NODE'
    target_id = Column(String) 
    restoration_payload = Column(Text) # JSON blob con relaciones y atributos
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    reverted_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('ix_graphaudit_action', 'action'),
    )

class EvolutionAudit(Base):
    __tablename__ = 'evolution_audit'
    id = Column(Integer, primary_key=True)
    filename = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    score_internal = Column(Float)
    score_external = Column(Float)
    confidence_score = Column(Float, default=0.0)
    lines_added = Column(Integer, default=0)
    lines_removed = Column(Integer, default=0)
    status = Column(String) # 'SUCCESS', 'REJECTED'
    reason = Column(String) # Motivo del estado
    proposal_title = Column(String)
    
    __table_args__ = (
        Index('ix_evolution_filename', 'filename'),
        Index('ix_evolution_status', 'status'),
    )

class ModuleHealth(Base):
    __tablename__ = 'module_health'
    id = Column(Integer, primary_key=True)
    filename = Column(String, unique=True, index=True)
    failure_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    total_value_generated = Column(Float, default=0.0) # Métrica de valor acumulado
    cooldown_until = Column(DateTime, nullable=True)
    last_update = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class EvolutionInsight(Base):
    """Memoria Estratégica Indexada de NOVA."""
    __tablename__ = 'evolution_insight'
    id = Column(Integer, primary_key=True)
    source_cycle = Column(DateTime, default=datetime.datetime.utcnow)
    category = Column(String) # error, performance, architecture
    strategy = Column(String)
    top_problematic = Column(String) # JSON string
    stabilization_index = Column(Float)
    learned_lesson = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class SystemFailure(Base):
    __tablename__ = 'system_failures'
    id = Column(Integer, primary_key=True)
    type = Column(String, index=True)  # 'CORRUPTION', 'API_ERROR', 'INTERNAL_ERROR'
    description = Column(Text)
    severity = Column(String, default='warning') # 'warning', 'critical'
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    resolved = Column(Boolean, default=False, index=True)
    
    __table_args__ = (
        Index('ix_system_failure_type', 'type'),
        Index('ix_system_failure_resolved', 'resolved'),
    )

class SystemSetting(Base):
    """Clave/valor persistente para flags de automatización (Panel de control)."""
    __tablename__ = 'system_settings'
    setting_key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class SnippetCache(Base):
    """Cache local de snippets de código generados para reutilización rápida."""
    __tablename__ = 'snippet_cache'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    snippet_type = Column(String, index=True)  # 'react_component', 'python_function', 'api_endpoint', etc.
    language = Column(String, index=True)  # 'python', 'javascript', 'typescript'
    framework = Column(String, nullable=True)  # 'react', 'vue', 'fastapi', etc.
    code = Column(Text)  # Código fuente
    description = Column(Text, nullable=True)  # Descripción corta del snippet
    keywords = Column(Text)  # JSON list de palabras clave para búsqueda
    vector_id = Column(String, nullable=True)  # ID en ChromaDB para búsqueda semántica
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    usage_count = Column(Integer, default=0)  # Número de veces reutilizado
    last_used = Column(DateTime, nullable=True)
    context = Column(Text, nullable=True)  # Contexto adicional (ej: "input validation")
    similarity_hash = Column(String, nullable=True)  # Hash para detectar duplicados
    
    __table_args__ = (
        Index('ix_snippet_type', 'snippet_type'),
        Index('ix_snippet_language', 'language'),
        Index('ix_snippet_user', 'user_id'),
        Index('ix_snippet_created', 'created_at'),
    )


from sqlalchemy import event

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")  # FIX-3.3: Enable Write-Ahead Logging for concurrency
    cursor.execute("PRAGMA busy_timeout=60000")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
