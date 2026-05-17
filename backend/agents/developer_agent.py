import json
import logging
import time
import difflib
import re
from typing import Dict, Any, Optional, Union, List
from core.llm_client import llm_client
from core.llm_gateway import llm_gateway
from agents.auditor_agent import auditor_agent

logger = logging.getLogger("agents.developer_agent")

class DeveloperAgent:
    """
    Agent responsible for designing, structuring, and coding complete multi-file projects.
    Returns a structured dictionary matching required files and their absolute code content.
    """
    
    async def build_project(self, requirement: str, user_id: Optional[int] = None, db_session: Optional[Any] = None) -> Dict[str, str]:
        """
        Accepts a user requirement (e.g. 'Build a React dashboard') and 
        returns a dictionary where keys are file paths and values are code.
        """
        if not requirement or not requirement.strip():
            raise ValueError("El requerimiento no puede estar vacío")
        
        start_time = time.time()
        # v11.9.0: Detectar proyectos complejos y usar estrategia incremental
        from services.system_service import system_service
        system_service.record_build_activity()
        
        if self._is_complex_project(requirement):
            logger.info("[DeveloperAgent] 🧩 Proyecto complejo detectado — usando generación incremental (2 fases)")
            try:
                result = await self._build_project_incremental(requirement, user_id, db_session)
                if result:
                    duration = time.time() - start_time
                    logger.info(f"[DeveloperAgent] Incremental build completed in {duration:.2f}s. Files: {len(result)}")
                    await self._save_to_cache(result, requirement, user_id, db_session, duration)
                    return result
            except Exception as e:
                logger.warning(f"[DeveloperAgent] Incremental build falló, usando método monolítico: {e}")
                # Fall through to monolithic method
        
        # SPRINT 1.1: Búsqueda en caché de snippets similares
        if user_id and db_session:
            try:
                from core.snippet_cache import SnippetCache
                snippet_cache = SnippetCache(db_session)
                
                # Buscar proyectos similares en el historial
                similar_snippets = snippet_cache.search(
                    user_id=user_id,
                    query=requirement,
                    limit=3
                )
                
                if similar_snippets:
                    logger.info(f"[DeveloperAgent] ✨ Encontrados {len(similar_snippets)} proyectos similares en caché")
                    reuse_candidate = self._try_reuse_cached_project(requirement, similar_snippets)
                    if reuse_candidate:
                        logger.info("[DeveloperAgent] ♻️ Reutilizando proyecto desde caché (>90% similar)")
                        return reuse_candidate
            except Exception as e:
                logger.warning(f"[DeveloperAgent] Error buscando en caché: {e}")

        user_preferences = "No hay preferencias específicas registradas. Usa mejores prácticas estándar."
        if user_id and db_session:
            try:
                from core.user_profile import UserProfile  # SPRINT 1.2
                profile_service = UserProfile(db_session)
                profile_style = profile_service.get_style(user_id)
                preferences_lines = [f"- Estilo de código: {profile_style.get('code_style', 'limpio y modular')}"]
                if profile_style.get("frameworks"):
                    preferences_lines.append(f"- Frameworks preferidos: {', '.join(profile_style['frameworks'])}")
                if profile_style.get("languages"):
                    preferences_lines.append(f"- Lenguajes favoritos: {', '.join(profile_style['languages'])}")
                if profile_style.get("patterns"):
                    preferences_lines.append(f"- Patrones frecuentes: {', '.join(profile_style['patterns'])}")
                user_preferences = "\n".join(preferences_lines)
            except Exception as e:
                logger.debug(f"[DeveloperAgent] Perfil de usuario no disponible aún: {e}")
        
        from core.telemetry import get_hardware_context
        hardware_ctx = get_hardware_context()

        # v12.0.0: Inyectar lecciones aprendidas de builds pasados
        lessons_context = ""
        try:
            from core.lessons_learned import lessons_db
            warnings = lessons_db.get_context_warnings("project_build")
            if warnings:
                lessons_context = "\n\nLECCIONES DE BUILDS ANTERIORES (EVITA estos errores):\n" + "\n".join(
                    f"  ⚠️ {w}" for w in warnings[:10]
                )
                logger.info(f"[DeveloperAgent] Inyectadas {len(warnings)} lecciones aprendidas en prompt")
        except Exception as e:
            logger.debug(f"[DeveloperAgent] No se pudieron cargar lecciones: {e}")
            
        # v13.0 (Fase 4): Inyectar Manifiesto de Diseño Premium
        design_manifest = ""
        try:
            import os
            design_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills", "DESIGN.md")
            if os.path.exists(design_path):
                with open(design_path, "r", encoding="utf-8") as f:
                    design_manifest = "\n\n--- MANIFIESTO DE DISEÑO PREMIUM (OBLIGATORIO PARA INTERFACES) ---\n" + f.read() + "\n--------------------------------------------------------------"
        except Exception as e:
            logger.debug(f"[DeveloperAgent] No se pudo cargar DESIGN.md: {e}")
        
        prompt = f"""Eres NOVA, Arquitecta de Software Principal e Ingeniera de Software de Élite.
El usuario ha solicitado construir el siguiente proyecto complejo:


"{requirement}"

PREFERENCIAS DEL USUARIO (DEBES SEGUIRLAS ESTRICTAMENTE):
{user_preferences}

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
13. REGLA DE ORO 10 (AUTOCONCIENCIA DE HARDWARE): {hardware_ctx} - ESTRICTAMENTE PROHIBIDO implementar frameworks pesados (ej. LangGraph, Kafka, PyTorch masivo) o arquitecturas que dependan de hardware que no poseemos. Prioriza soluciones bare-metal ultraligeras usando Python puro, Asyncio o librerías estándar.
14. Genera todo de forma integral: html, css, js, json de configuración, dependencias completas, validando que se llamen correctamente entre sí.
{lessons_context}

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
        max_attempts = 3  # v11.9.20: Reducido de 5 a 3 — si repite errores, más intentos no ayudan
        # FIX: Guardar los 2 mensajes iniciales para poder restablecer el historial
        _initial_messages = messages[:2]
        consecutive_failures = 0
        last_critique = ""  # v11.9.20: Tracking de críticas para detectar repetición

        for attempt in range(max_attempts):
            system_service.record_build_activity()
            logger.info(f"[DeveloperAgent] Intentando generar código (Intento {attempt+1}/{max_attempts})...")
            response_text = await llm_gateway.chat(
                messages=messages,
                lane="batch",
                temperature=0.2 + (attempt * 0.1),  # v11.9.20: Incrementar temperatura en reintentos
                format="json",  # v10.18.0: Forzar JSON Nativo de Ollama
                priority=1,
                model=llm_client.coder_model, # v11.0.0: Uso del Experto en Código especificado en config.py
                ignore_overdrive=True,
                agent_name="developer"
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

            # v11.9.20: Detección de contenido truncado ANTES de enviar al Auditor
            # El modelo frecuentemente genera HTML/JS truncado que desperdicia una llamada al Auditor
            truncated_files = []
            for fpath, fcontent in temp_files.items():
                if self._is_content_truncated(fcontent, fpath):
                    truncated_files.append(fpath)
            
            if truncated_files:
                logger.warning(f"[DeveloperAgent] ⚠️ Archivos truncados detectados: {truncated_files}. Saltando auditoría.")
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": (
                    f"ERROR CRÍTICO: Los siguientes archivos tienen contenido TRUNCADO o INCOMPLETO: {', '.join(truncated_files)}\n\n"
                    "Esto ocurre porque el código dentro de 'content' fue cortado antes de terminar.\n"
                    "SOLUCIÓN: Genera archivos MÁS CORTOS y SIMPLES. Reduce la cantidad de CSS y JavaScript.\n"
                    "Cada archivo debe estar COMPLETO hasta su última línea. NO dejes funciones, tags o bloques sin cerrar."
                )})
                files_dict = temp_files  # Guardar como fallback
                continue

            # Fase de Auditoría
            is_approved, critique = await auditor_agent.audit_project(temp_files, requirement, ignore_overdrive=True)

            if is_approved:
                files_dict = temp_files
                break
            else:
                logger.warning(f"[DeveloperAgent] Auditor rechazó la build: {critique}")
                
                # v11.9.20: Detección de errores repetidos — si la crítica es >80% similar
                # a la anterior, el modelo está atascado y más intentos no ayudarán
                if last_critique:
                    current_critique_str = " ".join(critique) if isinstance(critique, list) else str(critique)
                    last_critique_str = " ".join(last_critique) if isinstance(last_critique, list) else str(last_critique)
                    
                    similarity = difflib.SequenceMatcher(None, last_critique_str.lower(), current_critique_str.lower()).ratio()
                    if similarity > 0.80:
                        logger.error(
                            f"[DeveloperAgent] ❌ ABORT: Crítica del auditor repetida ({similarity:.0%} similar). "
                            f"El modelo no puede resolver estos errores. Abortando."
                        )
                        files_dict = temp_files  # Guardar como fallback (mejor que nada)
                        break
                
                last_critique = critique
                
                # v11.9.20: Extraer errores específicos para instrucciones "NO HACER"
                forbidden_patterns = self._extract_forbidden_patterns(critique)
                
                # v13.8.0: Bucle de Autocorrección Reflexivo (Fase 3)
                # Forzamos al modelo a "razonar" el error antes de generar el nuevo código
                reflection_msg = (
                    f"⚠️ EL QA AUDITOR HA RECHAZADO TU CÓDIGO POR LOS SIGUIENTES MOTIVOS:\n\n"
                    f"{critique}\n\n"
                    f"INSTRUCCIONES DE AUTOCORRECCIÓN (FASE 3):\n"
                    f"1. REFLEXIÓN TÉCNICA: Analiza por qué ocurrió este fallo (¿Sintaxis? ¿Placeholder? ¿Diseño mediocre?).\n"
                    f"2. SOLUCIÓN: Explica brevemente cómo vas a corregirlo.\n"
                    f"3. RE-ESCRITURA: Genera la versión corregida COMPLETA del proyecto en formato JSON.\n\n"
                    f"Recuerda: NO dejes placeholders ni código truncado. ¡Sé un ingeniero senior!"
                )
                if forbidden_patterns:
                    reflection_msg += f"\nERRORES ESPECÍFICOS A EVITAR (PROHIBIDOS):\n{forbidden_patterns}\n"
                
                # v12.0.0: Registrar la lección (Rechazo del Auditor) en la base de datos de lecciones
                try:
                    from core.lessons_learned import lessons_db
                    lessons_db.learn(
                        action=f"Generación de código para '{requirement}'",
                        context="project_build",
                        outcome="negative",
                        insight=f"Rechazado por Auditor: {forbidden_patterns or critique[:200]}",
                        source="system"
                    )
                except Exception as e:
                    logger.debug(f"[DeveloperAgent] Error guardando lección de rechazo: {e}")
                
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": reflection_msg})
                files_dict = temp_files  # Guardar como fallback
                
        if not files_dict:
            raise ValueError(f"No se pudo generar un proyecto válido tras {max_attempts} intentos. El modelo falló en entregar un JSON estructurado.")

        duration = time.time() - start_time
        logger.info(f"[DeveloperAgent] Project build completed in {duration:.2f} seconds. Generated {len(files_dict)} files.")
        
        # v11.9.0: Usar método compartido para guardar en caché
        await self._save_to_cache(files_dict, requirement, user_id, db_session, duration)

        return files_dict

    # ════════════════════════════════════════════════════════════
    #  v11.9.0: GENERACIÓN INCREMENTAL PARA PROYECTOS COMPLEJOS
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _is_complex_project(requirement: str) -> bool:
        """Detecta proyectos que necesitan subdivisión para evitar timeouts en CPU."""
        complex_indicators = [
            'juego', 'game', 'completo', 'full-stack', 'full stack', 'dashboard',
            'e-commerce', 'tienda', 'plataforma', 'sistema completo', 'app completa',
            'multiplayer', 'real-time', 'chat app', 'red social', 'clon de',
            'con ia', 'con inteligencia artificial', 'con sonido', 'con efectos',
            'con gráficos', 'con animaciones', 'con base de datos', 'con autenticación',
        ]
        req_lower = requirement.lower()
        word_count = len(requirement.split())
        indicator_count = sum(1 for kw in complex_indicators if kw in req_lower)
        return word_count > 30 or indicator_count >= 2

    async def _build_project_incremental(self, requirement: str, user_id=None, db_session=None) -> Optional[Dict[str, str]]:
        """
        Genera un proyecto complejo en 2 fases:
        1. Esqueleto: Lista de archivos con propósito y dependencias (~30s en CPU)
        2. Implementación: Cada archivo individual con contexto del esqueleto (~30s c/u)
        
        Impacto esperado vs monolítico:
        - Antes: 1 prompt gigante → 5min → TIMEOUT × 5 = 25min desperdiciados
        - Ahora:  1 esqueleto (30s) + N archivos (30s c/u) = ~5min total sin timeouts
        """
        
        # ── FASE 1: Generar esqueleto del proyecto ──
        skeleton_prompt = f"""Eres NOVA, Arquitecta de Software.
