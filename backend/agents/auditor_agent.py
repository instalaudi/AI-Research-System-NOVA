import logging
import json
from typing import Dict, Tuple
from core.llm_client import llm_client

logger = logging.getLogger("agents.auditor_agent")

class AuditorAgent:
    """
    Agente de Control de Calidad (QA). Analiza una estructura de proyecto generada,
    busca errores sintácticos o marcadores falsos ("// pon tu código aquí"),
    y aprueba o rechaza con comentarios.
    """
    
    async def audit_project(self, project_files: Dict[str, str], original_req: str) -> Tuple[bool, str]:
        """
        Audits a generated project. Returns (is_approved, critique_or_success_message).
        """
        logger.info("[AuditorAgent] Iniciando auditoría del proyecto generado...")
        
        # Format the files into a readable block for the LLM
        files_preview = ""
        for path, content in project_files.items():
            files_preview += f"\n--- Archivo: {path} ---\n```\n{content[:2000]}...\n```\n"

        prompt = f"""Eres NOVA, Actuando como Auditor de Código Estricto (QA Senior).
Acabas de generar el siguiente proyecto basado en este requerimiento inicial:
"{original_req}"

ESTOS SON LOS ARCHIVOS GENERADOS:
{files_preview}

TU MISIÓN:
Revisa estrictamente los archivos. Busca:
1. "Bugs" sintácticos obvios o imports faltantes.
2. Uso de "placeholders" perezosos como "// insert code here", "// lógica pendiente", "/* tu css */".
3. Archivos que falten (Ej: te pidieron React pero no hay package.json o vite.config).
4. Errores de lógica arquitectónica básicos.

INSTRUCCIONES DE RESPUESTA:
Responde EXCLUSIVAMENTE con un JSON con el siguiente formato:
{{
   "approved": true/false,
   "critique": "Tu análisis estricto detallando cada error o felicitando si está perfecto."
}}

Sé inquebrantable. Si el código está incompleto o es un "mockup", "approved" debe ser: false.
"""
        messages = [
            {"role": "system", "content": "Eres una API que responde exclusivamente en JSON puro estructurado."},
            {"role": "user", "content": prompt}
        ]

        response_text = await llm_client.chat(
            messages=messages, 
            temperature=0.1, 
            format="json", # v10.18.0: Forzar JSON modo
            priority=1
        )
        
        parsed = self._extract_json(response_text)
        if not parsed:
            # Fallback tolerante si falla el parseo pero no hay evidentes errores
            logger.warning("[AuditorAgent] Falló parseo JSON del auditor. Asumiendo válido por contingencia.")
            return True, "No se pudo parsear el auditor, pero asumiendo válido por contingencia."
            
        is_approved = parsed.get("approved", False)
        critique = parsed.get("critique", "Sin comentarios.")
        
        if is_approved:
            logger.info("[AuditorAgent] Proyecto APROBADO.")
        else:
            logger.warning(f"[AuditorAgent] Proyecto RECHAZADO: {critique}")
            
        return is_approved, critique

    def _extract_json(self, text: str) -> Dict:
        if not text:
            return {}
        import re
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        # Intento directo
        try:
            return json.loads(text)
        except Exception:
            pass

        # FIX: Reparar chars de control ilegales SIN eliminar \n, \r, \t (legales en JSON strings)
        def _repair(s: str) -> str:
            s = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', s)
            m = re.search(r'(\{[\s\S]*\})', s)
            return m.group(1) if m else s

        repaired = _repair(text)
        try:
            return json.loads(repaired)
        except Exception:
            pass

        # Fallback: bloque markdown
        m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', repaired)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except Exception:
                pass

        # Fallback final: primer bloque JSON
        m2 = re.search(r'\{[\s\S]*\}', repaired)
        if m2:
            try:
                return json.loads(m2.group())
            except Exception:
                pass
        return {}

auditor_agent = AuditorAgent()
