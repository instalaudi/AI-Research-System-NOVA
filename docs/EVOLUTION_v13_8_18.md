# 🧬 NOVA Evolution Log — v13.8.18 "Regression Shield"

> **Fecha:** 2026-05-16  
> **Versión:** 13.8.18  
> **Estado:** DESPLEGADO Y VALIDADO  
> **Versión Anterior:** v13.8.16 "Hybrid Intelligence"

---

## 🚀 Resumen del Salto Evolutivo
Esta versión añade una **capa de auto-protección** a NOVA. Cada vez que el servidor arranca, un sistema de 9 tests automáticos verifica que todos los componentes críticos estén intactos. Esto elimina el problema recurrente de "romper funcionalidad existente al evolucionar".

Además, se corrigieron **3 bugs funcionales** descubiertos durante la auditoría profunda y se implementó un **reparador de JSON truncado** para rescatar lecciones cortadas por límites de tokens.

---

## 🏗️ 1. Arquitectura de Inteligencia Dual-Cloud (heredada de v13.8.16)
Se mantiene la jerarquía de modelos:

1. **Razonamiento Profundo:** `llama-3.3-70b-versatile` (vía Groq)
2. **Síntesis y Creatividad:** `gemini-2.0-flash` (vía Google AI Studio)
3. **Soberanía Local:** `gemma4:e4b` / `qwen2.5-coder` (vía Ollama)

---

## 🛡️ 2. Regression Guard (NUEVO)

### Archivo: `core/regression_guard.py`
Sistema de verificación automática que se ejecuta al arrancar el servidor. Usa `inspect.getsource()` y lectura directa de archivos para validar la estructura del código sin ejecutar operaciones peligrosas.

### Tests Implementados

| # | Test | Qué Protege | Método de Verificación |
|---|------|-------------|----------------------|
| 1 | **Ollama Performance Options** | Que `num_thread`, `num_ctx`, `num_predict` estén en el payload | Inspección del código fuente de `LLMClient.chat` |
| 2 | **Cloud Provider Detection** | Que modelos locales tipo "llava-llama3" no se envíen a Groq | Verifica ausencia del patrón `"llama" in model` |
| 3 | **Batch Circuit Breaker** | Que el breaker no quede comentado por debugging | Busca `_batch_breaker.can_execute()` activo |
| 4 | **JSON Parser Resilience** | Que el parseador pueda reparar JSON truncado | Ejecuta 4 casos reales: limpio, markdown, truncado, newlines |
| 5 | **Files Visible in Chat** | Que archivos adjuntos sean visibles en modo CONVERSATION | Lee `chat_service.py` buscando `files_context.*MENSAJE` en 2 rutas |
| 6 | **Distillation Confidence** | Que las destilaciones no aparezcan al 0% en el frontend | Verifica mapeo de `confianza` → `confidence_score` |
| 7 | **Environment Keys** | Que las API keys de Groq/Gemini/Ollama estén definidas | Lee variables de entorno |
| 8 | **Latency Metrics & Cache** | Que el dashboard tenga datos de latencia correctos | Verifica presencia de `latency_ms` y `_fast_cache` |
| 9 | **Ollama Connectivity** | Que el modelo local esté accesible | HTTP GET a `/api/tags` |

### Integración en el Arranque
```python
# main.py — lifespan()
await asyncio.gather(
    check_system_integrity(),
    _safe_load_whisper(),
    _safe_load_embeddings(),
    nova_voice.initialize(),
    run_regression_checks(),   # ← NUEVO v13.8.18
)
```

