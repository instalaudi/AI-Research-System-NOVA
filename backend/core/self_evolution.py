import os
import json
import asyncio
import datetime
import traceback
import time
import logging
from typing import List, Dict, Any, Optional

from core.llm_client import llm_client
from core.config import LLM_CODER_MODEL, LLM_MODEL_NAME
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
        self.evolution_log_path = os.path.join("backend", "data", "nova_evolution_history.json")
        self.state_path = os.path.join("backend", "data", "nova_evolution_state.json")
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        os.makedirs(os.path.dirname(self.evolution_log_path), exist_ok=True)

    async def introspect(self) -> Dict[str, Any]:
        """
        Analiza el estado actual del sistema, métricas y errores recientes.
        Retorna un JSON estructurado con diagnósticos y propuestas.
        """
        logger.info("[EVOLUTION] Ejecutando ciclo de introspección...")
        
        # Simular obtención de métricas (en un sistema real esto vendría de telemetría)
        metrics = {
            "cpu_usage": "Normal (Ryzen 7)",
            "ram_usage": "Estable",
            "llm_latency": "Baja (Local Ollama)",
            "uptime": "Reiniciado recientemente"
        }
        
        # Obtener errores recientes si existen (esto podría leer logs)
        recent_errors = "No se detectaron errores críticos tras el reinicio."

        prompt = NOVA_INTROSPECTION_PROMPT.format(
            system_diagnosis="Sistema operativo tras crash por sobrecalentamiento. Optimizando hilos de Ollama.",
            performance_metrics=json.dumps(metrics, indent=2),
            recent_errors=recent_errors
        )

        response = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            format="json"
        )
        
        try:
            result = json.loads(response)
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

        response = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
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

        prompt = NOVA_TECH_WATCH_PROMPT.format(tech_content=simulated_tech_content)

        response = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            format="json"
        )

        try:
            return json.loads(response)
        except Exception:
            return {"tecnologias": []}

    async def implement_technology(self, tech_name: str) -> bool:
        """
        Intenta implementar una tecnología recomendada usando el DeveloperAgent.
        Utiliza el modelo Coder especializado para esta tarea.
        """
        logger.info(f"[EVOLUTION] Intentando implementar tecnología: {tech_name}")
        
        try:
            from agents.developer_agent import DeveloperAgent
            dev = DeveloperAgent()
            
            requirement = f"Implementa la tecnología o mejora '{tech_name}' en el sistema NOVA. Genera los archivos necesarios siguiendo las Reglas de Oro."
            
            # El DeveloperAgent ya está configurado para usar coder_model internamente.
            # Solo invocamos el build_project.
            project = await dev.build_project(requirement)
            
            if project and project.get("files"):
                # Aquí normalmente se aplicarían los cambios al sistema de archivos.
                # Por seguridad, en esta fase solo logueamos la intención.
                logger.info(f"[EVOLUTION] Proyecto de mejora '{tech_name}' generado con {len(project['files'])} archivos.")
                # En un sistema completamente autónomo: self._apply_changes(project)
                return True
        except Exception as e:
            logger.error(f"[EVOLUTION] Error en implement_technology: {e}")
        
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
            diagnosis = await llm_client.chat(
                messages=[{"role": "user", "content": repair_prompt}],
                priority=2 # Prioridad alta para reparaciones
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

# Instancia global exportada
nova_self_evolution = NovaSelfEvolution()

async def run_self_evolution_scheduler():
    """
    Scheduler para el ciclo de auto-evolución.
    """
    logger.info("[EVOLUTION] Scheduler iniciado.")
    # Esperar un poco al arranque
    await asyncio.sleep(60)
    
    while True:
        try:
            await nova_self_evolution.run_evolution_cycle()
        except Exception as e:
            logger.error(f"[EVOLUTION] Error en el loop del scheduler: {e}")
        
        # Ejecutar cada 6 horas por defecto
        await asyncio.sleep(6 * 3600)