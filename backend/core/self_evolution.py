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
        Vigila nuevas tendencias tecnológicas compatibles con el hardware de NOVA.
        """
        logger.info("[EVOLUTION] Iniciando vigilancia tecnológica...")
        
        # En una versión avanzada, aquí se harían búsquedas web reales.
        # Por ahora, simulamos contenido de blogs técnicos recientes.
        simulated_tech_content = """
        - LangGraph: Nueva librería para orquestar agentes cíclicos.
        - Whisper-v3-Turbo: Modelo de STT ultra rápido optimizado para CPU.
        - Qwen 2.5 Coder: Modelo especializado en programación con gran rendimiento en Ollama.
        - FastEmbed: Librería ligera para embeddings sin necesidad de GPU.
        """

        from core.telemetry import get_hardware_context
        hardware_ctx = get_hardware_context()

        prompt = NOVA_TECH_WATCH_PROMPT.format(
            tech_content=simulated_tech_content,
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
                    if tech.get("recomendacion") == "implementar":
                        self._proposals.append({
                            "id": f"tech_{int(time.time())}_{len(self._proposals)}",
                            "title": tech.get("nombre"),
                            "description": tech.get("descripcion"),
                            "type": "tech_watch",
                            "status": "pending",
                            "priority": "media"
                        })
            
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
        Intenta implementar una tecnología recomendada usando el DeveloperAgent.
        Utiliza el modelo Coder especializado para esta tarea.
        """
        logger.info(f"[EVOLUTION] Intentando implementar tecnología: {tech_name}")
        
        # v11.9.22: DESACTIVADO por defecto. Requiere aprobación manual vía EvolutionService.
        ALLOW_AUTO_FILE_WRITE = False
        
        try:
            from agents.developer_agent import DeveloperAgent
            dev = DeveloperAgent()
            
            requirement = f"Implementa la tecnología o mejora '{tech_name}' en el sistema NOVA. Genera los archivos necesarios siguiendo las Reglas de Oro."
            
            # El DeveloperAgent ya está configurado para usar coder_model internamente.
            # Solo invocamos el build_project.
            files_dict = await dev.build_project(requirement)
            
            if files_dict and isinstance(files_dict, dict) and len(files_dict) > 0:
                logger.info(f"[EVOLUTION] Proyecto de mejora '{tech_name}' generado con {len(files_dict)} archivos.")
                
                if ALLOW_AUTO_FILE_WRITE:
                    logger.info("[EVOLUTION] Auto-write habilitado. Iniciando protocolo de backup y escritura...")
                    self._backup_and_apply_files(files_dict, tech_name)
                    logger.info(f"[EVOLUTION] Proyecto '{tech_name}' implementado de forma segura.")
                    
                    # Verificar si se modificaron archivos core y requiere reinicio
                    # Ignore project outputs to avoid false positive reboots
                    ignored_paths = ["data/projects", "data/project_snapshots"]
                    requires_reboot = False
                    for path in files_dict.keys():
                        if any(ignored in path for ignored in ignored_paths):
                            continue
                        if "backend" in path or ".py" in path:
                            requires_reboot = True
                            break
                    if requires_reboot:
                        self._trigger_reboot()
                else:
                    logger.warning("[EVOLUTION] Auto-write is disabled. Changes will not be applied to filesystem.")
                    
                return True
            else:
                logger.warning(f"[EVOLUTION] DeveloperAgent no generó archivos para '{tech_name}'")
        except Exception as e:
            import traceback
            logger.error(
                f"[EVOLUTION] Error en implement_technology para '{tech_name}': "
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            )
        
        return False

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