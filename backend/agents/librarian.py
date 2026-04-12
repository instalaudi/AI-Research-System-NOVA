from typing import Dict, Any, Optional
from agents.base_agent import BaseAgent # type: ignore
from core.knowledge_base import knowledge_base # type: ignore
from core.llm_client import llm_client # type: ignore
import json
import re

class LibrarianAgent(BaseAgent):
    def __init__(self):
        super().__init__("Librarian") # type: ignore

    async def execute(self, content: Dict[str, Any], user_id: Optional[int] = None, **kwargs):
        """
        Stores non-duplicate content in the knowledge base.
        """
        # Real semantic deduplication using VectorDB
        from core.vector_db import vector_db # type: ignore
        is_duplicate = False 
        
        try:
            # FIX: Verificar top-3 resultados similares con umbral ampliado (0.25)
            # El umbral original de 0.1 solo capturaba duplicados casi exactos.
            # Con 0.25 se detectan paráfrasis y reformulaciones del mismo contenido.
            text_to_check = f"{content.get('title')}\n{content.get('summary')}"
            similar = vector_db.search_similar(text_to_check, limit=3)
            for candidate in similar:
                if candidate["distance"] < 0.25:
                    print(f"[{self.name}] Semantic duplicate detected: "
                          f"{candidate['metadata'].get('title')} "
                          f"(dist: {candidate['distance']:.4f})")
                    is_duplicate = True
                    break
        except Exception as e:
            print(f"[{self.name}] Deduplication check failed, proceeding: {e}")
        
        if not is_duplicate:
            # Senior Improv 5: Semantic Bridging
            res_topic = content.get("research_topic")
            current_concepts = content.get("concepts", [])
            if res_topic:
                if res_topic not in current_concepts:
                    current_concepts.append(res_topic)
                content["concepts"] = current_concepts

            # PHASE 11: Dynamic Knowledge Graph Extraction
            try:
                # BUG-01 FIX: Consistent use of 'content' or 'summary'
                text_to_kg = f"Titulo: {content.get('title')}\nContenido: {content.get('content') or content.get('summary') or 'Sin contenido'}"
                kg_prompt = f"""
                Extrae las 3-5 relaciones más importantes del siguiente texto para un Knowledge Graph.
                Responde ÚNICAMENTE con un objeto JSON válido, estrictamente con el formato: 
                {{"triplets": [["Sujeto", "Relación", "Objeto"]]}}
                Asegúrate de no incluir markdown ni texto antes o después del JSON.
                Ejemplo: {{"triplets": [["Bitcoin", "usa", "Proof of Work"]]}}
                
                Texto:
                {text_to_kg}
                """
                kg_res = await llm_client.chat([{"role": "user", "content": kg_prompt}], priority=1)
                kg_res_clean = kg_res.replace("```json", "").replace("```", "").strip()
                kg_match = re.search(r'\{.*\}', kg_res_clean, re.DOTALL)
                if kg_match:
                    kg_data = json.loads(kg_match.group())
                    content["triplets"] = kg_data.get("triplets", [])
                    print(f"[{self.name}] Grafos extraídos: {len(content['triplets'])} relaciones")
            except Exception as kge:
                print(f"[{self.name}] Error en extracción de KG: {kge}")
 
            # Set normalized scores
            content["novelty_score"] = 0.9
            quality_flag = content.get("quality_flag", "full_pipeline")
            
            # BUG-03/Librarian Fix: Use scores from analyzer if available
            if quality_flag == "unverified_but_stored":
                content["confidence_score"] = min(float(content.get("review_score", 0.3)), 0.3)
            else:
                # Default to review_score but allow analyzer's confidence_score to pass through if present
                content["confidence_score"] = float(content.get("confidence_score") or content.get("review_score", 0.8))
            
            content["source_score"] = 0.85

            # ── Segundo filtro de calidad: penalizar fuentes no académicas en zona borderline ──
            # Si la fuente es un blog/GitHub/Reddit Y la confianza está en zona gris (0.65-0.73),
            # aplicamos un 10% de penalización. Reduce el impacto en la confianza promedio sin bloquear.
            source_url = str(content.get("url") or content.get("source") or "").lower()
            non_academic_indicators = ["github.com", "medium.com", "reddit.com", "dev.to",
                                       "hashnode.dev", "blogger.com", "wordpress.com", "substack.com"]
            current_confidence = content.get("confidence_score", 0.0)
            is_non_academic = any(ind in source_url for ind in non_academic_indicators)
            if is_non_academic and 0.65 <= current_confidence <= 0.73:
                penalized = round(current_confidence * 0.90, 3)
                print(f"[{self.name}] ⚠️ Fuente no académica borderline ({source_url[:40]}): "
                      f"confidence {current_confidence:.2f} → {penalized:.2f} (-10%)")
                content["confidence_score"] = penalized
                content["quality_flag"] = content.get("quality_flag", "") + "|non_academic_source"


            from core.knowledge_base import knowledge_base # type: ignore
            print(f"[{self.name}] Guardando conocimiento real: {content.get('title')} "
                  f"(confianza: {content.get('confidence_score', 0):.2f}, User: {user_id})")
            await knowledge_base.add_entry(content, user_id=user_id)
            return True
        else:
            print(f"[{self.name}] Conocimiento duplicado omitido: {content.get('title')}")
            return False
