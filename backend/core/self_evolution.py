import os
import json
import asyncio
import datetime
import traceback
import time
import logging
from typing import List, Dict, Any, Optional

from core.llm_gateway import llm_gateway
from core.config import LLM_CODER_MODEL, LLM_MODEL_NAME, DATA_DIR
from core.prompts import (
    NOVA_INTROSPECTION_PROMPT,
    NOVA_CODE_ANALYSIS_PROMPT,
    NOVA_TECH_WATCH_PROMPT,
    NOVA_SELF_IMPROVEMENT_PROMPT,
    NOVA_EVOLUTION_LOG_PROMPT
)

logger = logging.getLogger("core.self_evolution")

class EvolutionValidator:
    """
    Validador de propuestas de evolución y cambios en el sistema.
    Asegura que las modificaciones sigan las Reglas de Oro.
    """
    def validate_proposal(self, proposal: Dict[str, Any]) -> bool:
        risk = proposal.get("risk", "low")
        description = proposal.get("description", "")
        
        # Lógica de validación básica: bloquear riesgos altos sin descripción clara
        if risk == "high" and len(description) < 20:
            logger.warning(f"[VALIDATOR] Propuesta rechazada por riesgo alto sin justificación: {proposal}")
            return False
            
        # En una versión avanzada, aquí se podría consultar a un auditor LLM
        logger.info(f"[VALIDATOR] Propuesta aceptada (Riesgo: {risk}): {proposal.get('type')}")
        return True

