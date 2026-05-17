# REPORTE TÉCNICO - NOVA AUTOMOUS SYSTEM v11.9.2

**Fecha:** 17 de Abril, 2026
**Módulos Afectados:** `launcher_server.py`, `backend/core/telemetry.py`, `backend/core/cache.py`, `backend/services/chat_service.py`

## Resumen Ejecutivo

La versión 11.9.2 está fuertemente orientada a estabilizar la orquestación maestra en hardware sin GPU (ambientes Windows + CPU) y erradicar falsos positivos en el monitoreo. Tras la integración oficial del `Control Center` en el puerto 9999 como punto exclusivo de arranque, se resolvieron cinco focos principales de inestabilidad y conflictos de red. Además, esta versión incluye las actualizaciones críticas v11.9.1 para el correcto reconocimiento multimodal.

---

## 🔧 Resoluciones Técnicas y Corrección de Bugs

### 1. Sistema de "Kill-Port" Previo en el Orquestador (Network Bind Fix)
**Problema:** Al hacer clic en "Iniciar Sistema", si Ollama ya estaba corriendo como servicio nativo de Windows (background ghost), el sistema colapsaba intentando atar el puerto `11434` arrojando un error fatal de red (`Only one usage of each socket address`).
**Solución:** Inyectamos una directiva de intercepción `_kill_port()` en `launcher_server.py`. Ahora, fracción de segundos antes de lanzar cualquier subproceso (`Popen`), el launcher destruye activamente con `taskkill` cualquier fantasma que ocupe de antemano el puerto solicitado. El arranque pasa a ser 100% resiliente a caídas anteriores.

### 2. Eliminación de Crash en Consolas Windows (UTF-8 Override)
**Problema:** FastAPI caía estrepitosamente en la línea 89 del arranque al intentar imprimir el símbolo de checkmark (✅) del Snippet Cache, emitiendo un `UnicodeEncodeError`. Esto sucede porque el subproceso de Windows hereda nativamente codificación cp1252.
**Solución:** Se forzó a Python a operar con codificación universal de manera independiente del SO. El launcher ahora inyecta la variable crítica `env["PYTHONIOENCODING"] = "utf-8"` en todo proceso esclavo desencadenado.

### 3. Normalización Absoluta de Directorios (`[WinError 267]`)
**Problema:** Mover el `launcher_server.py` a su propia carpeta rompió los directorios de arranque (buscaba falsamente `control_center/backend` en lugar de la raíz).
**Solución:** Implementada constante dinámica `PROJECT_ROOT = BASE_DIR.parent` que independiza la orientación del ejecutador de dónde se encuentre este guardado.

### 4. Reparación de métrica Fantasma (Cache Hit Rate)
**Problema:** El puerto 8000 (`/api/metrics/html`) estaba mostrando `45.8%` como tasa de aciertos de memoria por defecto, engañando al usuario con un número codificado duramente (hardcoded).
**Solución:** Se integró sincrónicamente `smart_cache.hit_rate` directo desde la instancia principal de memoria en `core/telemetry.py`. Ahora las mediciones reflejan en vivo cómo se ahorró CPU al evitar llamar grandes porciones de LLMs.

### 5. Bypass Asíncrono de Visión en SmartCache (Heredado de v11.9.1)
**Problema:** Si el usuario mandaba 2 imágenes en mensajes distintos sobre el mismo contexto, el sistema devolvía las respuestas pre-cacheables al no inyectar la carga fotográfica en su hash criptográfico.
**Solución:** Desacople explícito de ruta en `chat_service.py` que bypassea el Caché de por vida cuando detecta archivos adjuntos asegurando interpretación en crudo cada vez.

---

## 🚀 Resultado de Perfilado Operativo (Profiling)

Se verificó el rendimiento sobre hardware AMD Ryzen 7 5700G (24 GB RAM):

*   **Uso CPU en Reposo (Control Center Activo):** ~1%-3%
*   **RAM utilizada con 3 Clústeres Ollama Listos:** ~14.9 GB a 19.7 GB constantes
*   **Uptime y Respuesta Inicial de UVICORN:** Instantánea y tolerante a faltas.

## Documentos Oficializados

- `start_ai_system_global.bat` y afines han sido depreciados y eliminados. 
- Nuevo punto de anclaje maestro: `start_NOVA.bat`.
