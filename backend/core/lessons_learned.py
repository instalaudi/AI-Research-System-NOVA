"""
NOVA Lessons Learned — Sistema de Memoria de Lecciones.
Adaptado de OpenClaw agent-memory skill.
Versión: 12.0.0

Proporciona un sistema SQLite ligero para que NOVA:
- Registre lecciones aprendidas de éxitos y fallos.
- Recuerde correcciones del usuario.
- Busque lecciones relevantes antes de ejecutar tareas similares.
- Auto-limpie lecciones obsoletas.

Complementa (no reemplaza) el KnowledgeBase y VectorDB existentes.
Sin dependencias externas — solo sqlite3 + stdlib.
"""

import sqlite3
import json
import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger("core.lessons_learned")

# ═══════════════════════════════════════════════════════
#  Data Models
# ═══════════════════════════════════════════════════════

@dataclass
class Lesson:
    """Una lección aprendida de una experiencia."""
    id: str
    action: str        # Qué se hizo
    context: str       # Situación/tema
    outcome: str       # positive, negative, neutral
    insight: str       # Qué se aprendió
    created_at: str
    applied_count: int = 0
    source: str = "system"  # system, user_correction, self_reflection

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Correction:
    """Una corrección del usuario registrada para evitar repetir errores."""
    id: str
    original: str      # Lo que NOVA hizo mal
    correction: str    # Lo que el usuario corrigió
    context: str       # En qué contexto ocurrió
    created_at: str
    applied_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════
#  Core System
# ═══════════════════════════════════════════════════════