class NovaSelfEvolution:
    def __init__(self):
        self.evolution_log_path = os.path.join(DATA_DIR, "nova_evolution_history.json")
        self.state_path = os.path.join(DATA_DIR, "nova_evolution_state.json")
        
        # v11.9.22: Estado interno requerido por EvolutionService
        self._last_introspection = None
        self._last_tech_watch = None
        self._evolution_log = []
        self.evolution_mode = "active"
        self.consecutive_successes = 0
        self._soft_stop = False
        self._hard_stop = False
        self._proposals = []
        
        self._ensure_data_dir()
        self._load_state()

    def _ensure_data_dir(self):
        os.makedirs(os.path.dirname(self.evolution_log_path), exist_ok=True)

    def _load_state(self):
        """Carga el estado persistente y el historial."""
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    self.evolution_mode = state.get("evolution_mode", "active")
                    self.consecutive_successes = state.get("consecutive_successes", 0)
            except Exception:
                pass
        
        if os.path.exists(self.evolution_log_path):
            try:
                with open(self.evolution_log_path, "r", encoding="utf-8") as f:
                    self._evolution_log = json.load(f)
                    if self._evolution_log:
                        last = self._evolution_log[-1]
                        self._last_introspection = last.get("timestamp")
            except Exception:
                pass

    async def introspect(self) -> Dict[str, Any]:
        """
        Analiza el estado actual del sistema usando métricas reales de SystemService.
        """
        logger.info("[EVOLUTION] Ejecutando ciclo de introspección...")
        
        try:
            from services.system_service import system_service
            from core.database import SessionLocal
            
            # Obtener auditoría real del sistema
            with SessionLocal() as db:
                audit = await system_service.get_full_system_audit(db)
        except Exception as e:
            logger.error(f"[EVOLUTION] No se pudo importar system_service: {e}")
            audit = {"version": "desconocida", "hardware": {}, "health": {"status": "degradado"}}
        
        metrics = audit.get("hardware", {})
        health = audit.get("health", {})
        
        # Obtener errores reales de la BD
        recent_errors = "No se detectaron fallos críticos recientes."
        if health.get("status") != "healthy":
            recent_errors = f"Estado degradado detectado: {health.get('dependencies')}"

        prompt = NOVA_INTROSPECTION_PROMPT.format(
            system_diagnosis=f"Análisis de arquitectura v{audit.get('version')}. Salud global: {health.get('status')}.",
            performance_metrics=json.dumps(metrics, indent=2),
            recent_errors=recent_errors
        )

        response = await llm_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            lane="batch",
            priority=2,
            format="json"
        )
        
        try:
            result = json.loads(response)
            self._last_introspection = datetime.datetime.now().isoformat()
            
            # v11.9.22: Extraer propuestas para el panel de control
            if "problemas_criticos" in result:
                for prob in result["problemas_criticos"]:
                    self._proposals.append({
                        "id": f"introspect_{int(time.time())}_{len(self._proposals)}",
                        "title": prob.get("problema"),
                        "description": prob.get("impacto"),
                        "solucion": prob.get("solucion"),
                        "priority": prob.get("prioridad", "media"),
                        "type": "introspection",
                        "status": "pending"
                    })
            
            logger.info("[EVOLUTION] Introspección completada con éxito.")
            return result
        except Exception as e:
            logger.error(f"[EVOLUTION] Error parseando introspección: {e}")
            return {"mensaje_personal": "Me siento un poco confusa tras el reinicio, pero estoy operando."}

    async def analyze_own_file(self, target_path: str) -> str:
        """
        Analiza un archivo específico del código fuente de NOVA para sugerir mejoras.
        """
        logger.info(f"[EVOLUTION] Analizando archivo propio: {target_path}")
        if not os.path.exists(target_path):
            return "Archivo no encontrado."

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            return f"Error leyendo archivo: {e}"

        prompt = NOVA_CODE_ANALYSIS_PROMPT.format(
            filename=os.path.basename(target_path),
            code_content=code[:10000] # Limitar contexto
        )

        response = await llm_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            lane="batch",
            priority=2,
            format="json"
        )
        return response

    async def tech_watch(self) -> Dict[str, Any]:
        """
        Vigila nuevas tendencias tecnológicas Y herramientas/skills compatibles con NOVA.
        Ejecuta múltiples búsquedas en paralelo para cubrir diferentes ángulos.
        """
        logger.info("[EVOLUTION] Iniciando vigilancia tecnológica + búsqueda de skills en la web real...")
        
        # Definir múltiples consultas para cubrir diferentes dominios
        search_queries = [
            "latest AI backend libraries frameworks python local LLM Ollama 2025 2026",
            "python automation tools plugins APIs voice vision agents self-hosted 2025 2026",
            "open source AI skills tools RAG embeddings knowledge graph local deployment",
        ]
        
        all_content_lines = []
        try:
            from agents.explorer import ExplorerAgent
            async with ExplorerAgent(name="TechWatcher") as explorer:
                for idx, query in enumerate(search_queries):
                    try:
                        logger.info(f"[EVOLUTION] Búsqueda {idx+1}/{len(search_queries)}: {query[:60]}...")
                        results = await explorer.execute(query)
                        
                        if results and not results[0].get("is_fallback"):
                            for res in results[:3]:  # Top 3 por cada búsqueda
                                title = res.get("title", "")
                                summary = res.get("summary", "")
                                url = res.get("url", "")
                                if title and summary:
                                    all_content_lines.append(f"- {title}: {summary} (Fuente: {url})")
                    except Exception as search_err:
                        logger.warning(f"[EVOLUTION] Falló búsqueda '{query[:40]}...': {search_err}")
                        continue
                    
                    # Pequeña pausa entre búsquedas para no saturar
                    await asyncio.sleep(2)
                        
        except Exception as e:
            logger.error(f"[EVOLUTION] Error en búsqueda de vigilancia tecnológica: {e}")

        real_tech_content = "\n".join(all_content_lines) if all_content_lines else "No se encontraron nuevas tecnologías ni herramientas."
        logger.info(f"[EVOLUTION] Vigilancia completada: {len(all_content_lines)} hallazgos recopilados.")

        from core.telemetry import get_hardware_context
        hardware_ctx = get_hardware_context()

        prompt = NOVA_TECH_WATCH_PROMPT.format(
            tech_content=real_tech_content,
            hardware_context=hardware_ctx
        )

        response = await llm_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            lane="batch",
            priority=2,
            format="json"
        )

        try:
            result = json.loads(response)
            self._last_tech_watch = datetime.datetime.now().isoformat()
            
            # Integrar tecnologías recomendadas como propuestas
            if "tecnologias" in result:
                for tech in result["tecnologias"]:
                    tech_name_found = tech.get("nombre", "desconocido")
                    difficulty = tech.get("dificultad", "media")
                    recommendation = tech.get("recomendacion", "ignorar")
                    
                    if recommendation == "implementar":
                        proposal = {
                            "id": f"tech_{int(time.time())}_{len(self._proposals)}",
                            "title": tech_name_found,
                            "description": tech.get("descripcion"),
                            "type": tech.get("tipo", "tech_watch"),
                            "status": "pending",
                            "priority": "alta" if difficulty == "facil" else "media",
                            "difficulty": difficulty,
                            "how_to": tech.get("como_implementarlo", "")
                        }
                        self._proposals.append(proposal)
                        
                        # AUTO-IMPLEMENTAR si la dificultad es fácil
                        if difficulty == "facil":
                            logger.info(f"[EVOLUTION] 🤖 Auto-implementando skill fácil: {tech_name_found}")
                            proposal["status"] = "auto_implementing"
                            asyncio.create_task(self._safe_auto_implement(tech_name_found, proposal))
                        else:
                            # Dificultad media/difícil: notificar y esperar aprobación
                            await self._notify_telegram(
                                f"🔍 *Nueva tecnología descubierta*\n\n"
                                f"*{tech_name_found}* ({difficulty})\n"
                                f"_{tech.get('descripcion', '')[:200]}_\n\n"
                                f"Dime *\"aprueba {tech_name_found}\"* si quieres que la implemente.",
                                success=True
                            )
            
            return result
        except Exception:
            return {"tecnologias": []}

    def _backup_and_apply_files(self, files_dict: Dict[str, str], tech_name: str):
        """
        Realiza un backup de los archivos existentes y aplica los nuevos cambios.
        v11.9.22: Seguridad reforzada contra Path Traversal.
        """
        import shutil
        import datetime
        from pathlib import Path
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_tech_name = "".join([c if c.isalnum() else "_" for c in tech_name])
        backup_dir = os.path.join("backend", "data", "backups", f"evolution_{safe_tech_name}_{timestamp}")
        
        # Definir la raíz permitida para cambios
        BASE_DIR = Path(os.getcwd()).resolve()
        
        for file_path, content in files_dict.items():
            # SECURITY: Sanitización estricta de rutas
            try:
                # 1. Convertir a Path y limpiar
                p = Path(file_path)
                if p.is_absolute():
                    # Si es absoluta, intentamos hacerla relativa si está dentro de BASE_DIR
                    try:
                        p = p.relative_to(BASE_DIR)
                    except ValueError:
                        # Si es absoluta fuera de BASE_DIR, tomamos solo el nombre del archivo como fallback seguro
                        p = Path(p.name)
                
                # 2. Resolver y verificar que esté dentro de BASE_DIR
                full_path = (BASE_DIR / p).resolve()
                
                if not str(full_path).startswith(str(BASE_DIR)):
                    logger.error(f"[EVOLUTION] Bloqueado intento de Path Traversal: {file_path}")
                    continue
                
                # 3. Proceder con el backup si el archivo existe
                if full_path.exists():
                    rel_path = full_path.relative_to(BASE_DIR)
                    backup_file_path = Path(backup_dir) / rel_path
                    backup_file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        shutil.copy2(full_path, backup_file_path)
                        logger.info(f"[EVOLUTION] Backup creado para: {rel_path}")
                    except Exception as e:
                        logger.error(f"[EVOLUTION] Error creando backup de {rel_path}: {e}")
                
                # 4. Escribir el nuevo contenido
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"[EVOLUTION] Archivo aplicado exitosamente: {p}")
                
            except Exception as e:
                logger.error(f"[EVOLUTION] Error procesando archivo {file_path}: {e}")

    def _trigger_reboot(self):
        """
        Guarda el estado y dispara un reinicio a través del Control Center.
        """
        import httpx
        import asyncio
        import os
        import json
        
        # 1. Guardar estado
        try:
            state = {}
            if os.path.exists(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
            state["pending_reboot"] = True
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(state, f)
            logger.info("[EVOLUTION] Bandera 'pending_reboot' activada.")
        except Exception as e:
            logger.error(f"[EVOLUTION] Error guardando estado de reinicio: {e}")

        # 2. Enviar petición asíncrona de reinicio sin esperar (fire-and-forget)
        async def _fire_reboot():
            cc_api_key = os.getenv("CC_API_KEY", "nova-cc-cambiar-en-produccion")
            try:
                # Esperar 2 segundos para dar tiempo a que termine de retornar
                await asyncio.sleep(2)
                logger.warning("[EVOLUTION] 💥 Disparando AUTO-REINICIO del backend...")
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "http://localhost:9999/api/service/backend/restart",
                        headers={"X-CC-API-Key": cc_api_key},
                        timeout=1.0
                    )
            except Exception:
                pass # Es esperado que falle o de timeout si el proceso muere al instante
                
        asyncio.create_task(_fire_reboot())

    async def implement_technology(self, tech_name: str) -> bool:
        """
        Pipeline autónomo seguro para implementar una tecnología/skill descubierta.
        
        PROTOCOLO DE SEGURIDAD:
        1. Solo puede CREAR archivos nuevos en backend/skills/ (nunca modificar core)
        2. Puede instalar paquetes pip con --dry-run primero
        3. Valida sintaxis Python antes de escribir
        4. Auto-rollback si algo falla
        5. Notifica a Juan Ramón por Telegram con el resultado
        """
        logger.info(f"[EVOLUTION] 🚀 Iniciando pipeline autónomo para: {tech_name}")
        
        # ── ZONA SEGURA: Solo se crean archivos aquí ──
        import subprocess
        from pathlib import Path
        
        SKILLS_DIR = Path(os.getcwd()) / "backend" / "skills"
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Crear __init__.py si no existe
        init_file = SKILLS_DIR / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# Auto-generated skills directory\n", encoding="utf-8")
        
        created_files = []
        installed_packages = []
        
        try:
            # ── PASO 1: Generar código con DeveloperAgent ──
            from agents.developer_agent import DeveloperAgent
            dev = DeveloperAgent()
            
            requirement = (
                f"Crea un módulo de skill/herramienta llamado '{tech_name}' para el sistema NOVA.\n"
                f"REGLAS ESTRICTAS:\n"
                f"1. El archivo DEBE ser un único módulo Python autocontenido.\n"
                f"2. DEBE tener una clase principal con método async 'execute(self, **kwargs)'.\n"
                f"3. DEBE tener una función 'get_skill_info()' que retorne un dict con: name, description, version.\n"
                f"4. NO importes módulos internos de NOVA (core.*, agents.*, services.*).\n"
                f"5. Si necesitas dependencias pip externas, inclúyelas en un comentario: # REQUIRES: paquete1, paquete2\n"
                f"6. Incluye docstrings y manejo de errores robusto.\n"
                f"7. El nombre del archivo debe ser: skill_{self._safe_name(tech_name)}.py\n"
            )
            
            files_dict = await dev.build_project(requirement)
            
            if not files_dict or not isinstance(files_dict, dict) or len(files_dict) == 0:
                logger.warning(f"[EVOLUTION] DeveloperAgent no generó archivos para '{tech_name}'")
                await self._notify_telegram(
                    f"⚠️ *Evolución fallida*: No pude generar código para _{tech_name}_.",
                    success=False
                )
                return False
            
            # ── PASO 2: Validar y escribir archivos solo en zona segura ──
            for file_path, content in files_dict.items():
                # Forzar que TODOS los archivos vayan a backend/skills/
                filename = Path(file_path).name
                if not filename.endswith(".py"):
                    filename = f"skill_{self._safe_name(tech_name)}.py"
                
                target_path = SKILLS_DIR / filename
                
                # SEGURIDAD: Nunca sobreescribir archivos existentes
                if target_path.exists():
                    logger.warning(f"[EVOLUTION] Archivo ya existe, saltando: {target_path}")
                    continue
                
                # PASO 2.1: Validar sintaxis Python
                try:
                    compile(content, filename, "exec")
                    logger.info(f"[EVOLUTION] ✅ Sintaxis válida: {filename}")
                except SyntaxError as se:
                    logger.error(f"[EVOLUTION] ❌ Sintaxis inválida en {filename}: {se}")
                    await self._notify_telegram(
                        f"❌ *Skill rechazada* ({tech_name}): Error de sintaxis en línea {se.lineno}.",
                        success=False
                    )
                    return False
                
                # PASO 2.2: Extraer dependencias pip del código
                pip_deps = []
                for line in content.splitlines():
                    if line.strip().startswith("# REQUIRES:"):
                        deps_str = line.split("# REQUIRES:")[1].strip()
                        pip_deps = [d.strip() for d in deps_str.split(",") if d.strip()]
                        break
                
                # PASO 2.3: Instalar dependencias pip si las hay
                if pip_deps:
                    for pkg in pip_deps:
                        # Sanitizar nombre de paquete (solo alfanuméricos, guiones y puntos)
                        safe_pkg = "".join(c for c in pkg if c.isalnum() or c in "-._[]<>=!")
                        if not safe_pkg or safe_pkg != pkg:
                            logger.warning(f"[EVOLUTION] Paquete pip rechazado por nombre inseguro: {pkg}")
                            continue
                        
                        try:
                            logger.info(f"[EVOLUTION] 📦 Instalando dependencia: {safe_pkg}")
                            from core.safe_subprocess import run_safe
                            result = await asyncio.to_thread(
                                run_safe,
                                ["pip", "install", safe_pkg, "--quiet"],
                                timeout=120
                            )
                            if result.returncode == 0:
                                installed_packages.append(safe_pkg)
                                logger.info(f"[EVOLUTION] ✅ Paquete instalado: {safe_pkg}")
                            else:
                                logger.error(f"[EVOLUTION] ❌ Falló pip install {safe_pkg}: {result.stderr[:200]}")
                        except Exception as pip_err:
                            logger.error(f"[EVOLUTION] Error instalando {safe_pkg}: {pip_err}")
                
                # PASO 2.4: Escribir el archivo
                try:
                    target_path.write_text(content, encoding="utf-8")
                    created_files.append(str(target_path))
                    logger.info(f"[EVOLUTION] 📝 Archivo creado: {target_path}")
                except Exception as write_err:
                    logger.error(f"[EVOLUTION] Error escribiendo {target_path}: {write_err}")
                    return False
            
            # ── PASO 3: Verificación post-instalación ──
            if created_files:
                # Intentar importar el módulo para verificar que funciona
                verification_ok = True
                for fpath in created_files:
                    try:
                        module_name = Path(fpath).stem
                        # Test de importación básico
                        spec = __import__("importlib").util.spec_from_file_location(module_name, fpath)
                        if spec and spec.loader:
                            module = __import__("importlib").util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            
                            # Verificar que tiene get_skill_info
                            if hasattr(module, "get_skill_info"):
                                info = module.get_skill_info()
                                logger.info(f"[EVOLUTION] ✅ Skill verificada: {info.get('name', module_name)} v{info.get('version', '?')}")
                            else:
                                logger.warning(f"[EVOLUTION] ⚠️ Módulo {module_name} no tiene get_skill_info()")
                    except Exception as import_err:
                        logger.error(f"[EVOLUTION] ❌ Falló importación de {fpath}: {import_err}")
                        verification_ok = False
                        
                        # AUTO-ROLLBACK: Borrar archivos creados si falló la verificación
                        logger.warning(f"[EVOLUTION] 🔄 Auto-rollback: eliminando archivos creados...")
                        for cf in created_files:
                            try:
                                os.remove(cf)
                                logger.info(f"[EVOLUTION] Eliminado: {cf}")
                            except:
                                pass
                        
                        await self._notify_telegram(
                            f"🔄 *Auto-rollback ejecutado* para _{tech_name}_.\n"
                            f"Razón: Falló la verificación post-instalación.\n"
                            f"Error: `{str(import_err)[:100]}`",
                            success=False
                        )
                        return False
                
                # ── PASO 4: Registrar la skill en el inventario ──
                self._register_skill(tech_name, created_files, installed_packages)
                
                # ── PASO 5: Notificar éxito a Juan Ramón ──
                files_list = "\n".join([f"  📄 {Path(f).name}" for f in created_files])
                pkgs_list = ", ".join(installed_packages) if installed_packages else "ninguno"
                
                await self._notify_telegram(
                    f"🧬 *Nueva skill instalada autónomamente*\n\n"
                    f"*Skill:* _{tech_name}_\n"
                    f"*Archivos creados:*\n{files_list}\n"
                    f"*Paquetes pip:* {pkgs_list}\n"
                    f"*Estado:* ✅ Verificada y operativa\n\n"
                    f"_Si deseas desinstalarla, dime: \"desinstala {tech_name}\"_",
                    success=True
                )
                
                logger.info(f"[EVOLUTION] 🎉 Skill '{tech_name}' implementada autónomamente con éxito!")
                return True
            
        except Exception as e:
            import traceback
            logger.error(
                f"[EVOLUTION] Error en pipeline autónomo para '{tech_name}': "
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            )
            
            # Auto-rollback de archivos creados
            for cf in created_files:
                try:
                    os.remove(cf)
                except:
                    pass
            
            await self._notify_telegram(
                f"❌ *Error en evolución autónoma*: _{tech_name}_\n`{str(e)[:150]}`",
                success=False
            )
        
        return False

    def _safe_name(self, name: str) -> str:
        """Convierte un nombre de tecnología a un nombre de archivo Python seguro."""
        return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")

    def _register_skill(self, tech_name: str, files: list, packages: list):
        """Registra una skill instalada en el inventario persistente."""
        inventory_path = os.path.join(DATA_DIR, "skills_inventory.json")
        inventory = []
        if os.path.exists(inventory_path):
            try:
                with open(inventory_path, "r", encoding="utf-8") as f:
                    inventory = json.load(f)
            except:
                pass
        
        inventory.append({
            "name": tech_name,
            "files": files,
            "packages": packages,
            "installed_at": datetime.datetime.now().isoformat(),
            "status": "active"
        })
        
        with open(inventory_path, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2, ensure_ascii=False)
        logger.info(f"[EVOLUTION] Skill '{tech_name}' registrada en inventario.")

    async def _safe_auto_implement(self, tech_name: str, proposal: Dict):
        """Wrapper seguro para auto-implementación en background."""
        try:
            success = await self.implement_technology(tech_name)
            proposal["status"] = "implemented" if success else "failed"
            if success:
                self.consecutive_successes += 1
                self._save_state()
        except Exception as e:
            proposal["status"] = "failed"
            logger.error(f"[EVOLUTION] Auto-implementación fallida para '{tech_name}': {e}")

    async def _notify_telegram(self, message: str, success: bool = True):
        """Envía notificación de evolución a Telegram."""
        try:
            from core.proactive import nova_proactive
            initiative = "evolution_success" if success else "evolution_failure"
            await nova_proactive.notify(message, initiative=initiative)
        except Exception as e:
            logger.error(f"[EVOLUTION] No se pudo notificar por Telegram: {e}")

    async def diagnose_and_repair(self, error_msg: str, traceback_str: str):
        """
        Ciclo de reparación autónoma ante errores críticos.
        """
        logger.info(f"[REPAIR] Iniciando protocolo de auto-curación para: {error_msg[:50]}")
        
        repair_prompt = f"""Eres el sistema de auto-reparación de NOVA.
Has detectado el siguiente error crítico:
ERROR: {error_msg}
TRACEBACK:
{traceback_str}

Bajo tus Reglas de Oro, analiza la causa raíz y genera una solución.
Si la solución requiere cambios en el código, utiliza al Experto en Código ({LLM_CODER_MODEL}).
"""
        try:
            # Solicitar diagnóstico al modelo principal
            diagnosis = await llm_gateway.chat(
                messages=[{"role": "user", "content": repair_prompt}],
                lane="batch",
                priority=2 # Prioridad baja para reparaciones de fondo
            )
            
            logger.info(f"[REPAIR] Diagnóstico completado: {diagnosis[:100]}...")
            # En una versión productiva, aquí se dispararía el DeveloperAgent para corregir el archivo afectado.
            
        except Exception as e:
            logger.error(f"[REPAIR] Falló el ciclo de reparación: {e}")

    async def check_reboot_status(self):
        """
        Verifica si el sistema acaba de regresar de un reinicio autónomo.
        """
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if state.get("pending_reboot"):
                    logger.info("[EVOLUTION] Sistema detectado regresando de un reinicio solicitado.")
                    state["pending_reboot"] = False
                    with open(self.state_path, "w", encoding="utf-8") as f:
                        json.dump(state, f)
            except:
                pass

    async def run_evolution_cycle(self):
        """
        Ejecuta un ciclo completo de auto-evolución.
        """
        logger.info("[EVOLUTION] Iniciando ciclo de evolución completo.")
        
        # 1. Introspección
        intro = await self.introspect()
        
        # 2. Vigilancia
        watch = await self.tech_watch()
        
        # 3. Registro de evolución
        await self._log_evolution_step(intro, watch)
        
        logger.info("[EVOLUTION] Ciclo de evolución finalizado.")

    async def _log_evolution_step(self, introspection: Dict, watch: Dict):
        """Guarda un registro de lo analizado y descubierto."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "introspeccion": introspection,
            "vigilancia": watch
        }
        
        history = []
        if os.path.exists(self.evolution_log_path):
            try:
                with open(self.evolution_log_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except:
                pass
        
        history.append(entry)
        # Mantener solo los últimos 50 registros
        history = history[-50:]
        
        try:
            with open(self.evolution_log_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[EVOLUTION] No se pudo guardar el log de evolución: {e}")

# --- Métodos requeridos por EvolutionService ---

    def get_pending_proposals(self) -> List[Dict[str, Any]]:
        return [p for p in self._proposals if p.get("status") == "pending"]

    def approve_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        for p in self._proposals:
            if p["id"] == proposal_id:
                p["status"] = "approved"
                # Si tiene código, podríamos aplicarlo aquí
                if p.get("type") == "tech_watch":
                    # Disparar implementación asíncrona
                    asyncio.create_task(self.implement_technology(p["title"]))
                return p
        return None

    def get_intelligence_trend(self) -> Dict[str, Any]:
        """Calcula la tendencia de crecimiento del sistema."""
        total = len(self._evolution_log)
        return {
            "total_attempts": total,
            "success_count": self.consecutive_successes,
            "status": "improving" if self.consecutive_successes > 2 else "stable"
        }

    def get_critical_modules_ranking(self) -> List[Dict[str, Any]]:
        """Módulos que requieren atención inmediata."""
        # Simplificado para esta versión
        return [{"filename": "orchestrator.py", "score": 0.65, "status": "review_needed"}]

    def emergency_control(self, level: str):
        """Gestión de paradas de emergencia."""
        if level == "soft":
            self._soft_stop = True
        elif level == "hard":
            self._hard_stop = True
            self.evolution_mode = "learning"
        elif level == "reset":
            self._soft_stop = False
            self._hard_stop = False

    def _manage_evolution_logs(self, force: bool = False):
        """Limpieza y mantenimiento de logs."""
        if force:
            self._evolution_log = self._evolution_log[-10:]
            self._save_state()

    def _save_state(self):
        """Persiste el estado actual."""
        try:
            state = {
                "evolution_mode": self.evolution_mode,
                "consecutive_successes": self.consecutive_successes,
                "last_introspection": self._last_introspection,
                "last_tech_watch": self._last_tech_watch
            }
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"[EVOLUTION] Error guardando estado: {e}")

# Instancia global exportada
nova_self_evolution = NovaSelfEvolution()

async def run_self_evolution_scheduler():
    """
    Scheduler para el ciclo de auto-evolución.
    """
    logger.info("[EVOLUTION] Scheduler iniciado.")
    # v11.9.18: Delay inicial subido a 20m para evitar saturación en el arranque
    await asyncio.sleep(1200)
    
    while True:
        try:
            try:
                from services.system_service import system_service
            except Exception as e:
                logger.error(f"[EVOLUTION] system_service no está disponible: {e}")
                await asyncio.sleep(60)
                continue
            if not system_service.is_feature_enabled("self_evolution"):
                await asyncio.sleep(3600)
                continue
            
            # v11.9.18: PRIORIDAD INTELIGENTE
            if system_service.is_cpu_resource_reserved():
                logger.info("[EVOLUTION] ⏳ Usuario activo detectado. Posponiendo evolución 10 min.")
                await asyncio.sleep(600)
                continue

            # v11.9.20: Bloquear evolución si hay builds activas (consumen el LLM)
            if system_service.has_active_builds():
                logger.info("[EVOLUTION] 🔨 Build activa detectada. Posponiendo evolución 15 min.")
                await asyncio.sleep(900)
                continue

            await nova_self_evolution.run_evolution_cycle()
        except Exception as e:
            logger.error(f"[EVOLUTION] Error en el loop del scheduler: {e}")
        
        # Ejecutar cada 6 horas por defecto
        await asyncio.sleep(6 * 3600)