### Ejemplo de Salida en Logs
```
[RegressionGuard] ══════════════════════════════════════════
[RegressionGuard] 🛡️  Iniciando Verificación de Integridad
[RegressionGuard] ══════════════════════════════════════════
[RegressionGuard] ✅ Ollama Performance Options: num_thread, num_ctx, num_predict presentes
[RegressionGuard] ✅ Cloud Provider Detection: Lista explícita (sin falsos positivos)
[RegressionGuard] ✅ Batch Circuit Breaker: Activo y protegiendo
[RegressionGuard] ✅ JSON Parser Resilience: 4/4 casos superados
[RegressionGuard] ✅ Files Visible in Chat: Visibles en standard + stream
[RegressionGuard] ✅ Distillation Confidence Mapping: confianza → confidence_score OK
[RegressionGuard] ✅ Environment Keys: Groq, Google, Ollama configurados
[RegressionGuard] ✅ Latency Metrics & Cache: Activos
[RegressionGuard] ✅ Ollama Connectivity: OK (5 modelos disponibles)
[RegressionGuard] 🏆 RESULTADO: 9/9 PASS, 0 WARN — NOVA está sana.
```

---

## 🛠️ 3. Correcciones de Bugs (Auditoría v13.8.16)

### A. Reparador de JSON Truncado (`distillation.py`)
Cuando Llama 3.3 genera lecciones muy largas que superan el límite de tokens, el JSON se corta a mitad de frase. El nuevo método `_repair_truncated_json()` es capaz de:
- Cerrar bloques Markdown abiertos (` ```json ` sin cierre).
- Balancear comillas abiertas.
- Cerrar llaves `{}` y corchetes `[]` en el orden correcto.
- Limpiar texto basura al final sin destruir contenido válido.

### B. Archivos Adjuntos Invisibles (`chat_service.py`)
**Bug:** Cuando el usuario adjuntaba un archivo y escribía un mensaje corto (ej: "analiza este archivo"), el clasificador de intención lo marcaba como `CONVERSATION` y **eliminaba** el contenido del archivo del prompt.
**Fix:** Ahora `files_context` se inyecta en el prompt incluso en modo CONVERSATION, tanto en el endpoint estándar (`/query`) como en streaming (`/query/stream`).

### C. Confianza al 0% en Destilación (`distillation.py`)
**Bug:** El prompt de `distill_session` pedía el campo `"confianza"` pero el frontend esperaba `"confidence_score"`. Resultado: todas las entradas destiladas aparecían con 0%.
**Fix:** Normalización automática: busca `confianza`, `confidence`, o `score` y los mapea a `confidence_score`. Default: 0.85.

### D. Fallback Cloud-to-Local en Síntesis (`distillation.py`)
**Bug:** Si Gemini devolvía 429 (Rate Limit) durante la re-síntesis de voz de NOVA, la entrada se perdía.
**Fix:** Try/except con fallback automático a modelo local (`model=None`).

---

## 📋 Archivos Modificados en esta Versión

| Archivo | Cambios |
|---------|---------|
| `core/regression_guard.py` | **NUEVO** — Sistema de 9 tests de regresión |
| `core/distillation.py` | Reparador de JSON truncado, normalización de confianza, fallback cloud-to-local, `import re` global |
| `core/llm_client.py` | Lista explícita de modelos cloud, restauración de opciones Ollama, métricas de latencia y caché |
| `core/llm_gateway.py` | Circuit Breaker reactivado, código muerto eliminado, propagación de timeout |
| `services/chat_service.py` | Archivos adjuntos visibles en modo CONVERSATION (standard + stream) |
| `main.py` | Integración del Regression Guard en el arranque |

---

## 📋 Ficha Técnica Final
- **Versión:** 13.8.18
- **Núcleo:** Híbrido (Groq + Gemini + Ollama)
- **Embedding:** `all-MiniLM-L6-v2` (Local CPU)
- **Modo Offline:** Habilitado y Validado
- **Nivel de Autonomía:** Fase 3 (Destilación Autónoma Activa)
- **Tests de Regresión:** 9/9 PASS
- **Conocimiento Absorbido:** IDs #3155 - #3166+

---
*Documento generado por Antigravity AI durante el proceso de evolución de NOVA.*
