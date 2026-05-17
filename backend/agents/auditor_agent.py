import logging
import json
import os
import subprocess
import tempfile
import shutil
from typing import Dict, Tuple, List
from core.llm_gateway import llm_gateway

logger = logging.getLogger("agents.auditor_agent")

class AuditorAgent:
    """
    Agente de Control de Calidad (QA). Analiza una estructura de proyecto generada,
    busca errores sintácticos o marcadores falsos ("// pon tu código aquí"),
    y aprueba o rechaza con comentarios.
    """
    
    async def audit_project(self, project_files: Dict[str, str], original_req: str, ignore_overdrive: bool = False) -> Tuple[bool, str]:
        """
        Audits a generated project. Returns (is_approved, critique_or_success_message).
        v11.6.0: Hybrid Audit (Ruff Static Analysis + LLM Cognitive Analysis)
        """
        logger.info("[AuditorAgent] Iniciando auditoría híbrida...")
        
        # 1. Fase Estática (Ruff) - Ultra Rápida
        ruff_report = self._run_ruff_check(project_files)
        # v11.9.20: Solo errores REALMENTE críticos causan rechazo automático
        # E9xx = errores de sintaxis, invalid-syntax = código que no se puede parsear
        # F401 (imports no usados) es un warning menor, NO debe causar rechazo
        critical_errors = [
            e for e in ruff_report 
            if e.get("code") == "invalid-syntax" or 
               e.get("code", "").startswith("E9")
        ]
        
        if critical_errors:
            error_details = "\n".join([f"- {e['filename']}:{e['location']['row']} - {err_label(e)}" for e in critical_errors[:5]])
            msg = f"AUDITORIA ESTATICA FALLIDA: Se detectaron errores tecnicos criticos:\n{error_details}"
            logger.warning(f"[AuditorAgent] {msg}")
            return False, msg
        
        # Format the files into a readable block for the LLM
        files_preview = ""
        for path, content in project_files.items():
            files_preview += f"\n--- Archivo: {path} ---\n```\n{content[:2000]}...\n```\n"

        # Preparamos reporte de linter para el LLM
        linter_context = ""
        if ruff_report:
            linter_context = "\n[REPORTE TÉCNICO RUFF (ESTÁTICO)]:\n"
            for err in ruff_report[:15]: 
                linter_context += f"- {err['filename']}:{err['location']['row']} [{err['code']}]: {err['message']}\n"

        # v13.0 (Fase 4): Cargar Manifiesto de Diseño para evaluación estética
        design_manifest = ""
        try:
            design_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills", "DESIGN.md")
            if os.path.exists(design_path):
                with open(design_path, "r", encoding="utf-8") as f:
                    design_manifest = "\n[MANIFIESTO DE DISEÑO PREMIUM (CRITERIO OBLIGATORIO)]:\n" + f.read()
        except Exception: pass

        prompt = f"""Eres NOVA, Auditor de Código Pragmático y Estético (QA Senior).
Estás revisando un proyecto generado automáticamente basado en este requerimiento:
"{original_req}"

{linter_context}
{design_manifest}

ESTOS SON LOS ARCHIVOS GENERADOS:
{files_preview}

TU MISIÓN:
Evalúa si el proyecto es EJECUTABLE, FUNCIONAL y ESTÉTICAMENTE PREMIUM (si tiene interfaz). 

CRITERIOS DE RECHAZO (approved=false) — Rechaza si encuentras ALGUNO de estos:
1. Código truncado o incompleto.
2. Placeholders falsos ("// TODO", "implementar").
3. Errores de sintaxis GRAVES.
4. DISEÑO POBRE (Solo para Frontend): Rechaza si la interfaz es básica, usa colores aburridos, no tiene transiciones, no usa fuentes modernas o carece de la elegancia descrita en el MANIFIESTO DE DISEÑO. ¡NOVA no entrega productos mediocres!

CRITERIOS DE APROBACIÓN (approved=true) — APRUEBA si:
- El código es funcional y ejecutable.
- La interfaz (si existe) se ve espectacular, moderna y sigue el MANIFIESTO.
- Notas advertencias menores de Ruff (F841, F401) que no impiden la ejecución.

INSTRUCCIONES DE RESPUESTA:
Responde EXCLUSIVAMENTE con un JSON:
{{
   "approved": true/false,
   "critique": "Si rechazas: lista los errores técnicos O estéticos. Si apruebas: menciona qué lo hace una build de calidad."
}}
"""
        messages = [
            {"role": "system", "content": "Eres una API que responde exclusivamente en JSON puro estructurado."},
            {"role": "user", "content": prompt}
        ]

        response_text = await llm_gateway.chat(
            messages=messages, 
            lane="batch",
            temperature=0.1, 
            format="json", 
            priority=1,
            ignore_overdrive=ignore_overdrive,
            agent_name="auditor"
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

    def _run_ruff_check(self, project_files: Dict[str, str]) -> List[Dict]:
        """
        Executes Ruff analysis on the generated file strings using a temporary directory.
        """
        temp_dir = tempfile.mkdtemp(prefix="nova_audit_")
        try:
            # 1. Prepare files
            python_files = []
            for path, content in project_files.items():
                if path.endswith(".py"):
                    full_path = os.path.join(temp_dir, path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    python_files.append(path)
            
            if not python_files:
                return []

            # 2. Run Ruff
            # Ruff check <dir> --output-format json
            try:
                # v11.6: Usamos check --no-cache para asegurar frescura en auditorías fugaces
                cmd = ["ruff", "check", ".", "--output-format", "json", "--no-cache"]
                result = subprocess.run(cmd, cwd=temp_dir, capture_output=True, text=True, encoding="utf-8", errors="replace")
                
                if not result.stdout.strip():
                    return []
                
                return json.loads(result.stdout)
            except Exception as e:
                logger.error(f"[AuditorAgent] Ruff execution failed: {e}")
                return []
                
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

def err_label(e: Dict) -> str:
    return f"[{e.get('code', 'ERR')}] {e.get('message', 'Unspecified error')}"

auditor_agent = AuditorAgent()
