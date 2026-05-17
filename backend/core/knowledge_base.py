import time
import asyncio
import datetime
import re
from typing import List, Dict, Any
from core.database import SessionLocal, KnowledgeEntry, KnowledgeNode, GraphLink, init_db
from sqlalchemy.orm import Session

class KnowledgeBase:
    def __init__(self):
        # Initialize DB tables
        init_db()
        # v1.0 Hardening: Saneamiento inicial de integridad referencial
        self.sanitize_graph()

    def sanitize_graph(self):
        """Elimina aristas huérfanas que no tienen nodos correspondientes."""
        db = SessionLocal()
        try:
            # 1. Obtener todos los IDs de nodos válidos
            valid_node_ids = {n.id for n in db.query(KnowledgeNode.id).all()}
            
            # 2. Encontrar aristas inválidas
            all_links = db.query(GraphLink).all()
            orphans = []
            for link in all_links:
                if link.source not in valid_node_ids or link.target not in valid_node_ids:
                    orphans.append(link)
            
            if orphans:
                print(f"[KnowledgeBase] 🧹 Limpiando {len(orphans)} aristas huérfanas por inconsistencia estructural.")
                for o in orphans:
                    db.delete(o)
                db.commit()
        except Exception as e:
            print(f"[KnowledgeBase] Error en saneamiento de grafo: {e}")
            db.rollback()
        finally:
            db.close()

    async def add_entry(self, content: Dict[str, Any], user_id: int = None):
        # BUG-01: SQLite with SQLAlchemy is thread-safe via sessions
        db = SessionLocal()
        try:
            # Check if entry with same title exists for Merging
            existing_entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.title == content.get("title")).first()
            
            concepts_list = content.get("concepts", [])
            concepts_str = ",".join(concepts_list) if isinstance(concepts_list, list) else str(concepts_list)
            
            if existing_entry:
                # Senior Improv 2: Merging Knowledge — FIX-3.1: Weighted Average
                n = existing_entry.source_count
                new_score = float(content.get("confidence_score", 0.8))
                existing_entry.confidence_score = (existing_entry.confidence_score * n + new_score) / (n + 1)
                existing_entry.source_count += 1
                existing_entry.date = datetime.datetime.utcnow()
                if existing_entry.source_count >= 3:
                    existing_entry.consensus_label = "highly_verified"
                
                # Merge concepts — FIX-3.6: Trim spaces in CSV parsing
                existing_concepts = set(c.strip() for c in existing_entry.concepts.split(",") if c.strip()) if existing_entry.concepts else set()
                new_concepts = set(c.strip() for c in concepts_list if c.strip()) if isinstance(concepts_list, list) else set([concepts_list.strip()])
                merged_concepts = existing_concepts | new_concepts
                existing_entry.concepts = ",".join(list(merged_concepts))
                
                # FIX-6.5: Provenance Tracking (accumulate URLs)
                import json
                try:
                    urls = json.loads(existing_entry.source_urls) if getattr(existing_entry, "source_urls", None) else []
                except:
                    urls = []
                new_url = content.get("original_url") or content.get("url")
                if new_url and new_url not in urls:
                    urls.append(new_url)
                existing_entry.source_urls = json.dumps(urls)
                
                entry_data = existing_entry
            else:
                import json
                initial_url = content.get("original_url") or content.get("url") or ""
                entry_data = KnowledgeEntry(
                    title=content.get("title", "Untitled"),
                    category=content.get("category", "General"),
                    score=float(content.get("confidence_score", 0.0)),
                    content=content.get("content") or content.get("summary") or content.get("text") or "",
                    url=content.get("original_url") or content.get("url") or "",
                    quality_flag=content.get("quality_flag", "full_pipeline"),
                    is_fallback=1 if content.get("is_fallback") else 0,
                    concepts=concepts_str,
                    # v4.0 Scoring
                    confidence_score=float(content.get("confidence_score", 0.8)),
                    source_count=1,
                    source_urls=json.dumps([initial_url]) if initial_url else "[]",
                    consensus_label="verified",
                    user_id=user_id or content.get("user_id")
                )
                db.add(entry_data)
            
            # FIX-A3: Flush BEFORE vector indexing to get assigned ID
            db.flush()
            
            # Process Triplets if present
            triplets = content.get("triplets", [])
            if isinstance(triplets, list):
                for triplet in triplets:
                    if isinstance(triplet, list) and len(triplet) == 3:
                        self._add_triplet(db, str(triplet[0]), str(triplet[1]), str(triplet[2]))

            # Update Graph in DB (Nodes & Links)
            self._update_graph_db(db, entry_data)
            
            # v12.0.2: COMMIT ANTES de la indexación vectorial pesada.
            # Esto libera el bloqueo de SQLite para que el chat pueda seguir escribiendo logs
            # mientras generamos los embeddings.
            db.commit()
            
            # Semantic Indexing (Vector DB integration)
            from core.vector_db import vector_db
            try:
                text_to_index = f"{entry_data.title}\n{entry_data.content}"
                metadata = {
                    "id": str(entry_data.id),
                    "title": entry_data.title,
                    "category": entry_data.category,
                    "url": entry_data.url
                }
                await vector_db.index_article(str(entry_data.id), text_to_index, metadata)
            except Exception as ve:
                print(f"[KnowledgeBase] Warning: Vector indexing failed: {ve}")
        except Exception as e:
            db.rollback()
            # FIX-CONCURRENCY: Si dos workers insertan el mismo título simultáneamente,
            # capturar IntegrityError y reintentar con merge() silencioso.
            from sqlalchemy.exc import IntegrityError
            if isinstance(e, IntegrityError):
                print(f"[KnowledgeBase] IntegrityError (concurrent insert) for '{content.get('title', '?')}'. Retrying with merge...")
                try:
                    db2 = SessionLocal()
                    # Re-check with a fresh session to avoid stale state
                    existing = db2.query(KnowledgeEntry).filter(KnowledgeEntry.title == content.get("title")).first()
                    if existing:
                        existing.source_count += 1
                        existing.date = datetime.datetime.utcnow()
                        db2.commit()
                    db2.close()
                except Exception as retry_err:
                    print(f"[KnowledgeBase] Retry also failed: {retry_err}")
            else:
                print(f"Error adding entry to DB: {e}")
        finally:
            db.close()


    def _normalize_node_id(self, raw_id: str) -> str:
        """FIX-3.5: Normalizes Graph Node IDs to prevent duplicates due to case or spacing."""
        if not raw_id: return ""
        # Remove special characters that might mess up IDs but keep technical ones
        clean = re.sub(r'[^\w\s\-\.]', '', str(raw_id))
        return clean.strip().lower().replace("  ", " ")

    def _add_triplet(self, db: Session, subject: str, relation: str, object_obj: str):
        """Adds a triplet (S, R, O) to the Knowledge Graph using merge to prevent duplicates."""
        subject = self._normalize_node_id(subject)
        object_obj = self._normalize_node_id(object_obj)
        if not subject or not object_obj:
            return
            
        for concept in [subject, object_obj]:
            # Use merge to handle "get or create" safely
            db.merge(KnowledgeNode(id=concept, group=1))
        
        db.flush()  # Ensure nodes exist before adding FK-referencing links
        
        # Add the link/relation (GraphLink uses autoincrement ID, so no merge needed for PK, 
        # but we check for unique combination)
        existing_link = db.query(GraphLink).filter(
            GraphLink.source == subject, 
            GraphLink.target == object_obj,
            GraphLink.relation == relation
        ).first()
        
        if not existing_link:
            db.add(GraphLink(source=subject, target=object_obj, relation=relation, value=3))

    def _update_graph_db(self, db: Session, entry: KnowledgeEntry):
        # In v4.0, we link Concepts (KnowledgeNodes) extracted from the article
        concepts = [c.strip() for c in (entry.concepts.split(",") if entry.concepts else []) if c.strip()]
        concepts = [self._normalize_node_id(c) for c in concepts if c.strip()]
        
        # Calculate a deterministic group based on the category name
        category_hash = abs(hash(entry.category or "General"))
        group = (category_hash % 8) + 1  # Distribute across 8 different groups

        # 1. Create/Update Nodes for each concept
        processed_nodes = set()
        for concept_id in concepts:
            if concept_id in processed_nodes: continue
            processed_nodes.add(concept_id)
            # merge() prevents UNIQUE constraint failed by checking identity map/DB first
            db.merge(KnowledgeNode(id=concept_id, group=group))

        # 2. Link article title to its main concepts
        normalized_title = self._normalize_node_id(entry.title)
        if normalized_title and normalized_title not in processed_nodes:
            db.merge(KnowledgeNode(id=normalized_title, group=group, description=entry.category))
            processed_nodes.add(normalized_title)
        elif normalized_title:
            # If title was already processed as a concept, update its description to category
            title_node = db.get(KnowledgeNode, normalized_title)
            if title_node:
                title_node.description = entry.category
                title_node.group = group


        # CRITICAL FIX: Flush all nodes to DB before creating links (FK constraint)
        db.flush()

        for concept_id in concepts:
            if concept_id != normalized_title:
                # Deduplicate 'defines' link
                existing_link = db.query(GraphLink).filter(
                    GraphLink.source == normalized_title,
                    GraphLink.target == concept_id,
                    GraphLink.relation == "defines"
                ).first()
                if not existing_link:
                    db.add(GraphLink(source=normalized_title, target=concept_id, relation="defines", value=2))
                else:
                    existing_link.value = (existing_link.value or 0) + 1

        # 3. Semantic Cross-Linking (Inter-concept) - avoid duplicates and bidirectional links
        if len(concepts) > 1:
            for i in range(len(concepts) - 1):
                node_a, node_b = concepts[i], concepts[i+1]
                if node_a == node_b: continue
                # Sort alphabetically to avoid (A,B) and (B,A) duplicates
                source_id, target_id = sorted([node_a, node_b])
                
                existing_link = db.query(GraphLink).filter(
                    GraphLink.source == source_id,
                    GraphLink.target == target_id,
                    GraphLink.relation == "related_to"
                ).first()
                if not existing_link:
                    db.add(GraphLink(source=source_id, target=target_id, relation="related_to", value=1))
                else:
                    existing_link.value = (existing_link.value or 0) + 1

    async def get_recent_titles(self, limit: int = 10) -> List[str]:
        db = SessionLocal()
        try:
            entries = db.query(KnowledgeEntry.title).order_by(KnowledgeEntry.date.desc()).limit(limit).all()
            return [e.title for e in entries]
        finally:
            db.close()

    async def get_knowledge(self):
        db = SessionLocal()
        try:
            entries = db.query(KnowledgeEntry).order_by(KnowledgeEntry.date.desc()).all()
            return [
                {
                    "title": e.title,
                    "category": e.category,
                    "score": e.score,
                    "date": e.date.strftime("%Y-%m-%d %H:%M:%S"),
                    "content": e.content,
                    "url": e.url,
                    "concepts": e.concepts.split(",") if e.concepts else []
                } for e in entries
            ]
        finally:
            db.close()

    async def get_concept_stats(self, concepts: List[str]) -> Dict[str, Any]:
        """Calculates aggregate stats for a list of concepts (Scientific Honesty)."""
        db = SessionLocal()
        try:
            # Find entries that contain these concepts
            total_sources = 0
            avg_confidence = 0.0
            unique_titles = set()
            
            for concept in concepts:
                entries = db.query(KnowledgeEntry).filter(KnowledgeEntry.concepts.contains(concept)).all()
                for e in entries:
                    if e.title not in unique_titles:
                        unique_titles.add(e.title)
                        total_sources += e.source_count
                        avg_confidence += e.confidence_score
            
            count = len(unique_titles)
            return {
                "source_count": total_sources,
                "confidence": (avg_confidence / count) if count > 0 else 0.0,
                "consensus": "alto" if count > 2 else "medio" if count > 0 else "bajo",
                "unique_articles": count
            }
        finally:
            db.close()

    async def search_enhanced(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        v13.8.0: Búsqueda Híbrida (Graph-RAG Bridge).
        Combina similitud vectorial con expansión de grafo por vecindad.
        """
        # v13.8.0: 1. Búsqueda Vectorial Inicial
        try:
            from core.vector_db import vector_db
            vector_results = await vector_db.search_similar(query, limit=limit)
        except Exception as e:
            print(f"[KnowledgeBase] Error en búsqueda vectorial: {e}")
            vector_results = []
            
        entry_ids = [int(r["metadata"]["id"]) for r in vector_results if "metadata" in r and "id" in r["metadata"]]
            
        db = SessionLocal()
        try:
            # 2. Recuperar entradas base
            entries = db.query(KnowledgeEntry).filter(KnowledgeEntry.id.in_(entry_ids)).all()
            results = []
            seen_ids = set(entry_ids)

            # 3. Identificar Conceptos Clave para Expansión
            concepts_to_expand = []
            for e in entries:
                if e.concepts:
                    concepts_to_expand.extend([c.strip().lower() for c in e.concepts.split(",") if c.strip()])
                results.append({
                    "title": e.title,
                    "content": e.content,
                    "score": e.score,
                    "source": "vector"
                })

            # 4. Expansión por Grafo
            if concepts_to_expand:
                from collections import Counter
                top_concepts = [c for c, _ in Counter(concepts_to_expand).most_common(10)]
                neighbor_links = db.query(GraphLink).filter(GraphLink.source.in_(top_concepts)).limit(10).all()
                neighbor_ids = [l.target for l in neighbor_links]
                if neighbor_ids:
                    from sqlalchemy import or_
                    conditions = [KnowledgeEntry.concepts.like(f"%{nid}%") for nid in neighbor_ids[:5]]
                    neighbors = db.query(KnowledgeEntry).filter(or_(*conditions)).limit(3).all()
                    
                    for n in neighbors:
                        if n.id not in seen_ids:
                            results.append({
                                "title": f"[Relacionado] {n.title}",
                                "content": n.content,
                                "score": n.score,
                                "source": "graph_expansion"
                            })
                            seen_ids.add(n.id)

            return results
        finally:
            db.close()

    async def get_graph(self, limit: int = 100):
        """
        Retrieves the knowledge graph with pagination (v10.15.0).
        Limits nodes to the 'limit' most recently updated entries to prevent UI crashes.
        """
        db = SessionLocal()
        try:
            # 1. Get the most recently updated nodes
            nodes = db.query(KnowledgeNode).order_by(KnowledgeNode.updated_at.desc()).limit(limit).all()
            node_ids = {n.id for n in nodes}
            
            # 2. Get links ONLY where both nodes are in the set
            from sqlalchemy import and_
            links = db.query(GraphLink).filter(
                and_(GraphLink.source.in_(node_ids), GraphLink.target.in_(node_ids))
            ).all()
            
            return {
                "nodes": [{"id": n.id, "group": n.group} for n in nodes],
                "links": [
                    {"source": l.source, "target": l.target, "value": l.value, "relation": l.relation} 
                    for l in links
                ]
            }
        finally:
            db.close()

# Global instance
knowledge_base = KnowledgeBase()