class LessonsLearned:
    """
    Sistema de lecciones aprendidas para NOVA.
    
    Uso:
        from core.lessons_learned import lessons_db
        
        # Registrar un fallo
        lessons_db.learn(
            action="Usé require() en un proyecto Python",
            context="project_build",
            outcome="negative",
            insight="require() es de Node.js. En Python usar import."
        )
        
        # Antes de construir un proyecto, consultar lecciones
        lessons = lessons_db.get_lessons(context="project_build", outcome="negative")
        for l in lessons:
            print(f"⚠️ Recuerda: {l.insight}")
        
        # Registrar corrección del usuario
        lessons_db.add_correction(
            original="Generé HTML sin <!DOCTYPE>",
            correction="Siempre incluir <!DOCTYPE html>",
            context="project_build"
        )
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "nova_lessons.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Crear tablas si no existen."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                context TEXT NOT NULL,
                outcome TEXT NOT NULL,
                insight TEXT NOT NULL,
                created_at TEXT NOT NULL,
                applied_count INTEGER DEFAULT 0,
                source TEXT DEFAULT 'system'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id TEXT PRIMARY KEY,
                original TEXT NOT NULL,
                correction TEXT NOT NULL,
                context TEXT NOT NULL,
                created_at TEXT NOT NULL,
                applied_count INTEGER DEFAULT 0
            )
        """)

        # FTS5 index for fast text search on lessons
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts
            USING fts5(action, context, insight, tokenize='porter')
        """)

        conn.commit()
        conn.close()
        logger.info(f"[LessonsLearned] DB inicializada en {self.db_path}")

    def _generate_id(self, content: str) -> str:
        timestamp = datetime.utcnow().isoformat()
        return hashlib.sha256(f"{content}{timestamp}".encode()).hexdigest()[:12]

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    # ─────────────── LESSONS ───────────────

    def learn(self, action: str, context: str, outcome: str, insight: str,
              source: str = "system") -> str:
        """
        Registrar una lección aprendida.

        Args:
            action: Qué se hizo (ej: "Usé subprocess.call en vez de Popen")
            context: Contexto (ej: "project_build", "research", "chat")
            outcome: "positive", "negative", "neutral"
            insight: Lección (ej: "Usar Popen con timeout para evitar bloqueos")
            source: "system", "user_correction", "self_reflection"

        Returns:
            ID de la lección
        """
        lesson_id = self._generate_id(f"{action}{context}")
        now = self._now()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO lessons (id, action, context, outcome, insight, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (lesson_id, action, context, outcome, insight, now, source))

            # Index in FTS
            cursor.execute("""
                INSERT INTO lessons_fts (rowid, action, context, insight)
                SELECT rowid, action, context, insight FROM lessons WHERE id = ?
            """, (lesson_id,))

            conn.commit()
            logger.info(f"[LessonsLearned] Nueva lección ({outcome}): {insight[:80]}")
        except Exception as e:
            logger.error(f"[LessonsLearned] Error registrando lección: {e}")
            conn.rollback()
        finally:
            conn.close()

        return lesson_id

    def get_lessons(self, context: str = None, outcome: str = None,
                    limit: int = 10) -> List[Lesson]:
        """Obtener lecciones, opcionalmente filtradas."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM lessons WHERE 1=1"
        params: List[Any] = []

        if context:
            query += " AND context LIKE ?"
            params.append(f"%{context}%")
        if outcome:
            query += " AND outcome = ?"
            params.append(outcome)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            Lesson(
                id=r[0], action=r[1], context=r[2], outcome=r[3],
                insight=r[4], created_at=r[5], applied_count=r[6],
                source=r[7] if len(r) > 7 else "system"
            )
            for r in rows
        ]

    def search_lessons(self, query: str, limit: int = 5) -> List[Lesson]:
        """Búsqueda semántica (FTS5) de lecciones relevantes."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT l.* FROM lessons l
                JOIN lessons_fts fts ON l.rowid = fts.rowid
                WHERE lessons_fts MATCH ?
                ORDER BY fts.rank
                LIMIT ?
            """, (query, limit))
            rows = cursor.fetchall()
        except Exception:
            # Si la query FTS falla (caracteres especiales), fallback a LIKE
            safe_query = f"%{query}%"
            cursor.execute("""
                SELECT * FROM lessons
                WHERE insight LIKE ? OR action LIKE ? OR context LIKE ?
                ORDER BY created_at DESC LIMIT ?
            """, (safe_query, safe_query, safe_query, limit))
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [
            Lesson(
                id=r[0], action=r[1], context=r[2], outcome=r[3],
                insight=r[4], created_at=r[5], applied_count=r[6],
                source=r[7] if len(r) > 7 else "system"
            )
            for r in rows
        ]

    def apply_lesson(self, lesson_id: str):
        """Marcar una lección como aplicada (incrementar contador)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE lessons SET applied_count = applied_count + 1 WHERE id = ?",
            (lesson_id,)
        )
        conn.commit()
        conn.close()

    # ─────────────── CORRECTIONS ───────────────

    def add_correction(self, original: str, correction: str,
                       context: str = "general") -> str:
        """
        Registrar una corrección del usuario.

        Args:
            original: Lo que NOVA hizo mal
            correction: Lo que el usuario indicó como correcto
            context: Contexto de la corrección

        Returns:
            ID de la corrección
        """
        corr_id = self._generate_id(f"{original}{correction}")
        now = self._now()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO corrections (id, original, correction, context, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (corr_id, original, correction, context, now))
            conn.commit()
            logger.info(f"[LessonsLearned] Corrección registrada: {correction[:80]}")

            # Auto-convertir a lección negativa
            self.learn(
                action=original,
                context=context,
                outcome="negative",
                insight=correction,
                source="user_correction"
            )
        except Exception as e:
            logger.error(f"[LessonsLearned] Error registrando corrección: {e}")
            conn.rollback()
        finally:
            conn.close()

        return corr_id

    def get_corrections(self, context: str = None,
                        limit: int = 20) -> List[Correction]:
        """Obtener correcciones recientes."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM corrections WHERE 1=1"
        params: List[Any] = []

        if context:
            query += " AND context LIKE ?"
            params.append(f"%{context}%")

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            Correction(
                id=r[0], original=r[1], correction=r[2],
                context=r[3], created_at=r[4], applied_count=r[5]
            )
            for r in rows
        ]

    # ─────────────── UTILITIES ───────────────

    def get_context_warnings(self, context: str) -> List[str]:
        """
        Obtiene advertencias relevantes para un contexto dado.
        Útil para inyectar en prompts de agentes antes de ejecutar tareas.
        
        Uso en DeveloperAgent:
            warnings = lessons_db.get_context_warnings("project_build")
            # → ["Nunca usar require() en Python", "Siempre incluir <!DOCTYPE>"]
        """
        lessons = self.get_lessons(context=context, outcome="negative", limit=15)
        corrections = self.get_corrections(context=context, limit=10)

        warnings: List[str] = []
        for l in lessons:
            warnings.append(f"[LECCIÓN] {l.insight}")
        for c in corrections:
            warnings.append(f"[CORRECCIÓN] {c.correction}")

        return warnings[:20]  # Max 20 warnings to avoid prompt bloat

    def cleanup_stale(self, days: int = 90) -> int:
        """Eliminar lecciones nunca aplicadas y más antiguas que N días."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Note: 'last_accessed' no existe en nuestro schema, usamos created_at
        cursor.execute("""
            DELETE FROM lessons
            WHERE created_at < ? AND applied_count = 0
            AND source != 'user_correction'
        """, (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            logger.info(f"[LessonsLearned] Cleanup: {deleted} lecciones obsoletas eliminadas")
        return deleted

    def stats(self) -> Dict[str, Any]:
        """Estadísticas del sistema de lecciones."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM lessons")
        total_lessons = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM lessons WHERE outcome = 'negative'")
        negative = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM lessons WHERE outcome = 'positive'")
        positive = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM corrections")
        total_corrections = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM lessons WHERE source = 'user_correction'")
        user_corrections = cursor.fetchone()[0]

        conn.close()

        return {
            "total_lessons": total_lessons,
            "positive": positive,
            "negative": negative,
            "neutral": total_lessons - positive - negative,
            "total_corrections": total_corrections,
            "user_corrections": user_corrections,
        }

    def export_json(self) -> Dict[str, Any]:
        """Exportar todo como JSON."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM lessons ORDER BY created_at DESC")
        lessons = [
            Lesson(
                id=r[0], action=r[1], context=r[2], outcome=r[3],
                insight=r[4], created_at=r[5], applied_count=r[6],
                source=r[7] if len(r) > 7 else "system"
            ).to_dict()
            for r in cursor.fetchall()
        ]

        cursor.execute("SELECT * FROM corrections ORDER BY created_at DESC")
        corrections = [
            Correction(
                id=r[0], original=r[1], correction=r[2],
                context=r[3], created_at=r[4], applied_count=r[5]
            ).to_dict()
            for r in cursor.fetchall()
        ]

        conn.close()

        return {
            "exported_at": self._now(),
            "lessons": lessons,
            "corrections": corrections,
            "stats": self.stats(),
        }


# ═══════════════════════════════════════════════════════
#  Singleton global — importar en cualquier módulo de NOVA
# ═══════════════════════════════════════════════════════

lessons_db = LessonsLearned()
