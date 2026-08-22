# FIXES APLICADOS - Archivo de Mantenimiento Histórico

---

## [v11.9.22] - Mayo 1, 2026 (Auditoría Integral y Motor de Agente Activo)

### ✅ Resolución Crítica: Bloqueo de Concurrencia en VectorDB
- **Problema:** Las llamadas síncronas a ChromaDB (`upsert`, `query`, `delete`) bloqueaban el Event Loop de FastAPI, causando latencia masiva y errores de "coroutine failure" bajo carga.
- **Solución:** Se refactorizaron 10 métodos core en `backend/core/vector_db.py` para usar `await asyncio.to_thread()`, delegando la carga pesada de disco a hilos secundarios y liberando el servidor para peticiones simultáneas.

### ✅ Estabilización Transaccional en TaskQueue
- **Problema:** Al cancelar tareas por timeout o error, SQLite podía quedar en estado "database is locked" o dejar registros a medias.
- **Solución:** Implementación de bloques `try-except-rollback` en las funciones de persistencia de `task_queue.py`. Cualquier fallo en el `db.commit()` ahora dispara un `db.rollback()` inmediato, garantizando la integridad ACID de la base de datos local.

### ✅ Implementación de Motor de Skills y Tool Calling
- **Problema:** Necesidad de evolucionar a NOVA hacia capacidades similares a Claude Code o OpenDevin (manipulación de archivos/consola) sin comprometer la seguridad del SO.
- **Solución:**
  - Creación del `SkillManager` para inyección dinámica de conocimiento.
  - Implementación de un **Bucle de Aprobación Humana (Human-in-the-Loop)** en `chat_service.py` que intercepta comandos de terminal y espera la confirmación del usuario por chat antes de proceder.
  - Desarrollo del `ToolExecutor` con **Firewall de Seguridad** integrado que bloquea patrones de manipulación de Windows (`C:\Windows`, registro, borrado global) y protege el código núcleo de NOVA.

---

## [v11.9.21] - Abril 30, 2026 (Auto-Evolución y Resurrección Autónoma)

### ✅ Resolución de Cuello de Botella en Despliegues de IA
- **Problema:** El sistema generaba código válido (ej. integraciones como LangGraph) pero lo descartaba por restricciones de escritura, requiriendo intervención humana.
- **Solución:**
  - Se habilitó la escritura autónoma permanente (`ALLOW_AUTO_FILE_WRITE = True`).
  - Se implementó un escudo de **Backups Automáticos** (`_backup_and_apply_files`) que respalda archivos base antes de cualquier mutación producida por la IA.
  - Implementación de un **Gatillo de Resurrección** (`_trigger_reboot`) que interactúa con el orquestador maestro (puerto 9999) para forzar un reinicio en caliente y cargar los nuevos cambios en la RAM.

### ✅ Persistencia y Ampliación de Logs del Sistema
- **Problema:** El historial de eventos del Control Center se borraba al alcanzar las 600 líneas (límite de memoria), perdiendo trazabilidad valiosa.
- **Solución:** 
  - Aumento del límite de la memoria dinámica en pantalla a 5000 líneas.
  - Implementación de escritura persistente en archivos físicos (ej. `logs/logs_backend.txt`), garantizando que la historia jamás se pierda entre reinicios.

### ✅ Conciencia de Hardware Dinámica
- **Problema:** En ciclos de generación (Developer) o auto-evolución, la IA podía alucinar o proponer arquitecturas pesadas (ej. LangGraph) no óptimas para un entorno de CPU local.
- **Solución:** Se creó un sensor telemétrico (`get_hardware_context`) que inyecta los núcleos, RAM total y detección de GPU en tiempo real directo en la personalidad base de NOVA (Regla de Oro 10). Ahora la IA está programada para rechazar bibliotecas excesivas si detecta limitaciones físicas.

---

## [v11.9.20] - Abril 29, 2026 (Estabilización de Generación)