Analiza este requerimiento complejo y genera SOLO la estructura del proyecto:

"{requirement}"

Responde SOLO con JSON:
{{
  "project_name": "nombre_sin_espacios",
  "files": [
    {{
      "path": "ruta/archivo.ext",
      "purpose": "descripción breve de qué hace este archivo",
      "dependencies": ["otros archivos de los que depende"],
      "priority": 1
    }}
  ],
  "tech_stack": "tecnologías principales",
  "install_command": "comando de instalación (ej: npm install)"
}}

REGLAS:
- Máximo 10 archivos. Prioriza lo esencial.
- Incluye siempre README.md y archivos de configuración.
- NO incluyas el contenido del código, solo la estructura.
- Puerto del servidor: 3001 o 8080 (NUNCA 3000 ni 8000)."""

        logger.info("[DeveloperAgent] Fase 1/2: Generando esqueleto...")
        skeleton_response = await llm_gateway.chat(
            messages=[
                {"role": "system", "content": "Eres una API que responde exclusivamente en JSON puro."},
                {"role": "user", "content": skeleton_prompt}
            ],
            lane="batch",
            temperature=0.2,
            format="json",
            priority=1,
            model=llm_client.coder_model,
            ignore_overdrive=True,
            agent_name="developer"
        )

        skeleton = self._extract_json(skeleton_response)
        if not skeleton or not skeleton.get("files"):
            logger.warning("[DeveloperAgent] Fase 1 falló: no se obtuvo esqueleto válido")
            return None

        file_specs = skeleton["files"]
        project_name = skeleton.get("project_name", "nova_project")
        tech_stack = skeleton.get("tech_stack", "")
        logger.info(f"[DeveloperAgent] Esqueleto: {len(file_specs)} archivos planificados ({tech_stack})")

        # ── FASE 2: Implementar cada archivo individualmente ──
        files_dict = {}
        # Ordenar por prioridad (archivos de config primero)
        file_specs.sort(key=lambda f: f.get("priority", 5))

        for i, file_spec in enumerate(file_specs):
            file_path = file_spec.get("path", f"file_{i}.txt")
            purpose = file_spec.get("purpose", "")
            deps = file_spec.get("dependencies", [])

            # Construir contexto de archivos ya generados
            dep_context = ""
            for dep in deps:
                if dep in files_dict:
                    dep_context += f"\n--- {dep} ---\n{files_dict[dep][:500]}\n"

            file_prompt = f"""Eres NOVA. Estás construyendo el proyecto \"{project_name}\" ({tech_stack}).
