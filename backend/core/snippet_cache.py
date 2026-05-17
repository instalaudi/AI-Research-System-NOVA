"""
Módulo de Caché Local de Snippets - Reutilización Inteligente de Código
Permite almacenar y buscar snippets generados para evitar re-generación innecesaria.
"""

import json
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
import difflib

from core.database import SnippetCache as SnippetCacheModel
from core.logging_config import get_logger

logger = get_logger("core.snippet_cache")


class SnippetCache:
    """Gestor de caché local de snippets de código."""
    
    def __init__(self, db: Session):
        self.db = db
        self.similarity_threshold = 0.85  # Umbral para considerarse similares
    
    def save(
        self,
        user_id: int,
        snippet_type: str,
        language: str,
        code: str,
        description: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        framework: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Guarda un snippet en el caché local.
        
        Args:
            user_id: ID del usuario propietario
            snippet_type: Tipo de snippet ('react_component', 'python_function', etc.)
            language: Lenguaje ('python', 'javascript', 'typescript')
            code: Código fuente
            description: Descripción corta
            keywords: Lista de palabras clave
            framework: Framework usado (opcional)
            context: Contexto adicional (opcional)
        
        Returns:
            Dict con info del snippet guardado
        """
        try:
            # Calcular hash de similaridad para detectar duplicados
            similarity_hash = self._calculate_similarity_hash(code)
            
            # Verificar si ya existe un snippet idéntico
            existing = self.db.query(SnippetCacheModel).filter(
                and_(
                    SnippetCacheModel.user_id == user_id,
                    SnippetCacheModel.similarity_hash == similarity_hash
                )
            ).first()
            
            if existing:
                logger.info(f"Snippet duplicado detectado, actualizando uso: {snippet_type}")
                existing.usage_count += 1
                existing.last_used = datetime.utcnow()
                self.db.commit()
                return {
                    "status": "duplicate",
                    "id": existing.id,
                    "message": "Snippet idéntico ya existe en caché"
                }
            
            # SPRINT 1.1: búsqueda semántica diferida (se mantiene desactivada
            # hasta implementar add_document en vector_db).
            vector_id = None
            
            # Guardar snippet en base de datos
            snippet = SnippetCacheModel(
                user_id=user_id,
                snippet_type=snippet_type,
                language=language,
                framework=framework,
                code=code,
                description=description,
                keywords=json.dumps(keywords or []),
                vector_id=vector_id,
                context=context,
                similarity_hash=similarity_hash,
                created_at=datetime.utcnow(),
                usage_count=1,
                last_used=datetime.utcnow()
            )
            
            self.db.add(snippet)
            self.db.commit()
            self.db.refresh(snippet)
            
            logger.info(f"Snippet guardado: {snippet_type} (ID: {snippet.id})")
            
            return {
                "status": "saved",
                "id": snippet.id,
                "snippet_type": snippet_type,
                "language": language,
                "created_at": snippet.created_at.isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error guardando snippet: {e}")
            self.db.rollback()
            return {"status": "error", "message": str(e)}
    
    def search(
        self,
        user_id: int,
        query: str,
        snippet_type: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Busca snippets por texto, tipo y lenguaje.
        
        Args:
            user_id: ID del usuario
            query: Términos de búsqueda
            snippet_type: Filtrar por tipo (opcional)
            language: Filtrar por lenguaje (opcional)
            limit: Número máximo de resultados
        
        Returns:
            Lista de snippets encontrados
        """
        try:
            # Construir query
            db_query = self.db.query(SnippetCacheModel).filter(
                SnippetCacheModel.user_id == user_id
            )
            
            # Filtrar por tipo y lenguaje si se especifica
            if snippet_type:
                db_query = db_query.filter(SnippetCacheModel.snippet_type == snippet_type)
            
            if language:
                db_query = db_query.filter(SnippetCacheModel.language == language)
            
            # Búsqueda de texto en descripción y keywords
            # Primero intentar búsqueda exacta, luego aproximada
            results = []
            
            # Búsqueda por keyword
            all_snippets = db_query.all()
            for snippet in all_snippets:
                keywords = json.loads(snippet.keywords or "[]")
                score = 0
                
                # Aumentar puntuación si alguna keyword coincide
                for keyword in keywords:
                    if query.lower() in keyword.lower():
                        score += 2
                
                # Búsqueda en descripción
                if snippet.description and query.lower() in snippet.description.lower():
                    score += 1
                
                # Búsqueda en tipo
                if query.lower() in snippet.snippet_type.lower():
                    score += 2
                
                if score > 0:
                    results.append({
                        "id": snippet.id,
                        "snippet_type": snippet.snippet_type,
                        "language": snippet.language,
                        "framework": snippet.framework,
                        "description": snippet.description,
                        "code_preview": snippet.code[:200] + "..." if len(snippet.code) > 200 else snippet.code,
                        "code": snippet.code,
                        "created_at": snippet.created_at.isoformat(),
                        "usage_count": snippet.usage_count,
                        "score": score
                    })
            
            # Ordenar por score (descendente) y limitar
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:limit]
            
            logger.info(f"Búsqueda: '{query}' → {len(results)} resultados")
            return results
        
        except Exception as e:
            logger.error(f"Error buscando snippets: {e}")
            return []
    
    def get_similar(
        self,
        user_id: int,
        code: str,
        snippet_type: Optional[str] = None,
        similarity_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Encuentra snippets similares basado en código.
        
        Args:
            user_id: ID del usuario
            code: Código a comparar
            snippet_type: Filtrar por tipo (opcional)
            similarity_threshold: Umbral de similaridad (0.0-1.0)
        
        Returns:
            Lista de snippets similares ordenados por similaridad
        """
        try:
            threshold = similarity_threshold or self.similarity_threshold
            
            # Obtener todos los snippets del usuario
            query = self.db.query(SnippetCacheModel).filter(
                SnippetCacheModel.user_id == user_id
            )
            
            if snippet_type:
                query = query.filter(SnippetCacheModel.snippet_type == snippet_type)
            
            snippets = query.all()
            similar_snippets = []
            
            # Normalizar código
            code_lines = [line.strip() for line in code.split('\n') if line.strip()]
            
            for snippet in snippets:
                snippet_lines = [line.strip() for line in snippet.code.split('\n') if line.strip()]
                
                # Calcular similaridad usando difflib
                matcher = difflib.SequenceMatcher(None, code_lines, snippet_lines)
                ratio = matcher.ratio()
                
                if ratio >= threshold:
                    similar_snippets.append({
                        "id": snippet.id,
                        "snippet_type": snippet.snippet_type,
                        "language": snippet.language,
                        "framework": snippet.framework,
                        "description": snippet.description,
                        "code_preview": snippet.code[:150] + "..." if len(snippet.code) > 150 else snippet.code,
                        "code": snippet.code,
                        "similarity": round(ratio * 100, 2),
                        "created_at": snippet.created_at.isoformat(),
                        "usage_count": snippet.usage_count
                    })
            
            # Ordenar por similaridad (descendente)
            similar_snippets.sort(key=lambda x: x["similarity"], reverse=True)
            
            logger.info(f"Búsqueda de similares: {len(similar_snippets)} encontrados (threshold={threshold})")
            return similar_snippets
        
        except Exception as e:
            logger.error(f"Error buscando similares: {e}")
            return []
    
    def get_by_type(
        self,
        user_id: int,
        snippet_type: str,
        language: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Obtiene snippets por tipo y lenguaje.
        
        Args:
            user_id: ID del usuario
            snippet_type: Tipo de snippet
            language: Filtrar por lenguaje (opcional)
            limit: Número máximo de resultados
        
        Returns:
            Lista de snippets
        """
        try:
            query = self.db.query(SnippetCacheModel).filter(
                and_(
                    SnippetCacheModel.user_id == user_id,
                    SnippetCacheModel.snippet_type == snippet_type
                )
            )
            
            if language:
                query = query.filter(SnippetCacheModel.language == language)
            
            # Ordenar por uso más reciente
            snippets = query.order_by(desc(SnippetCacheModel.last_used)).limit(limit).all()
            
            results = [
                {
                    "id": s.id,
                    "snippet_type": s.snippet_type,
                    "language": s.language,
                    "framework": s.framework,
                    "description": s.description,
                    "code": s.code,
                    "created_at": s.created_at.isoformat(),
                    "usage_count": s.usage_count
                }
                for s in snippets
            ]
            
            return results
        
        except Exception as e:
            logger.error(f"Error obteniendo snippets por tipo: {e}")
            return []
    
    def update_usage(self, snippet_id: int) -> bool:
        """
        Actualiza count de uso de un snippet.
        
        Args:
            snippet_id: ID del snippet
        
        Returns:
            True si fue exitoso
        """
        try:
            snippet = self.db.query(SnippetCacheModel).filter(
                SnippetCacheModel.id == snippet_id
            ).first()
            
            if snippet:
                snippet.usage_count += 1
                snippet.last_used = datetime.utcnow()
                self.db.commit()
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error actualizando uso: {e}")
            return False
    
    def delete(self, user_id: int, snippet_id: int) -> bool:
        """
        Elimina un snippet del caché.
        
        Args:
            user_id: ID del usuario propietario
            snippet_id: ID del snippet a eliminar
        
        Returns:
            True si fue exitoso
        """
        try:
            snippet = self.db.query(SnippetCacheModel).filter(
                and_(
                    SnippetCacheModel.id == snippet_id,
                    SnippetCacheModel.user_id == user_id
                )
            ).first()
            
            if snippet:
                self.db.delete(snippet)
                self.db.commit()
                logger.info(f"Snippet deletado: {snippet_id}")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error deletando snippet: {e}")
            return False
    
    def get_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Obtiene estadísticas del caché del usuario.
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Diccionario con estadísticas
        """
        try:
            snippets = self.db.query(SnippetCacheModel).filter(
                SnippetCacheModel.user_id == user_id
            ).all()
            
            if not snippets:
                return {
                    "total_snippets": 0,
                    "total_usage": 0,
                    "snippet_types": {},
                    "languages": {}
                }
            
            # Agrupar por tipo y lenguaje
            snippet_types = {}
            languages = {}
            total_usage = 0
            
            for snippet in snippets:
                snippet_types[snippet.snippet_type] = snippet_types.get(snippet.snippet_type, 0) + 1
                languages[snippet.language] = languages.get(snippet.language, 0) + 1
                total_usage += snippet.usage_count
            
            return {
                "total_snippets": len(snippets),
                "total_usage": total_usage,
                "snippet_types": snippet_types,
                "languages": languages,
                "most_used": max([s.usage_count for s in snippets]) if snippets else 0
            }
        
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {}
    
    @staticmethod
    def _calculate_similarity_hash(code: str) -> str:
        """
        Calcula un hash para detectar código duplicado.
        Normaliza el código antes de hashear para detectar cambios cosméticos.
        
        Args:
            code: Código fuente
        
        Returns:
            Hash hexadecimal
        """
        # Normalizar: remover espacios en blanco y comentarios
        normalized = '\n'.join(
            line.strip()
            for line in code.split('\n')
            if line.strip() and not line.strip().startswith('#')
        )
        
        return hashlib.sha256(normalized.encode()).hexdigest()


# Instancia global (será inicializada en main.py)
snippet_cache = None


def init_snippet_cache(db: Session):
    """Inicializa el caché global de snippets."""
    global snippet_cache
    snippet_cache = SnippetCache(db)
    logger.info("✅ Snippet Cache inicializado")
