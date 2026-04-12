import json
import logging
from typing import Dict, Any, Optional
from core.llm_client import llm_client
from agents.auditor_agent import auditor_agent

logger = logging.getLogger("agents.developer_agent")

class DeveloperAgent:
    """
    Agent responsible for designing, structuring, and coding complete multi-file projects.
    Returns a structured dictionary matching required files and their absolute code content.
    """
    
    async def build_project(self, requirement: str) -> Dict[str, str]:
        """
        Accepts a user requirement (e.g. 'Build a React dashboard') and 
        returns a dictionary where keys are file paths and values are code.
        """
        logger.info(f"[DeveloperAgent] Initiating project build for: {requirement[:50]}...")
        
        prompt = f"""Eres NOVA, Arquitecta de Software Principal e Ingeniera de Software de Élite.
El usuario ha solicitado construir el siguiente proyecto complejo:

"{requirement}"

TU MISIÓN:
1. Diseña la arquitectura ideal para este proyecto garantizando calidad de producción, rendimiento extremo y mejores prácticas de la industria.
2. Escribe el código COMPLETO, FUNCIONAL y LISTO PARA DESPLEGAR de cada archivo necesario sin dejar nada a medias.
3. ESTRICTAMENTE PROHIBIDO usar *placeholders* como "// código aquí", "tu_api_key_aqui" ni recortar las implementaciones.
4. REGLA DE ORO 1: Si usas una librería (ej. axios, react), ASEGÚRATE de importarla en los scripts y REGISTRARLA obligatoriamente en package.json o requirements.txt.
5. REGLA DE ORO 2: NUNCA escribas API Keys fijas (hardcoded). Provee un archivo `.env.example` y lee las variables a través de `process.env` o bibliotecas equivalentes usando dotenv.
6. REGLA DE ORO 3: Maneja todos los errores de red, asíncronos y posibles fallos (ej. bloque de un try/catch) arrojando advertencias en consola claras, en vez de asumir que todo funcionará.
7. REGLA DE ORO 4 (ESTÉTICA PREMIUM): Para aplicaciones Frontend/Web, es OBLIGATORIO crear un diseño espectacular y vanguardista (Modern UI/UX). Usa colores vibrantes, paletas HSL, sombras suaves (glassmorphism), tipografías modernas y transiciones/animaciones CSS. ¡Un diseño básico y aburrido será RECHAZADO!
8. REGLA DE ORO 5 (EVITAR CONFLICTO DE PUERTOS): NUNCA configures servidores en el puerto 3000 o 8000 (ya que están ocupados por NOVA). Usa siempre el puerto 3001, 8080 o similares por defecto en tus scripts.
9. REGLA DE ORO 6 (DOCUMENTACIÓN OBLIGATORIA): TODOS los proyectos deben incluir estrictamente un archivo `README.md` muy detallado. Este debe explicar el propósito del proyecto, los requisitos previos (ej. Node.js, Python), los pasos EXACTOS para instalar dependencias (ej. npm install) y cómo ejecutar el proyecto paso a paso, incluyendo cómo configurar el `.env`.
10. REGLA DE ORO 7 (MODULARIZACIÓN): PROHIBIDO poner todo el código en un solo archivo. Separa responsabilidades: lógica en `/services`, componentes en `/components`, utilidades en `/utils`. El código debe ser limpio y escalable.
11. REGLA DE ORO 8 (PROGRAMACIÓN DEFENSIVA): Valida SIEMPRE las entradas y respuestas de APIs. Usa valores por defecto o mensajes de error elegantes si los datos no llegan. NUNCA permitas que la app se rompa (crash) por datos nulos.
12. REGLA DE ORO 9 (KISS - KEEP IT SIMPLE): No uses librerías pesadas si no son estrictamente necesarias. Prefiere el código nativo y eficiente. El código debe ser fácil de leer y mantener.
13. Genera todo de forma integral: html, css, js, json de configuración, dependencias completas, validando que se llamen correctamente entre sí.

INSTRUCCIONES DE FORMATO ESTRICTO:
Debes responder ÚNICA Y ESTRICTAMENTE con un objeto JSON. No añadas introducciones, explicaciones ni etiquetas markdown separadas. El servidor parseará directamente tu respuesta.

El JSON debe tener este formato:
{{
  "project_name": "nombre_del_proyecto_sin_espacios",
  "files": [
    {{
      "path": "ruta/al/archivo/ejemplo.py",
      "content": "contenido real del archivo con saltos de línea \\n correctos escapados para JSON"
    }},
    {{
      "path": "index.html",
      "content": "codigo html completo"
    }}
  ]
}}

Escribe todo el código real dentro de la clave 'content'.
"""

        messages = [
            {"role": "system", "content": "Eres una API que responde exclusivamente en JSON puro estructurado."},
            {"role": "user", "content": prompt}
        ]

        files_dict = {}
        max_attempts = 5  # v10.9.8: Aumentado para mayor tolerancia en CPU
        # FIX: Guardar los 2 mensajes iniciales para poder restablecer el historial
        _initial_messages = messages[:2]
        consecutive_failures = 0

        for attempt in range(max_attempts):
            logger.info(f"[DeveloperAgent] Intentando generar código (Intento {attempt+1}/{max_attempts})...")
            response_text = await llm_client.chat(
                messages=messages,
                temperature=0.2,
                format="json",  # v10.18.0: Forzar JSON Nativo de Ollama
                priority=1,
                model=llm_client.coder_model # v11.0.0: Uso del Experto en Código especificado en config.py
            )

            parsed_data = self._extract_json(response_text)
            if not parsed_data:
                logger.warning("[DeveloperAgent] Falló el parseo JSON. Reintentando...")
                consecutive_failures += 1
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": "ERROR DE FORMATO: Tu respuesta no es un JSON válido. Asegúrate de escapar correctamente los saltos de línea con \\n dentro de las strings de código y no incluyas texto fuera del objeto JSON."})
                # FIX: Truncar historial cada 2 fallos consecutivos para evitar context overflow
                if consecutive_failures % 2 == 0:
                    logger.warning("[DeveloperAgent] Truncando historial para evitar overflow de contexto.")
                    messages = list(_initial_messages)
                continue

            consecutive_failures = 0  # Reset al tener parseo exitoso

            # Construir dict temporal
            temp_files = {}
            for file_entry in parsed_data.get("files", []):
                path = file_entry.get("path")
                content = file_entry.get("content")
                if path and content:
                    temp_files[path] = content

            if not temp_files:
                continue

            # Fase de Auditoría
            is_approved, critique = await auditor_agent.audit_project(temp_files, requirement)

            if is_approved:
                files_dict = temp_files
                break
            else:
                logger.warning(f"[DeveloperAgent] Auditor rechazó la build: {critique}")
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": f"El QA Auditor ha rechazado tu código por los siguientes motivos:\n\n{critique}\n\nPor favor, reescribe los archivos solucionando todos estos errores. No dejes placeholders."})
                files_dict = temp_files  # Guardar como fallback
                
        if not files_dict:
            raise ValueError("No se pudo generar un proyecto válido tras 5 intentos. El modelo falló en entregar un JSON estructurado.")

        return files_dict

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extracts and repairs JSON payload from a potentially messy or malformed string."""
        if not text:
            return None
        import re
        
        # 1. Limpieza base: Quitar tags de razonamiento y whitespace extremo
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        
        # 2. Intento de parseo directo
        try:
            return json.loads(text)
        except Exception:
            pass

        # 3. Reparación de caracteres de control (El enemigo #1 de JSON.loads)
        # Los LLMs a veces meten caracteres invisibles o saltos de línea reales dentro de strings
        def repair_json(s):
            # FIX: Eliminar SOLO caracteres de control verdaderamente ilegales en JSON.
            # Se preservan: \t (0x09), \n (0x0A), \r (0x0D) que son legales en strings JSON
            # y son comunes en contenido de código generado por el LLM.
            s = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', s)
            # Intentar capturar el bloque JSON si hay basura alrededor
            m = re.search(r'(\{[\s\S]*\})', s)
            return m.group(1) if m else s

        text = repair_json(text)

        # 4. Fallback: Parsear bloques markdown de todas formas
        m_md = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
        if m_md:
            try:
                return json.loads(m_md.group(1).strip())
            except Exception:
                pass

        # 5. Fallback final: Reparación agresiva de strings e impactos
        try:
            # Reemplazar saltos de línea reales dentro de valores por la secuencia \n
            # Esto es complejo pero ayuda con modelos perezosos
            # Buscamos patrones de "content": "..." donde el contenido tiene saltos reales
            text = re.sub(r',(\s*[\]}])', r'\1', text) # Comas finales
            return json.loads(text)
        except Exception as e:
            logger.debug(f"[DeveloperAgent] Error final de parseo: {e}")
            pass
            
        return None

developer_agent = DeveloperAgent()