Requerimiento original: "{requirement[:200]}"

Genera el código COMPLETO para el archivo: {file_path}
Propósito: {purpose}
{f'Contexto de dependencias ya creadas:{dep_context}' if dep_context else ''}

REGLAS:
- Código COMPLETO y FUNCIONAL. PROHIBIDO usar placeholders.
- Maneja errores con try/catch.
- Puerto del servidor: 3001 o 8080.
- Importa correctamente todas las dependencias.

Responde SOLO con JSON:
{{
  "path": "{file_path}",
  "content": "código completo del archivo"
}}"""

            logger.info(f"[DeveloperAgent] Fase 2/2: Generando {file_path} ({i+1}/{len(file_specs)})...")
            
            file_response = await llm_gateway.chat(
                messages=[
                    {"role": "system", "content": "Eres una API que responde exclusivamente en JSON puro."},
                    {"role": "user", "content": file_prompt}
                ],
                lane="batch",
                temperature=0.2,
                format="json",
                priority=1,
                model=llm_client.coder_model,
                ignore_overdrive=True,
                agent_name="developer"
            )

            parsed = self._extract_json(file_response)
            if parsed and parsed.get("content"):
                files_dict[file_path] = parsed["content"]
            else:
                logger.warning(f"[DeveloperAgent] No se pudo generar {file_path}, omitiendo")

        if not files_dict:
            return None

        # Auditoría rápida del resultado
        is_approved, critique = await auditor_agent.audit_project(files_dict, requirement, ignore_overdrive=True)
        if not is_approved:
            logger.warning(f"[DeveloperAgent] Auditor rechazó build incremental: {critique[:100]}")
            # Aun así retornamos los archivos como fallback (mejor que nada)

        return files_dict

    async def _save_to_cache(self, files_dict, requirement, user_id, db_session, duration):
        """Guarda el proyecto generado en caché para reutilización futura."""
        if not user_id or not db_session:
            return
        try:
            from core.snippet_cache import SnippetCache
            snippet_cache = SnippetCache(db_session)
            project_code = json.dumps(files_dict, indent=2)
            languages = set()
            frameworks = None
            if any('.py' in p for p in files_dict.keys()): languages.add('python')
            if any(p.endswith(('.js', '.jsx', '.mjs')) or 'package.json' in p for p in files_dict.keys()):
                languages.add('javascript')
                if any('react' in c.lower() for c in files_dict.values()): frameworks = 'react'
                elif any('vue' in c.lower() for c in files_dict.values()): frameworks = 'vue'
            if any(p.endswith(('.ts', '.tsx')) for p in files_dict.keys()): languages.add('typescript')
            snippet_cache.save(
                user_id=user_id, snippet_type='project',
                language=','.join(languages) if languages else 'mixed',
                framework=frameworks, code=project_code,
                description=f"Proyecto generado: {requirement[:100]}",
                keywords=[w.lower() for w in requirement.split() if len(w) > 3],
                context=f"duration={duration:.2f}s, files={len(files_dict)}"
            )
            logger.info("[DeveloperAgent] ✅ Proyecto guardado en caché")
        except Exception as e:
            logger.warning(f"[DeveloperAgent] Error guardando en caché: {e}")

    @staticmethod
    def _try_reuse_cached_project(requirement: str, snippets: list) -> Optional[Dict[str, str]]:
        target = requirement.lower().strip()
        for snippet in snippets:
            description = (snippet.get("description") or "").lower()
            similarity = difflib.SequenceMatcher(None, target, description).ratio()
            if similarity >= 0.90:
                try:
                    parsed = json.loads(snippet.get("code", "{}"))
                    if isinstance(parsed, dict) and parsed:
                        return parsed
                except Exception:
                    continue
        return None

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extracts and repairs JSON payload from a potentially messy or malformed string."""
        if not text:
            return None
        import re
        
        # 1. Limpieza base: Quitar tags de razonamiento y whitespace extremo
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        
        # 2. Escapar saltos de línea literales (\n y \r reales) dentro de las strings JSON
        # para evitar que json.loads falle (ya que JSON estándar prohíbe saltos de línea literales en strings)
        def escape_literal_newlines(s: str) -> str:
            in_string = False
            escaped = False
            result = []
            for char in s:
                if char == '"' and not escaped:
                    in_string = not in_string
                if char == '\\' and in_string:
                    escaped = not escaped
                else:
                    escaped = False
                    
                if char == '\n' and in_string:
                    result.append('\\n')
                elif char == '\r' and in_string:
                    result.append('\\r')
                else:
                    result.append(char)
            return "".join(result)

        text = escape_literal_newlines(text)

        # 3. Intento de parseo directo
        try:
            return json.loads(text)
        except Exception:
            pass

        # 4. Reparación de caracteres de control (El enemigo #1 de JSON.loads)
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

    @staticmethod
    def _extract_forbidden_patterns(critique: Union[str, List[str]]) -> str:
        """
        v11.9.20: Extrae patrones de error específicos de la crítica del auditor
        para generar instrucciones explícitas de "NO HACER" en el retry.
        """
        forbidden = []
        if isinstance(critique, list):
            critique_text = "\n".join(critique)
        else:
            critique_text = str(critique)
            
        critique_lower = critique_text.lower()
        
        if "require(" in critique_lower or "require" in critique_lower:
            forbidden.append("- PROHIBIDO usar require() en Python. Usa 'import' y 'os.environ' para variables de entorno.")
        if "incompleta" in critique_lower or "truncad" in critique_lower or ".inn..." in critique:
            forbidden.append("- PROHIBIDO dejar líneas incompletas o truncadas. Cada línea debe estar COMPLETA.")
        if "requirements.txt" in critique_lower:
            forbidden.append("- OBLIGATORIO incluir requirements.txt con TODAS las dependencias (flask, flask-cors, python-dotenv, etc.)")
        if "placeholder" in critique_lower or "// código" in critique_lower or "# tu" in critique_lower:
            forbidden.append("- PROHIBIDO usar placeholders. Todo el código debe ser real y funcional.")
        if "interfaz" in critique_lower or "gui" in critique_lower or "frontend" in critique_lower:
            forbidden.append("- OBLIGATORIO incluir frontend completo con HTML/CSS/JavaScript funcional.")
        if "package.json" in critique_lower:
            forbidden.append("- OBLIGATORIO incluir package.json con todas las dependencias declaradas.")
        
        return "\n".join(forbidden) if forbidden else ""

    @staticmethod
    def _is_content_truncated(content: str, filepath: str) -> bool:
        """
        v11.9.20: Detecta si el contenido de un archivo está truncado/incompleto.
        El modelo frecuentemente genera archivos que se cortan a mitad de línea.
        """
        if not content or len(content.strip()) < 10:
            return False  # Archivos muy cortos (.env, etc.) no se validan

        lines = content.strip().split('\n')
        last_line = lines[-1].strip() if lines else ""

        # 1. Línea final termina con patrón de truncamiento
        truncation_patterns = ['...', '..', 'getEle', 'inn...', 'docu', '.inner']
        if any(last_line.endswith(p) for p in truncation_patterns):
            return True

        # 2. Para HTML: verificar cierre de tags principales
        if filepath.endswith(('.html', '.htm')):
            has_html_open = '<html' in content.lower() or '<!doctype' in content.lower()
            has_html_close = '</html>' in content.lower()
            if has_html_open and not has_html_close:
                return True

        # 3. Para JS/Python: verificar balance de llaves/paréntesis
        if filepath.endswith(('.js', '.jsx', '.ts', '.py')):
            open_braces = content.count('{')
            close_braces = content.count('}')
            # Diferencia significativa = probablemente truncado
            if open_braces > 0 and (open_braces - close_braces) >= 3:
                return True

        return False

developer_agent = DeveloperAgent()
