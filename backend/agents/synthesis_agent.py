from typing import Dict, Any, List
import json
from agents.base_agent import BaseAgent
from core.llm_gateway import llm_gateway
from core.database import SessionLocal, KnowledgeEntry, KnowledgeNode, GraphLink

class SynthesisAgent(BaseAgent):
    def __init__(self):
        super().__init__("Synthesis")

    async def execute(self, query: str, **kwargs) -> str:
        """
        Answers a user query by synthesising knowledge from the Triple Store.
        """
        print(f"[{self.name}] Synthesizing answer for: {query}")
        
        db = SessionLocal()
        from core.knowledge_base import knowledge_base
        try:
            # 1. Retrieval
            from core.text_utils import extract_keywords
            keywords = extract_keywords(query)
            
            # Use a dict for deduplication to avoid unhashable type error with set(relevant_entries)
            relevant_entries_dict = {}
            matched_concepts = set()
            
            for kw in keywords:
                entries = db.query(KnowledgeEntry).filter(
                    (KnowledgeEntry.title.contains(kw)) | (KnowledgeEntry.concepts.contains(kw))
                ).limit(3).all()
                for e in entries:
                    relevant_entries_dict[e.id] = e # Deduplicate by entry ID
                    if e.concepts:
                        matched_concepts.update([c.strip() for c in e.concepts.split(",") if c.strip()])
            
            # 2. Optimized Graph Retrieval
            triplets = set()
            if matched_concepts:
                # Optimized: Use IN operator for all concepts in a single query
                concepts_list = list(matched_concepts)
                links = db.query(GraphLink).filter(
                    (GraphLink.source.in_(concepts_list)) | (GraphLink.target.in_(concepts_list))
                ).limit(30).all() # Global limit for synthesis
                
                for l in links:
                    triplets.add(f"{l.source} --({l.relation})--> {l.target}")

            # 3. Scientific Honesty Stats
            # FIX: Limitar a MAX_CONCEPTS=50 para evitar cláusulas SQL IN demasiado grandes
            MAX_CONCEPTS = 50
            stats = await knowledge_base.get_concept_stats(list(matched_concepts)[:MAX_CONCEPTS])
            
            # 4. Context Construction
            relevant_entries = list(relevant_entries_dict.values())
            context_parts = []
            for e in relevant_entries:
                content_snip = e.content[:400] if e.content else "Sin contenido"
                context_parts.append(f"ARTÍCULO: {e.title}\nRESUMEN: {content_snip}...")
            
            context_text = "\n\n".join(context_parts)
            graph_text = "\n".join(list(triplets))
            
            prompt = f"""
            Actúa como un INVESTIGADOR CIENTÍFICO SENIOR. Responde a la pregunta del usuario con total honestidad intelectual.
            
            ESTRUCTURA OBLIGATORIA DE RESPUESTA:
            1. Análisis del conocimiento disponible (Menciona qué conceptos clave hemos encontrado).
            2. Relaciones encontradas (Menciona las conexiones del grafo de tripletas).
            3. Síntesis (La respuesta final basada en la combinación de datos).
            4. Métricas de Certeza (Confidence, Sources, Consensus).
            
            DATOS DE LA BASE DE CONOCIMIENTO:
            - RELACIONES: {graph_text if graph_text else "No hay relaciones gráficas encontradas."}
            - ARTÍCULOS: {context_text if context_text else "No hay artículos específicos encontrados."}
            
            PREGUNTA: {query}
            
            MÉTRICAS DEL SISTEMA:
            - Confidence: {stats['confidence']:.2f}
            - Sources: {stats['source_count']}
            - Consensus: {stats['consensus']}
            """
            
            messages = [{"role": "user", "content": prompt}]
            response = await llm_gateway.chat(messages, lane="batch", temperature=0.2, priority=1, ignore_overdrive=True)
            return response

        finally:
            db.close()