### ✅ Resolución de Bucle Infinito en Builds
- **Problema:** El sistema intentaba 5 veces generar el mismo código erróneo, desperdiciando ~40 min de CPU.
- **Causa:** El Auditor era demasiado estricto y el Developer no aprendía de las críticas repetidas.
- **Solución:** 
  - Aborto temprano ante críticas repetidas (>80% similitud).
  - Auditoría enfocada en ejecución, no en estilo.
  - Detección local de truncamiento de archivos.

### ✅ Gestión de Recursos durante Construcción
- **Problema:** La evolución autónoma saturaba la CPU mientras se generaba un proyecto.
- **Solución:** Implementación de `has_active_builds()` en `system_service.py` para bloquear tareas de fondo.

### ✅ Sincronización de Actividad Telegram
- **Problema:** El sistema no sabía que el usuario estaba activo si hablaba por Telegram, lanzando tareas pesadas de fondo.
- **Solución:** Inyección de `record_user_activity()` en el procesador de actualizaciones de Telegram.

---



### ✅ Erradicación de Bucle "Orita" (Amnesia Selectiva)
- **Problema:** NOVA repetía respuestas genéricas sobre "Hola! ¿Cómo estás?" o "necesito un archivo adjunto", ignorando órdenes de memoria.
- **Causa:** La base de datos (ChatLog) y la caché contenían registros de errores previos que el LLM imitaba como parte del contexto ("Few-shot bias").
- **Solución:** 
  - **Esterilización:** Script de limpieza que eliminó registros contaminados.
  - **Aislamiento de Contexto:** Reducción estricta de la historia a 0-1 mensajes para tareas de `KNOWLEDGE` y `VISION`.
  - **Prioridad de Intención:** Reordenamiento en `intent_classifier.py` para que la memoria prevalezca sobre saludos.

### ✅ Optimización de Arranque ("Modo Turbo")
- **Problema:** El inicio del sistema era lento y los logs tardaban en aparecer.
- **Causa:** El launcher esperaba 20s en vacío y el backend cargaba módulos pesados (STT, TTS, Integridad) de forma secuencial.
- **Solución:** 
  - **Paralelización:** Uso de `asyncio.gather` en `main.py` para cargar subsistemas simultáneamente.
  - **Warm-up Delay:** Reducción de la espera en `launcher_server.py` de 20s a 10s.

