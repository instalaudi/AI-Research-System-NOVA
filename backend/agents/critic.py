import json
from typing import Dict, Any
from agents.base_agent import BaseAgent # type: ignore
from core.llm_gateway import llm_gateway # type: ignore
from core.utils import parse_llm_json # type: ignore

class CriticAgent(BaseAgent):
    def __init__(self):
        super().__init__("Critic") # type: ignore

    async def execute(self, analysis: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Reviews the analyzer's output for quality using real LLM.
        """
        print(f"[{self.name}] Reviewing quality for: {analysis.get('title')}")
        
        # Correctly pass temperature to llm_client
        payload_options = {"temperature": 0.5}  # FIX-1: Balanced strictness
        
        prompt = f"""
        Eres un revisor de calidad equilibrado. Evalúa el siguiente análisis de investigación.
        Título: {analysis.get('title')}
        Resumen: {analysis.get('summary')}
        Conceptos: {', '.join(analysis.get('concepts', []))}
        
        Criterios de evaluación:
        - Si el resumen tiene sentido, extrae conceptos claros y no inventa hechos: puntúa entre 0.5 y 0.8.
        - Solo puntúa por debajo de 0.4 si hay errores evidentes, contradicciones o contenido claramente inventado.
        - Un resumen breve pero correcto y con conceptos útiles merece al menos 0.5.
        
        Calcula review_score (float 0.0-1.0) y escribe una crítica breve (critique).
        Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después.
        Formato:
        {{
            "review_score": (float entre 0.0 y 1.0),
            "critique": (string breve)
        }}
        """
        
        messages = [{"role": "user", "content": prompt}]
        # Pass temperature to the chat call
        response_text = await llm_gateway.chat(messages, lane="batch", format="json", temperature=payload_options["temperature"], priority=1, ignore_overdrive=True)
        
        try:
            data = parse_llm_json(response_text)
            raw_score = float(data.get("review_score", 0.5))
            # FIX-3.2: Removed artificial score floor that bypassed QUALITY_THRESHOLD
            analysis["review_score"] = min(1.0, max(0.0, raw_score))
            analysis["critique"] = data.get("critique", "Sin crítica disponible.")
            analysis["is_fallback"] = analysis.get("is_fallback", False) or False
        except Exception as e:
            print(f"[{self.name}] Error in critic review: {e}")
            analysis["review_score"] = 0.5
            analysis["critique"] = "Error procesando la crítica."
            analysis["is_fallback"] = True
            analysis["quality_flag"] = "critic_fallback"
            
        return analysis
