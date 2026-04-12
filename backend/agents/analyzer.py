import json
from typing import Dict, Any, List
from agents.base_agent import BaseAgent # type: ignore
from core.llm_client import llm_client # type: ignore
from core.utils import parse_llm_json # type: ignore

class AnalyzerAgent(BaseAgent):
    def __init__(self):
        super().__init__("Analyzer") # type: ignore

    async def execute(self, article: Dict[str, Any], **kwargs):
        """
        Analyzes the article using full_content and provides historical context.
        """
        context = kwargs.get("context", None)
        print(f"[{self.name}] Analyzing real article: {article.get('title')}")
        
        from core.content_sanitizer import sanitize_for_prompt # type: ignore
        raw_content = article.get('full_content') or article.get('summary') or "Sin contenido disponible"
        content_to_analyze = sanitize_for_prompt(raw_content)
        context_str = "\n- ".join(context) if context else "Ninguno"
        
        prompt = f"""
        Actúa como un Analista de Investigación Senior y Extractor de Conocimiento.
        Analiza el siguiente contenido y genera un resumen profundo Y un conjunto de TRIPLETAS DE CONOCIMIENTO (Sujeto, Relación, Objeto).
        
        CONTEXTO HISTÓRICO (Temas ya investigados):
        - {context_str}
        
        Título: {article.get('title')}
        Contenido: {content_to_analyze}
        
        INSTRUCCIONES DE TRIPLETAS:
        Extrae al menos 3 tripletas que definan conceptos clave. Ejemplos:
        - ["Lidar", "es_un_tipo_de", "Sensor"]
        - ["Navegación Autónoma", "utiliza", "Lidar"]
        
        Genera un resumen ejecutivo de 3 párrafos.
        
        SISTEMA: Responde EXCLUSIVAMENTE con un objeto JSON válido. 
        NO incluyas explicaciones, NO incluyas markdown, NO incluyas texto antes o después del JSON.
        
        Ejemplo de formato requerido:
        {{
            "title": "...",
            "content": "...",
            "concepts": ["Concepto1", "Concepto2"],
            "triplets": [["Sujeto", "Relación", "Objeto"]],
            "category": "Tecnología"
        }}
        """
        
        messages = [{"role": "user", "content": prompt}]
        response_text = await llm_client.chat(messages, format="json", priority=1)
        
        if response_text and response_text.startswith("SYSTEM_BUSY"):
            raise Exception("SYSTEM_BUSY")
            
        try:
            data = parse_llm_json(response_text)
            
            # BUG-01 FIX: Ensure 'content' key exists for backend consistency
            if "summary" in data and "content" not in data:
                data["content"] = data.pop("summary")
            elif "content" not in data:
                data["content"] = article.get("summary") or article.get("full_content") or "Sin resumen disponible"

            data["original_url"] = article.get("url")
            data["research_topic"] = article.get("research_topic")
            data["is_fallback"] = False
            data["quality_flag"] = "full_pipeline"
            
            # FIX-5.4: Preserve and incorporate relevance_score from research
            relevance_score = float(article.get("relevance_score", 1.0))
            data["relevance_score"] = relevance_score
            
            # BUG-03 FIX: Add confidence scores to successful path
            # Adjust final confidence based on research relevance
            llm_confidence = float(data.get("confidence_score", 0.9))
            data["confidence_score"] = round(llm_confidence * relevance_score, 3)
            data["review_score"] = data.get("review_score", 0.8)
            
            return data
        except Exception as e:
            print(f"[{self.name}] Error parsing LLM response: {e}")
            return {
                "title": article.get("title"),
                "summary": article.get("summary") or "Error en análisis",
                "concepts": ["Error de Análisis"],
                "category": "General",
                "original_url": article.get("url"),
                "is_fallback": True,
                "quality_flag": "fallback",
                "confidence_score": 0.4, # Minimal score for fallbacks
                "review_score": 0.4
            }
