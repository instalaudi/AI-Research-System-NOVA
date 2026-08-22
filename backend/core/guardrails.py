"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v14.0 — Guardrails Anti-Alucinación y Fidelidad Fáctica║
║  Archivo: core/guardrails.py                                 ║
║  Evalúa la fidelidad de las respuestas contrastándolas       ║
║  con el contexto RAG recuperado para prevenir alucinaciones. ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("core.guardrails")

# Stopwords y verbos conectores comunes para análisis de entidades fácticas
STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en", "y", "a", "que", "es", "son",
    "por", "para", "con", "se", "su", "sus", "al", "lo", "como", "mas", "pero", "este", "esta", "estos", "estas",
    "crea", "crear", "utiliza", "utilizar", "usa", "usar", "ajusta", "ajustar", "optimizar", "hace", "hacer",
    "puede", "pueden", "debe", "deben", "ser", "estar", "tiene", "tienen", "hay", "sobre", "entre", "sin",
    "the", "a", "an", "is", "are", "and", "or", "in", "on", "of", "to", "for", "with", "by", "that", "this",
    "use", "using", "uses", "make", "create", "set", "adjust", "optimize", "can", "should", "from"
}


class HallucinationGuardrail:
    """
    Evaluador determinista de fidelidad fáctica (*Faithfulness*) y relevancia.
    Detecta afirmaciones sin sustento en el contexto RAG recuperado.
    """
    def __init__(self, hallucination_threshold: float = 0.40):
        self.hallucination_threshold = hallucination_threshold


    @staticmethod
    def _extract_factual_claims(text: str) -> List[str]:
        """Extrae términos fácticos, identificadores, números y nombres propios del texto."""
        if not text:
            return []
        
        # Palabras de más de 2 caracteres que no sean stopwords
        words = re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', text.lower())
        claims = [w for w in words if w not in STOPWORDS and not w.isdigit()]
        return list(set(claims))

    def evaluate_faithfulness(self, answer: str, context_chunks: List[str]) -> Dict[str, Any]:
        """
        Evalúa si la respuesta generada está respaldada por los fragmentos de contexto.
        Retorna score de fidelidad (0.0 a 1.0) y alerta de alucinación.
        """
        if not answer or not answer.strip():
            return {"faithfulness_score": 0.0, "is_hallucination": True, "ungrounded_terms": []}

        if not context_chunks:
            # Si no hubo contexto RAG solicitado, la fidelidad se asume neutra
            return {
                "faithfulness_score": 1.0,
                "is_hallucination": False,
                "ungrounded_terms": [],
                "note": "Consulta sin contexto RAG previo (conocimiento base del modelo)"
            }

        answer_claims = self._extract_factual_claims(answer)
        if not answer_claims:
            return {"faithfulness_score": 1.0, "is_hallucination": False, "ungrounded_terms": []}

        # Construir corpus unificado de contexto
        context_corpus = " ".join(context_chunks).lower()

        grounded_count = 0
        ungrounded_terms = []

        for claim in answer_claims:
            if claim in context_corpus:
                grounded_count += 1
            else:
                ungrounded_terms.append(claim)

        faithfulness_score = round(grounded_count / len(answer_claims), 4)
        is_hallucination = faithfulness_score < self.hallucination_threshold

        if is_hallucination:
            logger.warning(
                f"[Guardrails] ⚠️ Posible alucinación detectada (Score: {faithfulness_score:.2f} < {self.hallucination_threshold}). "
                f"Términos no respaldados: {ungrounded_terms[:5]}"
            )

        return {
            "faithfulness_score": faithfulness_score,
            "is_hallucination": is_hallucination,
            "grounded_terms_count": grounded_count,
            "total_claims_count": len(answer_claims),
            "ungrounded_terms": ungrounded_terms[:10]
        }

    def evaluate_relevance(self, query: str, answer: str) -> Dict[str, Any]:
        """Evalúa si la respuesta aborda el tema de la consulta del usuario."""
        query_terms = self._extract_factual_claims(query)
        if not query_terms:
            return {"relevance_score": 1.0, "is_relevant": True}

        answer_lower = answer.lower()
        matched = sum(1 for term in query_terms if term in answer_lower)
        relevance_score = round(matched / len(query_terms), 4)

        return {
            "relevance_score": relevance_score,
            "is_relevant": relevance_score >= 0.4
        }

    def audit_response(self, query: str, answer: str, context_chunks: Optional[List[str]] = None) -> Dict[str, Any]:
        """Audita completamente una respuesta retornando métricas de seguridad y fidelidad."""
        faithfulness = self.evaluate_faithfulness(answer, context_chunks or [])
        relevance = self.evaluate_relevance(query, answer)

        overall_safe = (not faithfulness["is_hallucination"]) and relevance["is_relevant"]

        return {
            "overall_safe": overall_safe,
            "faithfulness": faithfulness,
            "relevance": relevance
        }


# Instancia global del Guardrail
hallucination_guardrail = HallucinationGuardrail()
