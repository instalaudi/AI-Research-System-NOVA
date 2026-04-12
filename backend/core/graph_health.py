"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v10.3 — MetaCritic (Fase 3.1)                          ║
║  Archivo: core/graph_health.py                               ║
║  Análisis pasivo determinista usando NetworkX                ║
╚══════════════════════════════════════════════════════════════╝
"""
import networkx as nx
from typing import Dict, Any, List
from core.database import SessionLocal, KnowledgeNode, GraphLink, KnowledgeEntry

def analyze_graph_health() -> Dict[str, Any]:
    """
    Ejecuta un análisis estructural pasivo del grafo usando NetworkX.
    Devuelve un informe JSON con métricas de salud y ruido.
    """
    db = SessionLocal()
    try:
        nodes = db.query(KnowledgeNode).all()
        links = db.query(GraphLink).all()
        
        # También traemos los scores de confianza del entry correspondiente
        # Usamos dicts para rápido acceso
        entry_scores = {e.title: e.confidence_score for e in db.query(KnowledgeEntry.title, KnowledgeEntry.confidence_score).all()}
        
        # 1. Construir el grafo dirigido
        G = nx.DiGraph()
        
        # Agregar nodos
        for node in nodes:
            conf = entry_scores.get(node.id, 0.0)
            G.add_node(node.id, group=node.group, confidence=conf)
            
        # Agregar aristas
        # Llevamos cuenta de aristas redundantes mientras agregamos
        redundant_edges_count = 0
        redundant_details = []
        
        for link in links:
            if G.has_edge(link.source, link.target):
                redundant_edges_count += 1
                redundant_details.append({
                    "source": link.source,
                    "target": link.target,
                    "relation": link.relation
                })
            else:
                G.add_edge(link.source, link.target, relation=link.relation, value=link.value)

        total_nodes = G.number_of_nodes()
        total_edges = G.number_of_edges()

        if total_nodes == 0:
            return {"status": "empty_graph"}

        # 2. Análisis de grados (Nodos Aislados)
        in_degrees = dict(G.in_degree())
        out_degrees = dict(G.out_degree())
        
        isolated_nodes = []
        for n in G.nodes():
            if in_degrees[n] == 0 and out_degrees[n] == 0:
                isolated_nodes.append({
                    "id": n,
                    "confidence": G.nodes[n].get("confidence", 0.0)
                })

        # Nodos con grado 1 (solo entra o solo sale, sin participar en redes)
        degree_one_count = sum(1 for n in G.nodes() if (in_degrees[n] + out_degrees[n]) == 1)

        # 3. Componentes conectados (Comunidades estructurales)
        # Convertimos a no dirigido para conectividad débil
        G_undirected = G.to_undirected()
        components = list(nx.connected_components(G_undirected))
        
        # 4. Ciclos contradictorios (A -> B y B -> A)
        contradictory_cycles = []
        # Para grafos grandes, nx.simple_cycles(G, length_bound=2) es muy eficiente en NetworkX 3.0+
        # Si length_bound no soportado, buscamos ciclos de largo 2 manualmente:
        for u, v in G.edges():
            if G.has_edge(v, u):
                # Evitar contar el mismo ciclo dos veces (A->B, B->A y B->A, A->B)
                if u < v:  
                    contradictory_cycles.append({
                        "node_a": u,
                        "node_b": v,
                        "rel_a_to_b": G[u][v].get("relation", ""),
                        "rel_b_to_a": G[v][u].get("relation", "")
                    })

        return {
            "summary": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "total_components": len(components),
                "largest_component_size": len(max(components, key=len)) if components else 0
            },
            "metrics": {
                "isolated_nodes_count": len(isolated_nodes),
                "isolated_nodes_pct": round(len(isolated_nodes) / max(1, total_nodes) * 100, 2),
                "degree_one_nodes_count": degree_one_count,
                "degree_one_nodes_pct": round(degree_one_count / max(1, total_nodes) * 100, 2),
                "redundant_edges_count": redundant_edges_count,
                "contradictory_cycles_count": len(contradictory_cycles)
            },
            "details": {
                "isolated_nodes_sample": isolated_nodes[:20],
                "redundant_edges_sample": redundant_details[:10],
                "contradictory_cycles_sample": contradictory_cycles[:10]
            }
        }
        
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()
