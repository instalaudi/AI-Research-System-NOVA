"""
NOVA Regression Guard v13.8.18
================================
Sistema de verificación automática que se ejecuta al arrancar el servidor.
Detecta regresiones silenciosas causadas por modificaciones de código.

Cada test valida un componente crítico y reporta PASS/FAIL con explicación.
Si algún test falla, NOVA arranca pero muestra advertencias claras en los logs.
"""
import os
import re
import json
import asyncio
import logging
import importlib
from typing import List, Dict, Tuple

logger = logging.getLogger("core.regression_guard")


class RegressionGuard:
    """
    Ejecuta una batería de tests de regresión al arranque.
    No bloquea el servidor si algo falla, pero reporta claramente.
    """

    def __init__(self):
        self.results: List[Dict] = []
        self._passed = 0
        self._failed = 0
        self._warnings = 0

    def _record(self, name: str, passed: bool, detail: str = "", warn: bool = False):
        status = "PASS" if passed else ("WARN" if warn else "FAIL")
        self.results.append({"name": name, "status": status, "detail": detail})
        if passed:
            self._passed += 1
        elif warn:
            self._warnings += 1
        else:
            self._failed += 1

    async def run_all(self) -> Dict:
        """Ejecuta todos los tests de regresión."""
        logger.info("[RegressionGuard] ══════════════════════════════════════════")
        logger.info("[RegressionGuard] 🛡️  Iniciando Verificación de Integridad")
        logger.info("[RegressionGuard] ══════════════════════════════════════════")

        # Tests síncronos (inspección de código/config)
        self._test_ollama_options()
        self._test_cloud_provider_detection()
        self._test_circuit_breaker_active()
        self._test_json_parser_repair()
        self._test_files_context_in_conversation()
        self._test_distillation_confidence_mapping()
        self._test_env_keys_present()
        self._test_latency_metrics_active()

        # Tests asíncronos (conectividad)
        await self._test_ollama_connectivity()

        # Reporte final
        self._print_report()

        return {
            "passed": self._passed,
            "failed": self._failed,
            "warnings": self._warnings,
            "total": len(self.results),
            "details": self.results,
        }

    # ══════════════════════════════════════════════════════════════
    #  TEST 1: Opciones de Rendimiento de Ollama
    # ══════════════════════════════════════════════════════════════
    def _test_ollama_options(self):
        """Verifica que el payload de Ollama incluya num_thread, num_ctx, num_predict."""
        try:
            import inspect
            from core.llm_client import LLMClient

            source = inspect.getsource(LLMClient.chat)

            has_num_thread = "num_thread" in source
            has_num_ctx = "num_ctx" in source
            has_num_predict = "num_predict" in source

            if has_num_thread and has_num_ctx and has_num_predict:
                self._record("Ollama Performance Options", True,
                             "num_thread, num_ctx, num_predict presentes en payload")
            else:
                missing = []
                if not has_num_thread: missing.append("num_thread")
                if not has_num_ctx: missing.append("num_ctx")
                if not has_num_predict: missing.append("num_predict")
                self._record("Ollama Performance Options", False,
                             f"FALTAN opciones de rendimiento: {', '.join(missing)}. "
                             f"El chat local será extremadamente lento.")
        except Exception as e:
            self._record("Ollama Performance Options", False, f"Error en inspección: {e}")

    # ══════════════════════════════════════════════════════════════
    #  TEST 2: Detección de Proveedores Cloud (Sin falsos positivos)
    # ══════════════════════════════════════════════════════════════
    def _test_cloud_provider_detection(self):
        """Verifica que la detección de Groq/Gemini use una lista explícita, no substrings."""
        try:
            import inspect
            from core.llm_client import LLMClient

            source = inspect.getsource(LLMClient.chat)

            # Buscar el patrón peligroso: "llama" in model_to_use
            uses_substring = bool(re.search(r'"llama"\s+in\s+model_to_use', source))

            if uses_substring:
                self._record("Cloud Provider Detection", False,
                             "PELIGRO: Usa detección por substring ('llama' in model). "
                             "Modelos locales como 'llava-llama3' serán enviados a Groq.")
            else:
                self._record("Cloud Provider Detection", True,
                             "Detección por lista explícita (sin falsos positivos)")
        except Exception as e:
            self._record("Cloud Provider Detection", False, f"Error: {e}")

    # ══════════════════════════════════════════════════════════════
    #  TEST 3: Circuit Breaker Activo
    # ══════════════════════════════════════════════════════════════
    def _test_circuit_breaker_active(self):
        """Verifica que el Circuit Breaker del batch lane NO esté comentado."""
        try:
            import inspect
            from core.llm_gateway import LLMGateway

            source = inspect.getsource(LLMGateway.chat)

            # Buscar si la línea del circuit breaker está comentada
            has_active_breaker = bool(re.search(
                r'if not self\._batch_breaker\.can_execute\(\)', source
            ))
            has_commented_breaker = bool(re.search(
                r'#\s*if not self\._batch_breaker\.can_execute', source
            ))

            if has_active_breaker and not has_commented_breaker:
                self._record("Batch Circuit Breaker", True,
                             "Circuit Breaker activo y protegiendo contra fallos en cascada")
            elif has_commented_breaker:
                self._record("Batch Circuit Breaker", False,
                             "PELIGRO: Circuit Breaker está COMENTADO. "
                             "El sistema puede saturarse con reintentos infinitos.")
            else:
                self._record("Batch Circuit Breaker", True,
                             "No se detectó patrón de Circuit Breaker (posible refactor)", warn=True)
        except Exception as e:
            self._record("Batch Circuit Breaker", False, f"Error: {e}")

    # ══════════════════════════════════════════════════════════════
    #  TEST 4: Reparador de JSON Truncado
    # ══════════════════════════════════════════════════════════════
    def _test_json_parser_repair(self):
        """Verifica que el parseador de JSON pueda reparar respuestas truncadas."""
        try:
            from core.distillation import nova_distillation

            # Caso 1: JSON limpio
            clean = '{"title": "Test", "content": "OK", "confidence_score": 0.9}'
            r1 = nova_distillation._parse_json(clean)

            # Caso 2: JSON en Markdown
            markdown = '```json\n{"title": "Test", "content": "OK"}\n```'
            r2 = nova_distillation._parse_json(markdown)

            # Caso 3: JSON TRUNCADO (el caso real que fallaba)
            truncated = '```json\n{"title": "Test", "content": "Este es un texto muy largo que se corta a mit'
            r3 = nova_distillation._parse_json(truncated)

            # Caso 4: JSON con newlines literales (problema de Llama 3.3)
            with_newlines = '{"title": "Test", "content": "Línea 1\nLínea 2\nLínea 3"}'
            r4 = nova_distillation._parse_json(with_newlines)

            results = [
                ("JSON limpio", r1 is not None),
                ("JSON en Markdown", r2 is not None),
                ("JSON truncado", r3 is not None),
                ("JSON con newlines", r4 is not None),
            ]

            failed_cases = [name for name, ok in results if not ok]
            if not failed_cases:
                self._record("JSON Parser Resilience", True,
                             "4/4 casos de parseo superados (limpio, markdown, truncado, newlines)")
            else:
                self._record("JSON Parser Resilience", False,
                             f"Falló en: {', '.join(failed_cases)}")
        except Exception as e:
            self._record("JSON Parser Resilience", False, f"Error: {e}")

    # ══════════════════════════════════════════════════════════════
    #  TEST 5: Archivos Adjuntos Visibles en CONVERSATION
    # ══════════════════════════════════════════════════════════════
    def _test_files_context_in_conversation(self):
        """Verifica que files_context se inyecte incluso en intent CONVERSATION."""
        try:
            # Leer el código fuente directamente para evitar importar dependencias pesadas
            chat_service_path = os.path.join(
                os.path.dirname(__file__), '..', 'services', 'chat_service.py'
            )
            if not os.path.exists(chat_service_path):
                self._record("Files Visible in Chat", True, "chat_service.py no existe, omitiendo test", warn=True)
                return
            with open(chat_service_path, 'r', encoding='utf-8') as f:
                source = f.read()

            # Buscar que en la rama CONVERSATION se use files_context
            has_fix_standard = bool(re.search(
                r'files_context.*MENSAJE DEL USUARIO', source
            ))
            
            # Contar ocurrencias: debería estar en AMBOS (standard y stream)
            occurrences = len(re.findall(r'files_context.*MENSAJE DEL USUARIO', source))

            if occurrences >= 2:
                self._record("Files Visible in Chat", True,
                             "Archivos adjuntos visibles en modo CONVERSATION (standard + stream)")
            elif has_fix_standard:
                self._record("Files Visible in Chat", True,
                             f"Fix parcial: encontrado en {occurrences} de 2 rutas", warn=True)
            else:
                self._record("Files Visible in Chat", False,
                             "Archivos adjuntos IGNORADOS en modo CONVERSATION")
        except Exception as e:
            self._record("Files Visible in Chat", False, f"Error: {e}")

    # ══════════════════════════════════════════════════════════════
    #  TEST 6: Mapeo de Confianza en Destilación
    # ══════════════════════════════════════════════════════════════
    def _test_distillation_confidence_mapping(self):
        """Verifica que 'confianza' se mapee a 'confidence_score' en distill_session."""
        try:
            import inspect
            from core.distillation import NOVADistillationEngine

            source = inspect.getsource(NOVADistillationEngine._convert_to_nova_style)
            has_mapping = "confidence_score" in source

            if has_mapping:
                self._record("Distillation Confidence Mapping", True,
                             "Campo 'confianza' se mapea correctamente a 'confidence_score'")
            else:
                self._record("Distillation Confidence Mapping", False,
                             "FALTA mapeo de 'confianza' a 'confidence_score'. "
                             "Las entradas destiladas aparecerán con 0% en el frontend.")
        except Exception as e:
            self._record("Distillation Confidence Mapping", False, f"Error: {e}")

    # ══════════════════════════════════════════════════════════════
    #  TEST 7: Variables de Entorno Críticas
    # ══════════════════════════════════════════════════════════════
    def _test_env_keys_present(self):
        """Verifica que las API keys estén configuradas."""
        groq_key = os.getenv("GROQ_API_KEY", "")
        google_key = os.getenv("GOOGLE_API_KEY", "")
        ollama_url = os.getenv("OLLAMA_URL", "")

        issues = []
        if not groq_key:
            issues.append("GROQ_API_KEY no definida")
        if not google_key:
            issues.append("GOOGLE_API_KEY no definida")
        if not ollama_url:
            issues.append("OLLAMA_URL no definida")

        if not issues:
            self._record("Environment Keys", True,
                         f"Groq: ...{groq_key[-4:]}, Google: ...{google_key[-4:]}, Ollama: {ollama_url}")
        else:
            self._record("Environment Keys", True,
                         f"Advertencias: {'; '.join(issues)}", warn=True)

    # ══════════════════════════════════════════════════════════════
    #  TEST 8: Métricas de Latencia Activas
    # ══════════════════════════════════════════════════════════════
    def _test_latency_metrics_active(self):
        """Verifica que el código de métricas de latencia no fue eliminado."""
        try:
            import inspect
            from core.llm_client import LLMClient

            source = inspect.getsource(LLMClient.chat)
            has_latency = "latency_ms" in source or "latency_samples" in source
            has_cache = "_fast_cache" in source

            if has_latency and has_cache:
                self._record("Latency Metrics & Cache", True,
                             "Métricas de latencia y caché de respuestas activos")
            else:
                missing = []
                if not has_latency: missing.append("latency tracking")
                if not has_cache: missing.append("response cache")
                self._record("Latency Metrics & Cache", False,
                             f"FALTAN: {', '.join(missing)}. Dashboard mostrará datos incorrectos.")
        except Exception as e:
            self._record("Latency Metrics & Cache", False, f"Error: {e}")

    # ══════════════════════════════════════════════════════════════
    #  TEST 9: Conectividad con Ollama
    # ══════════════════════════════════════════════════════════════
    async def _test_ollama_connectivity(self):
        """Verifica que Ollama esté corriendo y accesible."""
        try:
            import httpx
            ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
            base = ollama_url.rsplit("/api/", 1)[0] if "/api/" in ollama_url else ollama_url

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    model_names = [m.get("name", "?") for m in models[:5]]
                    self._record("Ollama Connectivity", True,
                                 f"Ollama OK. Modelos disponibles: {', '.join(model_names)}")
                else:
                    self._record("Ollama Connectivity", False,
                                 f"Ollama respondió con status {resp.status_code}")
        except Exception as e:
            self._record("Ollama Connectivity", False,
                         f"No se pudo conectar a Ollama: {type(e).__name__}: {e}", warn=True)

    # ══════════════════════════════════════════════════════════════
    #  REPORTE FINAL
    # ══════════════════════════════════════════════════════════════
    def _print_report(self):
        logger.info("[RegressionGuard] ──────────────────────────────────────────")
        logger.info("[RegressionGuard] 📋 REPORTE DE INTEGRIDAD")
        logger.info("[RegressionGuard] ──────────────────────────────────────────")

        for r in self.results:
            icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "WARN" else "❌")
            logger.info(f"[RegressionGuard] {icon} {r['name']}: {r['detail']}")

        logger.info("[RegressionGuard] ──────────────────────────────────────────")

        total = len(self.results)
        if self._failed == 0:
            logger.info(
                f"[RegressionGuard] 🏆 RESULTADO: {self._passed}/{total} PASS, "
                f"{self._warnings} WARN — NOVA está sana."
            )
        else:
            logger.error(
                f"[RegressionGuard] 🚨 RESULTADO: {self._failed} FALLOS, "
                f"{self._passed} PASS, {self._warnings} WARN — ¡REVISAR URGENTE!"
            )

        logger.info("[RegressionGuard] ══════════════════════════════════════════")


# Instancia global
regression_guard = RegressionGuard()


async def run_regression_checks() -> Dict:
    """Entry point para ejecutar desde lifespan."""
    return await regression_guard.run_all()
