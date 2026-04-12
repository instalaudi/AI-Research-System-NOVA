from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from core.database import SessionLocal, KnowledgeNode, GraphLink

class NavigatorAgent(BaseAgent):
    def __init__(self):
        super().__init__("Navigator")

    async def execute(self, topic: str, **kwargs) -> str:
        """
        Explores the graph to build a hierarchical tree of knowledge related to the topic.
        """
        print(f"[{self.name}] Navigating knowledge tree for: {topic}")
        db = SessionLocal()
        try:
            # 1. Precise match or near match for the root node
            root_node = db.query(KnowledgeNode).filter(KnowledgeNode.id.contains(topic)).first()
            if not root_node:
                return f"No tengo un mapa conceptual detallado sobre '{topic}'. Intenta investigar el tema primero."

            # 2. Build the Tree (BFS limited to 2 levels)
            tree = self._build_tree(db, root_node.id, depth=0, max_depth=2, visited=set())
            
            # 3. Format Response as Scientific Tree
            response = f"### Mapa de Conocimiento: {root_node.id}\n\n"
            response += "He explorado mi base de datos interna y estas son las conexiones jerárquicas encontradas (bidireccionales):\n\n"
            # FIX: Limitar la salida del árbol para evitar desborde en Telegram/chat
            MAX_TREE_CHARS = 3000
            tree_text = self._render_tree(tree)
            if len(tree_text) > MAX_TREE_CHARS:
                tree_text = tree_text[:MAX_TREE_CHARS] + "\n\n*... (mapa truncado por longitud máxima)*"
            response += tree_text
            response += "\n\n*Puedes profundizar en cualquiera de estos subtemas con una pregunta específica.*"
            return response
            
        finally:
            db.close()

    def _build_tree(self, db, node_id: str, depth: int, max_depth: int, visited: set) -> Dict:
        if depth > max_depth or node_id in visited:
            return None
        
        visited.add(node_id)
        children = []
        
        # Find links where this node is either SOURCE or TARGET (Bidirectional)
        links = db.query(GraphLink).filter(
            (GraphLink.source == node_id) | (GraphLink.target == node_id)
        ).limit(10).all() # Limit to avoid response explosion
        
        for link in links:
            # Determine the other end of the link
            neighbor_id = link.target if link.source == node_id else link.source
            
            if neighbor_id in visited: continue
            
            child_tree = self._build_tree(db, neighbor_id, depth + 1, max_depth, visited)
            children.append({
                "id": neighbor_id,
                "relation": link.relation if link.source == node_id else f"invert-{link.relation}",
                "subtree": child_tree
            })
            
        return {"id": node_id, "children": children}

    def _render_tree(self, tree: Dict, prefix: str = "") -> str:
        if not tree or not tree.get("id"): return ""
        
        output = f"{prefix}**{tree['id']}**\n"
        
        for i, child in enumerate(tree.get("children", [])):
            is_last = i == len(tree["children"]) - 1
            curr_prefix = "└── " if is_last else "├── "
            rel_prefix = f"    ({child['relation']}) "
            
            output += f"{prefix}{curr_prefix}{rel_prefix}**{child['id']}**\n"
            if child["subtree"]:
                next_prefix = prefix + ("    " if is_last else "│   ")
                output += self._render_tree(child["subtree"], next_prefix)
                
        return output
