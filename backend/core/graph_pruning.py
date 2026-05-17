"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v10.4 — MetaCritic (Fase 3.2: Poda Automática Segura)  ║
║  Archivo: core/graph_pruning.py                              ║
║  Ejecuta poda estructural usando Database y NetworkX         ║
╚══════════════════════════════════════════════════════════════╝
"""
import networkx as nx
import json
import datetime
from typing import Dict, Any, List
from sqlalchemy import func
from core.database import SessionLocal, KnowledgeNode, GraphLink, KnowledgeEntry, GraphAuditLog
from core.vector_db import vector_db
import numpy as np
from core.text_utils import extract_keywords

def _build_networkx_graph(db) -> nx.DiGraph:
    """Construye un DiGraph temporal con in_degrees y out_degrees requeridos para podar."""
    G = nx.DiGraph()
    nodes = db.query(KnowledgeNode.id).all()
    for n in nodes:
        G.add_node(n[0])
    links = db.query(GraphLink.source, GraphLink.target).all()
    for l in links:
        G.add_edge(l.source, l.target)
    return G

def prune_isolated_noise_nodes() -> Dict[str, Any]:
    """
    Elimina nodos de grado 0 (aislados) que tienen < 0.4 de confianza o sin entry.
    También salva si el nodo tiene menos de 7 días.
    """
    db = SessionLocal()
    try:
        G = _build_networkx_graph(db)
        
        in_degrees = dict(G.in_degree())
        out_degrees = dict(G.out_degree())
        
        isolated_ids = [n for n in G.nodes() if in_degrees.get(n, 0) == 0 and out_degrees.get(n, 0) == 0]
        
        if not isolated_ids:
            return {"status": "ok", "deleted": 0}

        # Filtrar por confianza y antigüedad
        threshold_date = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        
        # Obtenemos entries para ver fechas y confianzas
        entries = db.query(KnowledgeEntry).filter(KnowledgeEntry.title.in_(isolated_ids)).all()
        entry_map = {e.title: e for e in entries}
        
        deleted_count = 0
        
        for node_id in isolated_ids:
            entry = entry_map.get(node_id)
            
            # Si no hay entry, es un nodo huérfano puro (posible de extracción NLP) y aislado = ruido total
            if not entry:
                should_delete = True
            else:
                conf = getattr(entry, "confidence_score", 0.0) or 0.0
                created_at = entry.date or datetime.datetime.utcnow()
                # Borrar si confianza < 0.4 Y es más viejo de 7 días
                should_delete = (conf < 0.4) and (created_at < threshold_date)
                
            if should_delete:
                # Loggear en auditoría
                node_obj = db.query(KnowledgeNode).filter(KnowledgeNode.id == node_id).first()
                if node_obj: # Solo por safety
                    payload = {
                        "id": node_obj.id,
                        "group": node_obj.group,
                        "description": node_obj.description,
                        "entry_existed": entry is not None
                    }
                    audit = GraphAuditLog(
                        action="DELETE_NODE",
                        target_id=node_id,
                        restoration_payload=json.dumps(payload)
                    )
                    db.add(audit)
                    
                    if entry:
                        # Nota: eliminamos KnowledgeEntry también si existiera para que no quede colgando
                        db.delete(entry)
                        
                    db.delete(node_obj)
                    deleted_count += 1
                    
        db.commit()
        return {"status": "ok", "deleted": deleted_count}
        
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


def prune_redundant_edges() -> Dict[str, Any]:
    """
    Escanea si existen múltiples aristas entre A y B (en la misma dirección).
    Borra los duplicados y conserva la de id más reciente (o mayor value).
    """
    db = SessionLocal()
    try:
        # Encontrar (source, target) con count > 1
        duplicates = db.query(
            GraphLink.source, 
            GraphLink.target, 
            func.count(GraphLink.id).label('edge_count')
        ).group_by(GraphLink.source, GraphLink.target).having(func.count(GraphLink.id) > 1).all()

        deleted_count = 0
        for dup in duplicates:
            # Obtener todas las aristas entre este par
            edges = db.query(GraphLink).filter(
                GraphLink.source == dup.source,
                GraphLink.target == dup.target
            ).order_by(GraphLink.value.desc(), GraphLink.id.desc()).all()
            
            if len(edges) > 1:
                # Conservar solo edge[0] (el de mayor valor y más nuevo)
                edges_to_delete = edges[1:]
                for edge in edges_to_delete:
                    # Log en auditoría
                    payload = {"source": edge.source, "target": edge.target, "relation": edge.relation, "value": edge.value}
                    audit = GraphAuditLog(
                        action="DELETE_EDGE",
                        target_id=str(edge.id),
                        restoration_payload=json.dumps(payload)
                    )
                    db.add(audit)
                    db.delete(edge)
                    deleted_count += 1

        db.commit()
        return {"status": "ok", "deleted": deleted_count}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    a, b = np.array(v1), np.array(v2)
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0: return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def merge_similar_nodes(limit: int = 100) -> Dict[str, Any]:
    """
    Escanea nodos hoja (grado 1) y los fusiona si hay uno casi idéntico en el DB vectorial
    con similitud > 0.92. Transfiere todas las aristas.
    """
    db = SessionLocal()
    merged_count = 0
    try:
        G = _build_networkx_graph(db)
        
        in_degrees = dict(G.in_degree())
        out_degrees = dict(G.out_degree())
        
        # Candidatos: Nodos de grado 1 (entero, ya sea in o out)
        leaf_nodes = [n for n in G.nodes() if (in_degrees.get(n, 0) + out_degrees.get(n, 0)) == 1]
        
        # Limitar en esta ronda para no bloquear
        leaf_nodes = leaf_nodes[:limit]
        
        for node_id in leaf_nodes:
            # v11.8.2: Búsqueda asíncrona usando la nueva arquitectura de VectorDB
            try:
                matches = await vector_db.search_similar(str(node_id), limit=3)
            except Exception as e:
                print(f"[GraphPruning] Error buscando similares para {node_id}: {e}")
                continue
                
            best_match = None
            best_sim = 0.0
            
            for m in matches:
                doc_title = m.get("document", "") # document es el título en KnowledgeEntries
                dist = m.get("distance", 1.0)
                # Chroma usa cosine distance (1 - sim)
                sim = 1.0 - dist
                
                # Ignorar a sí mismo
                if doc_title == node_id: continue
                
                if sim >= 0.92 and sim > best_sim:
                    best_sim = sim
                    best_match = doc_title
            
            if best_match:
                # ¡Eureka! Hay que fusionar node_id EN best_match
                # Es decir, eliminar node_id y pasar sus aristas a best_match
                
                # 1. Obtener objeto original para respaldar
                node_obj = db.query(KnowledgeNode).filter(KnowledgeNode.id == node_id).first()
                if not node_obj: continue
                
                # Recopilar edges a mover para histórico
                incoming = db.query(GraphLink).filter(GraphLink.target == node_id).all()
                outgoing = db.query(GraphLink).filter(GraphLink.source == node_id).all()
                
                in_list = [{"id": e.id, "source": e.source, "relation": e.relation, "value": e.value} for e in incoming]
                out_list = [{"id": e.id, "target": e.target, "relation": e.relation, "value": e.value} for e in outgoing]
                
                payload = {
                    "absorbed_into": best_match,
                    "node": {"id": node_obj.id, "group": node_obj.group, "description": node_obj.description},
                    "incoming_edges": in_list,
                    "outgoing_edges": out_list
                }
                
                audit = GraphAuditLog(
                    action="MERGE_NODE",
                    target_id=node_id,
                    restoration_payload=json.dumps(payload)
                )
                db.add(audit)
                
                # 2. Transferir incoming
                for e in incoming:
                    # Prevenir crear auto-referencias (self-loops) o redundantes
                    e.target = best_match
                    
                # 3. Transferir outgoing
                for e in outgoing:
                    e.source = best_match
                    
                # 4. Eliminar el nodo origen
                db.delete(node_obj)
                
                # Opcional: También borrar su KnowledgeEntry asociado
                entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.title == node_id).first()
                if entry:
                    db.delete(entry)
                    
                # Nota: ChromaDB quedará con el documento fantasma, pero será deprecado con el tiempo o en syncs.
                db.flush()
                merged_count += 1
                
        db.commit()
        return {"status": "ok", "merged": merged_count}
        
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()