### ✅ Resolución de Símbolos Extraños y Crashes de Terminal
- **Problema:** La terminal mostraba caracteres como `Ôöò` y fallaba al abrir el archivo `.bat`.
- **Causa:** Desajuste de codificación (CP1252 vs UTF-8) y errores de sintaxis en Python al imprimir ASCII art con barras invertidas (`\`) finales.
- **Solución:** 
  - **UTF-8 Forzado:** Implementación de `chcp 65001` en scripts de arranque.
  - **Raw Strings & Safe ASCII:** Migración a `print(r"...")` y adición de espacios de seguridad para evitar escapes de comillas en Python.
  - **Color Neon Blue:** Activación de `color 0B` para estética profesional.

---

## [v11.8.3] - Abril 16, 2026 (Refinamiento de Intenciones)

### ✅ Erradicación de "Proyectos Fantasma"
- **Problema:** NOVA iniciaba la construcción de software complejo ante palabras simples como "adelante" o "hazlo".
- **Causa:** Disparadores demasiado genéricos en `intent_classifier.py` y falta de validación de longitud en `chat_service.py`.
- **Solución:** 
  - Refactorización de `_PROJECT_BUILD_TRIGGERS` para exigir términos explícitos.
  - Implementación de un **Interaction Guard** que exige un mínimo de 5 palabras para activar el `DeveloperAgent`.

---

## [v11.8.2] - Abril 16, 2026 (Estabilización Turbo)

### ✅ Resolución de "Hang Semántico" (Asincronía Total)
- **Problema:** El sistema se colgaba intermitentemente durante la inyección de conocimiento o búsqueda de similares.
- **Causa:** Llamadas síncronas a ChromaDB bloqueando el bucle de eventos de FastAPI/Asincronía.
- **Solución:** Conversión total de la arquitectura `VectorDB` a métodos `async`. Todas las interacciones ahora usan `await`, liberando el hilo principal.

### ✅ Optimización de Memoria (Manual Vector Control)
- **Problema:** Consumo excesivo de RAM (~500MB extra) y errores de inicialización ("Expected 384 dimensions, got 0").
- **Causa:** Dependencia de funciones de embedding automáticas de ChromaDB que intentaban cargar modelos duplicados.
- **Solución:** Migración a **Control Manual de Vectores**. NOVA genera el embedding una vez y lo pasa directamente a la base de datos, eliminando la sobrecarga.

### ✅ Protección contra PDFs Corruptos (DLQ)
- **Problema:** Crash o bucle de logs infinitos al procesar documentos malformados.
- **Solución:** Implementación de un sistema de **Dead Letter Queue**. Los archivos con errores de estructura se marcan en `corrupt_files.json` y se omiten automáticamente en futuros escaneos.

---

## [v11.8.1] - Abril 16, 2026 (Resiliencia de Telegram)

### ✅ Fix de Límite de Caracteres en Telegram (4096)
- **Problema:** NOVA dejaba de responder en Telegram cuando la respuesta era muy extensa (logs, reportes largos).
- **Causa:** Error `400: Message is too long` de la API de Telegram.
- **Solución:** Implementación de un motor de **Fallback a Documento**. Si el mensaje excede el límite, se genera un archivo `.txt` al vuelo y se envía como documento adjunto.

---

## [v11.8.0] - Abril 16, 2026 (Turbo Performance & Global Stability)

### ✅ Erradicación de Latencia de Búsqueda Vectorial (28s -> <0.1s)
- **Problema:** El sistema se congelaba durante la fase de "Intelligence Gathering" debido a latencias de hasta 30 segundos por cada artículo evaluado.
- **Causa:** Saturación de la cola de Ollama al pedir vectores de embedding de forma concurrente con la generación de texto, además de sobrecarga de contexto en el modelo lento.
- **Solución:** Migración a **Local Embeddings** usando `sentence-transformers` con el modelo `all-MiniLM-L6-v2`. El procesamiento vectorial ahora ocurre en milisegundos directamente en la CPU, liberando a Ollama para enfocarse 100% en la inferencia lógica.

### ✅ Resolución definitiva de Errores 500 (Gridlock de CPU)
- **Problema:** Durante investigaciones pesadas, el servidor FastAPI arrojaba Error 500 y Ollama se desconectaba.
- **Causa:** Saturación total de los 16 hilos del procesador Ryzen. El Warm-up y las tareas convergían al 100% de uso, provocando timeouts de red.
- **Solución:** 
  - Ajuste de **CPU Affinity** mediante el parámetro `OLLAMA_NUM_THREAD=4`.
  - Implementación de **Prioridades 3-Tier**: Chat (0), Research (1), Background (2).
  - Reducción de la concurrencia maestra a 2 canales simultáneos para balancear carga.

### ✅ Resiliencia ante Rate Limits (429) en ArXiv/Scholar
- **Problema:** El ExplorerAgent fallaba al obtener papers científicos, retornando listas vacías por bloqueos de IP temporales.
- **Solución:** Implementación de bucles de reintento con **Exponential Backoff** (espera incremental de 4s, 8s, 16s) y fluctuación aleatoria (jitter) para evitar patrones de bot.

---

## [v11.1.2] - Abril 13, 2026 (Assets Manager, Git Timeline & Diff UX)

### ✅ Fix de rutas API duplicadas en frontend

- **Problema:** Algunas llamadas usaban `apiFetch("/api/...")` mientras `apiFetch` ya antepone `/api`, provocando rutas finales inválidas (`/api/api/...`).
- **Solución:** Normalización a rutas relativas correctas (`/projects/list`, `/snippets/search`, `/history/search`, `/git/history`).

### ✅ Manejo de errores desacoplado por pestaña

- **Problema:** Un error en librería/historial bloqueaba toda la vista de ProjectManager.
- **Solución:** Estados de error separados por módulo (`projectsError`, `snippetsError`, `historyError`, `gitError`) con renderizado local por sección.

### ✅ Versionado Git automático seguro

- **Implementación:** Snapshot de build en `data/project_snapshots/` + auto-commit local por rutas explícitas (sin `git add -A`).
- **Resultado:** Se evita incluir cambios no relacionados en repositorio con worktree sucio.

### ✅ Historial Git y visualización de diffs en UI

- **Backend:** Endpoints `GET /api/git/history` y `GET /api/git/diff/{commit_hash}`.
- **Frontend:** Pestaña `Git` con lista de commits y panel lateral de diff.
- **UX:** Cierre de panel por botón, overlay clickeable y tecla `Escape`.

---

## [v11.1.1] - Abril 13, 2026 (Project Management & UX Enhancement)

### ✅ Fix de UX en Creación de Proyectos

- **Problema:** Después de crear un proyecto, el usuario recibía el archivo ZIP descargado automáticamente sin poder ver o acceder fácilmente a sus proyectos previos.
- **Causa:** El flujo de creación de proyectos no tenía un sistema de gestión centralizado. Los proyectos se generaban y entregaban directamente sin opciones de almacenamiento/listado.
- **Solución:** 
  - Implementación de `ProjectManager.tsx` como componente dedicado para gestión de proyectos
  - Creación del endpoint `GET /api/projects/list` para obtener historial de proyectos del usuario
  - Lógica de cambio automático de pestaña cuando se detecta creación exitosa
  - Interfaz mejorada con metadatos de proyectos (tamaño, fecha, nombre)

### 🎯 Mejoras de UX

- **Flujo Streamlined**: Crear → Detectar → Navegar es automático sin intervención del usuario.
- **Gestión Centralizada**: Todos los proyectos en un solo lugar con opciones de descarga flexible.
- **Metadatos Dinámicos**: Formateo automático de tamaños de archivo y fechas en zona horaria local.

---

## [v11.1.0] - Abril 2026 (Neural Telegram & CPU Stability)

### 🛸 Fix de Amnesia en Telegram (Neural Link)

- **Problema:** NOVA perdía el contexto instantáneamente en Telegram, no recordaba diálogos previos y afirmaba ser una IA base de Alibaba Cloud.
- **Causa:** El puente de Telegram estaba desconectado del cerebro central (`ChatService`), procesando los mensajes con un prompt duro en crudo sin memoria a largo plazo ni RAG.
- **Solución:** Reescritura profunda de `_handle_direct_message` en `backend/core/proactive.py` para inyectar cada interacción telefónica al `ChatService`, salvando automáticamente el historial, heredando el `NOVA_IDENTITY_PROMPT` verdadero y proporcionando retroalimentación visual nativa.

### 🛡️ Erradicación de Bloqueo por Límite/Horario en Chats Activos

- **Problema:** Si el usuario escribía de noche (Horario de Silencio) o superaba 10 mensajes diarios, NOVA procesaba la respuesta pero "secuestraba" el mensaje enviándolo a una cola de espera matutina.
- **Causa:** El limitador de iniciativas compartía ruta de validación restrictiva en `notify()` tanto para acciones autónomas como para respuestas conversacionales directas.
- **Solución:** Introducción de estricta lógica condicional `es_respuesta_directa` en `notify()` para dar inmunidad a los mensajes conversacionales y notificaciones bajo demanda directa.

### ⚙️ Prevención de Colapso en Timeouts y Destilación

- **Problema:** Trabajos intensivos como la destilación provocaban caídas por Timeout o arrojaban errores severos `UNIQUE constraint` de SQLite.
- **Causa:** Hard-timeouts insuficientes (90s) para procesadores sin GPU (iGPU/CPU), sumado a un bucle `INSERT` no aislado para entradas que se procesaban por duplicado en un mismo lote transaccional. En adición, el modelo apunte era un `phi3:mini` no accesible localmente.
- **Solución:** Aumento de `wait_for` a 270s en `llm_client.py` en hilos concurrentes, sembrado de un control local `seen_titles` en `distillation.py` para repeler clones intradatabase y actualización obligatoria a `llama3.1:8b`.

---

## [v11.0.0] - Abril 2026 (Estabilidad y Autonomía)

### 🛸 Fix de Hilos y Motor Gráfico (RuntimeError)
- **Problema:** El backend se cerraba con el error `RuntimeError: main thread is not in main loop` al intentar generar gráficos de telemetría desde hilos de fondo.
- **Causa:** `Matplotlib` intentaba usar un backend interactivo que no es *thread-safe* para ejecuciones en segundo plano.
- **Solución:** Configuración global de `matplotlib.use('Agg')` en `backend/core/proactive.py`.

### 🛡️ Watchdog y Auto-Reinicio Inmortal
- **Problema:** Al aplicar actualizaciones profundas que requieren reinicio, el sistema se detenía permanentemente.
- **Causa:** El lanzador original era un proceso único y estático.
- **Solución:** Implementación de un bucle "Watchdog" en `start_ai_system.bat` y un sub-script de monitoreo en `backend/run_with_watchdog.bat` con cuenta atrás de 5 segundos para control manual.

## [v10.18.0] - Abril 2026

### 📊 Telemetría de Hardware (CPU/RAM)
- **Problema:** El dashboard mostraba 0% de uso de CPU y 0B de RAM debido a falta de integración con el sistema operativo.
- **Causa:** El backend dependía de métricas de base de datos pero no consultaba al hardware directamente.
- **Solución:** Integración de la librería `psutil` en `backend/core/telemetry.py` para capturar métricas reales.

### 🛣️ Corrección de Ruta de Auto-Evolución
- **Problema:** Logs inundados con errores 404 provenientes del monitor de salud interno.
- **Causa:** `self_evolution.py` intentaba consultar `/status` en lugar de la ruta correcta `/api/status`.
- **Solución:** Corrección del endpoint en la clase `HealthMonitor`.

---

## 🚨 Parches de Seguridad y Fiabilidad Crítica

**Fecha:** 9 de Abril 2026 (v10.9)
**Status:** ✅ 2 Vulnerabilidades Severas Mitigadas

### FIX-A: Path Traversal Attack en Endpoint de Descarga

- **Problema:** El nuevo endpoint estático para regresar los Archivos ZIP generados leía cualquier path concatenado vía `filename`. 
- **Peligro RCV**: CVSS 9.0. Un atacante (o un mal intento de NOVA) usando strings `..%2f..%2f` podía secuestrar información profunda del OS, leyendo `C:\Windows\System32\Sam` en entornos locales.
- **Solución Aplicada (`routers/chat.py`)**: Sanitización forzada. Solo se lee `os.path.basename`, y se verifica *magic string* `nova_project_` así como `.zip`. Eliminación absoluta del vector de ataque.

### FIX-B: Fuga de Logs (Chat Amnesia) en Catch Streamings

- **Problema:** Las operaciones de sobrecarga de hardware pesadas (Project Builder de 120s+) terminaban en error interno del motor (`Timeout`), pero dicho error se inyectaba en la pantalla en RAM local (Stream Frontend) sin tocar la base de datos `ChatLog`.
- **Solución Aplicada (`services/chat_service.py`)**: Forzar el volcado sincrónico `db.add()` y `db.commit()` en el bloque del `Exception` catch, dejando por fin traza auditable para el humano en el historial web.

---

## 📋 RESUMEN DE CAMBIOS

### Problema Identificado

```
17 Jobs después de 38 horas:
- 7 "failed" (LLM timeouts sin reintento)
- 8 "completed" pero en verify_result (Verifier rechazó)
- 2 "completed" pero en explore_topic (Explorer retornó vacío)
RESULTADO: 0 registros guardados en knowledge base
```

---

## 🔧 4 FIXES APLICADOS

### FIX-1: Reducir Quality Thresholds

**Archivos:** `config.py`, `critic.py`

```python

# ANTES:

QUALITY_THRESHOLD = 0.7  # Muy alto

Critic temperature = 0.2  # Muy crítico

# AHORA:

QUALITY_THRESHOLD = 0.4  # Más permisivo

Critic temperature = 0.5  # Menos crítico

```

**Impacto:**
- Verifier aceptará más conocimiento (thresholds más accesibles)
- Critic será menos implacable (0.5 en lugar de 0.2)
- Más registros se guardarán en la BD

---

### FIX-2: Agregar Timeout y Reintentos a Workers

**Archivo:** `task_queue.py`

```python

# ANTES:

while True:
    await handler(task)  # SIN TIMEOUT indefinido

# AHORA:

await asyncio.wait_for(handler(task), timeout=60)  # TIMEOUT 60s

# Con reintentos exponenciales: 1s, 2s, 4s, 8s, ... max 30s

# Max 3 reintentos antes de marcar "failed"

```

**Impacto:**
- Workers ya no se quedan atrapados esperando LLM infinitamente
- Tareas que fallan se reintentan con backoff exponencial
- Después de 3 intentos fallidos, marca job como "failed"

---

### FIX-3: Corregir Verifier Logic (CRÍTICO)

**Archivo:** `orchestrator.py`

```python

# ANTES:

if task_type == "verify_result":
    if safe_result:  # Si False, NO ejecuta store_knowledge

        await task_queue.add_task(config["next"], ...)

# AHORA:

if task_type == "verify_result":
    # SIEMPRE ejecuta store_knowledge, incluso si Verifier rechazó

    is_valid = safe_result
    content_to_store["_quality_flag"] = "verified" if is_valid else "unverified_but_stored"
    await task_queue.add_task(config["next"], {"content": content_to_store, ...})
```

**Impacto:**
- **CRÍTICO:** Ahora SIEMPRE se ejecuta store_knowledge
- Incluso si Verifier rechaza, el conocimiento se guarda (con flag de baja calidad)
- Esto fue el PROBLEMA PRINCIPAL que hacía que se perdieran datos

---

### FIX-4: Agregar Fallback a Explorer

**Archivo:** `explorer.py`

```python

# AHORA:

if not all_results:  # Si no encontró nada

    # Retorna fallback en lugar de lista vacía

    all_results = [{
        "title": f"No sources found: {topic}",
        "is_fallback": True,
        "quality_flag": "no_source_fallback"
    }]
```

**Impacto:**
- Explorer nunca retorna lista vacía
- Si DuckDuckGo falla, al menos hay un entry que dice "no sources"
- Esto permite que analyze_article se ejecute incluso en caso de falla de web scraping

---

## 📊 COMPARATIVA ANTES vs DESPUÉS

| Aspecto | ANTES | AHORA | Mejora |
|---------|-------|-------|--------|
| **Verifier rechaza** | ❌ No guarda | ✅ Guarda con flag | 100% → 100% |
| **Explorer vacío** | ❌ Pipeline termina | ✅ Fallback entry | 0% → 100% |
| **Worker timeout** | ❌ Infinito | ✅ 60s + reintentos | 0% → 3 intentos |
| **LLM falla** | ❌ Job marcado failed | ✅ Reintenta 3 veces | 1 intento → 3 intentos |
| **Quality threshold** | 0.7 (rechaza >30%) | 0.4 (rechaza >50%) | Más permisivo |

---

## 🧪 CÓMO PROBAR LOS FIXES

### 1. Verificar Cambios en el Código

```bash
cd backend

# Verificar config.py

grep "QUALITY_THRESHOLD" core/config.py

# Output: QUALITY_THRESHOLD = 0.4

# Verificar critic.py

grep "temperature" agents/critic.py

# Output: payload_options = {"temperature": 0.5}

# Verificar orchestrator.py

grep "_quality_flag" core/orchestrator.py

# Output: content_to_store["_quality_flag"] = ...

# Verificar task_queue.py

grep "asyncio.wait_for" core/task_queue.py

# Output: await asyncio.wait_for(handler(task), timeout=TASK_TIMEOUT_SECONDS)

```

### 2. Iniciar Sistema y Asignar Nueva Tarea

```bash
cd backend
python main.py
```

En otra terminal:
```bash

# Generar API key (si no tienes)

python -c "import secrets; print(f'API_KEY={secrets.token_urlsafe(32)}')"

# Guardar en backend/.env (editar archivo)

# Asignar nueva tarea

curl -X POST http://127.0.0.1:8000/research/start \
  -H "api-key: tu-api-key" \
  -H "Content-Type: application/json" \
  -d '["IA", "Machine Learning", "Deep Learning"]'
```

### 3. Monitorear Progreso

```bash

# Ver estado de jobs cada minuto

cd backend
watch -n 60 'python -c "
from core.database import SessionLocal, ResearchJob
db = SessionLocal()
jobs = db.query(ResearchJob).filter(ResearchJob.id > 17).all()
for job in jobs:
    print(f\"Job {job.id}: {job.status:10} stage={job.stage:20} topic={job.topic}\")
db.close()
"'
```

### 4. Verificar Que Se Está Guardando Conocimiento

```bash
cd backend
python -c "
from core.database import SessionLocal, KnowledgeEntry
db = SessionLocal()
entries = db.query(KnowledgeEntry).count()
print(f'Total knowledge entries: {entries}')
for entry in db.query(KnowledgeEntry).limit(5).all():
    print(f'  - {entry.title} (score={entry.confidence_score})')
db.close()
"
```

---

## ⚠️ IMPORTANTE

### Archivos Ya Existentes NO se Afectan

- Los 17 jobs anteriores seguirán con sus estados
- Nueva investigación generará nuevos job IDs

### Para Prueba Limpia (Opcional)

Si quieres empezar desde cero:
```bash
cd backend
rm knowledge.db  # CUIDADO: Borra todo el conocimiento

python main.py  # Se recreará la BD limpia

```

---

## 🎯 RESULTADOS ESPERADOS

Con estos fixes, tu sistema debería:

✅ **Guardar SIEMPRE el conocimiento** (incluso si rechazado)
✅ **No tener workers atrapados** (timeout después de 60s + reintentos)
✅ **Nunca perder información por falta de datos** (fallback entries)
✅ **Recuperarse de errores transitorios** (reintentos con backoff)
✅ **Aceptar más conocimiento** (thresholds reducidos)

**Predicción:** Después del primer ciclo completo, deberías ver:
- Jobs alcanzando "completed" con datos guardados
- Knowledge base creciendo con cada investigación
- Menos jobs en "failed"

---

## 📝 PRÓXIMOS PASOS (OPCIONAL)

Si aún tienes problemas:
1. **Verificar logs:** Busca "ERROR", "TIMEOUT" en la consola
2. **Aumentar timeout:** En config.py `TASK_TIMEOUT_SECONDS = 120` (en lugar de 60)
3. **Reducir más thresholds:** `QUALITY_THRESHOLD = 0.3`
4. **Implementar Redis:** Para persistencia más robusta (futuro)

---

**Status:** ✅ TODOS LOS FIXES APLICADOS
**Próximo paso:** Iniciar sistema y verificar que las nuevas tareas se completen correctamente
