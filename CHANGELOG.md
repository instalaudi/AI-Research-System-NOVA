# Changelog (NOVA AI System)

Todas las actualizaciones y parches importantes aplicados a la arquitectura base se documentarán en este archivo.

## [v12.0.0] - Agentic Skills & Deep Persistence (Mayo 6, 2026)

Esta actualización mayor integra capacidades agenticas avanzadas extraídas del repositorio `master-skills-main`, elevando el nivel de autonomía, memoria y calidad de recuperación de conocimiento (RAG) de NOVA.

### 🧠 Memoria Muscular (AgentMemory)
- **Sistema de Lecciones Aprendidas:** Implementado `core/lessons_learned.py` usando SQLite FTS5. Ahora NOVA es capaz de aprender de sus propios errores.
- **Auto-Corrección Activa:** El `DeveloperAgent` inyecta automáticamente advertencias y correcciones pasadas en su prompt de desarrollo si el `AuditorAgent` rechazó una construcción previa. Esto previene que el LLM cometa exactamente el mismo error en múltiples intentos.

### 📚 Semantic Chunking (RAG Optimization)
- **Segmentación Consciente:** El `Librarian` abandonó el viejo método de división arbitraria por caracteres. Ahora utiliza el `ChunkingOptimizer` para segmentar documentos respetando los límites lógicos, encabezados Markdown y saltos de párrafo, mejorando exponencialmente la calidad semántica en ChromaDB.

### 🛡️ Estabilidad del Enjambre
- **Handoff Protocol:** Implementado el protocolo formal de transferencia de contexto `_build_handoff` en el Orquestador, asegurando que ninguna instrucción técnica se pierda cuando una tarea pasa entre agentes del Swarm.
- **Anti-Drift Limits (ADL):** Inyectados guardarraíles VFM (Value-First Modification) en el prompt de Auto-Evolución. NOVA ahora priorizará la "Estabilidad Estructural" por encima de añadir librerías sin beneficio diario comprobable.

## [v11.9.22] - Active Agentic Skills & Tool Calling (Mayo 1, 2026)

Esta actualización transforma a NOVA de un sistema reactivo a un **Agente Activo con Capacidad de Acción**, permitiendo la manipulación segura del entorno local y la carga modular de conocimiento experto.

### 🧠 Motor de Skills (Skill Manager)
- **Carga Modular de Contexto:** Implementado `backend/core/skill_manager.py` que permite inyectar instrucciones específicas (Skills) al prompt del sistema bajo demanda. Esto reduce el consumo de tokens y previene la saturación de instrucciones en el prompt global.
- **Carpeta de Habilidades:** Se creó `backend/skills/` para almacenar manuales de instrucciones en Markdown.
- **Skill de Terminal Habilitada:** Implementada la `terminal_skill.md` que dota a NOVA de la consciencia necesaria para proponer comandos de sistema estructurados en JSON.

### 🛠️ Interacción de Sistema (Tool Calling & Loop)
- **Bucle de Acción Humana (Human-in-the-Loop):** Refactorizado `chat_service.py` para interceptar peticiones de herramientas. NOVA ahora puede proponer un comando de terminal, el cual queda en "pausa" hasta que el usuario lo apruebe o rechace explícitamente en el chat.
- **Manejo de Observaciones:** Una vez aprobado, el sistema ejecuta el comando, captura el `stdout/stderr` y se lo re-inyecta a NOVA de forma invisible para que continúe la conversación con datos reales del PC.

### 🛡️ Seguridad y Blindaje (Sandboxing)
- **Firewall de Ejecución:** Implementado `backend/core/tool_executor.py` con una lista negra de patrones destructivos. NOVA tiene prohibido tocar `C:\Windows`, modificar el registro o borrar sus propios archivos núcleo (`Self-Preservation Guard`).
- **Concurrencia de ChromaDB:** Corregido el bloqueo crítico del Event Loop envolviendo todas las llamadas a ChromaDB con `asyncio.to_thread`.
- **Integridad ACID en SQLite:** Se protegieron todas las transacciones de `TaskQueue` con bloques `try-except-rollback` para evitar corrupciones de base de datos ante cancelaciones abruptas.


## [v11.9.21] - Autonomous Self-Evolution & Backups (Abril 30, 2026)

Esta actualización dota a NOVA de la capacidad de auto-modificar su núcleo de forma segura, permitiendo despliegues automáticos con respaldo de seguridad y reinicios autónomos.

### 🧠 Auto-Evolución Autónoma
- **Escritura Autónoma Habilitada:** Se removió el candado de seguridad (`ALLOW_AUTO_FILE_WRITE = True`). Ahora NOVA aplica las mejoras de arquitectura generadas durante su ciclo de vigilancia directamente al sistema.
- **Protocolo de Backups Inquebrantable:** El sistema ahora realiza una copia de seguridad (`data/backups/evolution_<tecnologia>_<timestamp>/`) del archivo original antes de sobrescribirlo, garantizando la reversibilidad ante fallos generados por la IA.
- **Auto-Resurrección (Gatillo de Reinicio):** Implementado el método `_trigger_reboot()` que utiliza el Control Center (`launcher_server.py`) para reiniciar el proceso backend en caliente tras modificar el núcleo, aplicando el código nuevo en la memoria RAM en ~2 segundos.

### 📜 Trazabilidad Extendida (Control Center)
- **Persistencia de Logs en Disco:** Los registros de la consola para cada subsistema (backend, frontend, ollama) ahora se guardan de forma permanente en archivos de texto en la carpeta `logs/` (ej. `logs_backend.txt`).
- **Ampliación de Historial Web:** Se aumentó el límite de memoria del buffer en vivo (`deque`) de 600 a 5000 líneas, proveyendo un historial 10 veces más largo en la interfaz web sin fugas de RAM.

### ⚙️ Autoconciencia de Hardware (Hardware Awareness)
- **Detección Dinámica (`telemetry.py`):** Implementada la función `get_hardware_context()` que lee en tiempo real el uso de CPU (núcleos físicos), RAM total y detecta automáticamente si el sistema posee una GPU dedicada (NVIDIA/AMD) o gráficos integrados (iGPU) usando `wmic`/`psutil`.
- **Inyección en Agentes (`DeveloperAgent`):** Se inyectó la *Regla de Oro 10*, instruyendo a NOVA a prohibir el uso de frameworks pesados (ej. LangGraph, Kafka, PyTorch) si detecta que no posee hardware masivo, forzando soluciones ultraligeras y bare-metal en Python.
- **Filtro de Evolución (`self_evolution.py`):** El ciclo de vigilancia tecnológica ahora está "consciente" de su cuerpo y descarta tecnologías incompatibles con su lectura de hardware en tiempo real.

---

## [v11.9.20] - Generation Pipeline Stabilization (Abril 29, 2026)

Esta actualización resuelve el bucle de fallos en la generación de proyectos, optimiza el uso de recursos durante builds y mejora la integración con Telegram.

### 🏗️ Developer & Auditor Pipeline
- **Detección de Errores Repetidos:** El `DeveloperAgent` ahora aborta tras 2 intentos con críticas idénticas (>80% similitud), ahorrando ~30 min de CPU inútil.
- **Auditoría Pragmática:** Reescritura del prompt del Auditor para priorizar la funcionalidad sobre la estética. Ya no se rechazan proyectos por warnings menores (F401) o sugerencias de estilo.
- **Detección de Truncamiento:** Nuevo sistema de pre-validación que detecta archivos cortados (ej. HTML incompleto) antes de llamar al Auditor, reintentando instantáneamente con feedback correctivo.

### 🚦 Resource & Task Management
- **Smart Build Threshold:** El `HealthMonitor` ahora otorga 35 minutos a las tareas de construcción (antes 15 min), evitando re-encolados prematuros en builds pesadas sobre CPU.
- **Build-Aware Evolution:** El ciclo de auto-evolución ahora detecta builds activas y se pospone automáticamente para no competir por el LLM.
- **Telegram Activity Tracking:** Las interacciones vía Telegram ahora registran actividad del usuario, permitiendo que el sistema de "Prioridad Inteligente" pause tareas de fondo correctamente.

---



Esta actualización implementa el 100% de las resoluciones derivadas de la auditoría profunda de seguridad, arquitectura y rendimiento.

### 🛡️ Security Hardening (Fase 1)

- **Control Center Auth (C-2):** El panel de control (`launcher_server.py`) ahora está protegido por `X-CC-API-Key` y bloqueado a `127.0.0.1` con CORS estricto.
- **Rotación de Credenciales (C-1):** Generación de nuevo `JWT_SECRET_KEY` y limpieza de variables de entorno expuestas (`CORS_ORIGINS=*`).
- **Config Whitelist (M-1):** Protección contra inyección de variables de entorno arbitrarias en el endpoint de configuración.

### 🧠 Graph & Memory Optimization (Fase 2)

- **ChromaDB Orphan Cleanup (M-4):** Sincronización automática de bases vectoriales con SQLite, eliminando documentos fantasmas tras podas de grafos en batches de 100.
- **Matplotlib Lazy-Loading (M-5):** Ahorro de ~100MB de RAM en el backend importando la librería de gráficos de manera diferida y en hilos asíncronos (`asyncio.to_thread`).
- **PromptGuard Hardened (M-8):** Arquitectura de 5 capas de defensa contra prompt injection, homoglifos Unicode, y contexto RAG envenenado.

### ⚙️ Concurrency & Resilience (Fase 3)

- **Ollama Warm-up Loop (M-9):** Sistema de reintentos resiliente que evita cold-starts fatales en la inicialización del motor local.
- **Error Sanitization (M-2):** Los registros del `DeveloperAgent` truncan trazas y enmascaran rutas absolutas antes de guardarlas en el `ChatLog`.
- **SQLite Batching (M-6, m-6):** Agrupación de operaciones transaccionales en un solo `commit` y delegación a hilos separados (`to_thread`) para liberar el event loop asíncrono.
- **Anti-Mutation Guard (M-7):** Bloqueo explícito (`ALLOW_AUTO_FILE_WRITE = False`) al agente de auto-evolución para prevenir daños al núcleo del sistema.

### 🎙️ STT Upgrade

- **Whisper v3-Turbo:** Upgrade del modelo de reconocimiento de voz de `base` a `turbo` (large-v3-turbo). Precisión cercana a large-v3 con velocidad optimizada para CPU. Configurable vía `WHISPER_MODEL` en `.env`.

### 🚀 Performance (Arranque & RAG)

- **Embeddings Eager-Load:** El modelo de embeddings (`all-MiniLM-L6-v2`) ahora se pre-carga al arranque en paralelo con Whisper y TTS, eliminando ~13s de latencia en la primera query RAG del usuario.
- **HuggingFace Offline Mode:** Se desactivan las verificaciones HTTP a HuggingFace Hub (`HF_HUB_OFFLINE=1`) al cargar el modelo de embeddings, eliminando ~20 requests HEAD innecesarias ya que el modelo está en caché local.
- **Ollama Model Picker:** Nueva funcionalidad en el Control Center que lista los modelos instalados localmente. Permite seleccionar modelos (Fast, Main, Coder) desde un desplegable, eliminando errores tipográficos al configurar el sistema.
- **PromptGuard Expanded:** Añadidos sinónimos (`órdenes`, `directivas`, `limitaciones`, `mandatos`) y verbos (`sáltate`, `omite`) al regex de detección de inyección, cerrando un bypass descubierto en testing en vivo.
- **Identidad Social Suavizada:** NOVA ya no rechaza cortesías del usuario. Responde brevemente a saludos y pasa al tema, en lugar de negarse a participar.

---

## [v11.9.15] - Stabilization, Optimization & Premium UI (Abril 17, 2026)

### 🧠 Estabilización Cognitiva y Memoria
- **Esterilización de Bucle "Orita"**: Limpieza profunda de la base de datos para eliminar contaminaciones de contexto y respuestas genéricas repetitivas.
- **Identidad Blindada (Regla #1)**: Refuerzo estricto del prompt de identidad (Social y Estándar) para prohibir saludos y formalismos innecesarios.
- **Confirmación Visual de Aprendizaje**: Implementación de confirmaciones explícitas `[!TIP]` al final de las respuestas cuando NOVA almacena información en memoria.
- **Prioridad de Intención**: Reestructuración del clasificador para que las órdenes de aprendizaje tengan precedencia sobre las de conversación casual.

### 🚀 Optimización de Arranque ("Modo Turbo")
- **Lifespan Paralelo**: El backend ahora carga el escaneo de integridad, el modelo de oído (Whisper) y la voz de NOVA simultáneamente, reduciendo el retardo de inicio percibido.
- **Launcher Ágil**: Reducción del retardo de pre-calentamiento (warm-up) de 20s a 10s en el Control Center.

### 💎 Interfaz de Terminal Premium v2
- **Temática Tech-Blue**: Implementación de color de consola `0B` (Cian Neón) para una estética de investigación de vanguardia.
- **Blindaje de Caracteres (UTF-8)**: Forza el uso de `chcp 65001` en Windows para eliminar símbolos extraños y asegurar que el arte ASCII se vea perfecto.
- **ASCII Art Robusto**: Nuevo logo de NOVA v11.9.15 utilizando cadenas "raw" en Python para evitar errores de sintaxis y cierres inesperados de terminal.

---

## [v11.9.2] - Control Center Master Orchestration & Hardware Guard (Abril 17, 2026)

### 🎛️ Control Center Unificado (Puerto 9999)

- **Rutas Absolutas Anti-Crash**: Se corrigió el error `[WinError 267]` dentro del `launcher_server.py`. Ahora el orquestador resuelve inteligentemente el `PROJECT_ROOT`, permitiendo levantar servidores independientemente de desde dónde se ejecute el script.
- **Limpieza de Puertos Dinámica**: Para evitar choques de `Address already in use`, incorporamos `_kill_port()` en el ciclo de arranque. Ahora NOVA destruye agresivamente cualquier servicio zombi (puertos 11434, 11435, 11436) antes de intentar reiniciar Ollama.
- **Python Unicode Override**: Inyección de `PYTHONIOENCODING=utf-8` en el entorno virtual de arranque para prevenir colapsos (`UnicodeEncodeError`) en la consola de Windows al intentar imprimir caracteres especiales (✅, ⚠️).
- **Master Script Único**: Eliminación de scripts heredados obsoletos (`start_ai_system*.bat`, `start.sh`) y reemplazo oficial por el único `start_NOVA.bat` guiado por el motor del Control Center.
- **Silencio de Buffering de Python**: Refactorización del `subprocess.Popen` para usar el modo de Texto Activo (`text=True`), eliminando el molesto `RuntimeWarning` de `bufsize=1` en binario.

### 🧠 Sincronización Biométrica (Metrics Dashboard)

- **Real-Time Smart Cache**: La métrica de `Cache Hit Rate` en `/api/metrics/html` (puerto 8000) ya no muestra un valor "hardcoded" de 45.8%. Ahora el puente telemétrico consulta en tiempo real a `smart_cache.hit_rate` para mostrar el verdadero porcentaje de memoria muscular a corto plazo ahorrado.

### 🖼️ Soporte Multimodal Total (V11.9.1 Vision Override)

- **Caché Hashing Inteligente**: Tras descubrir que el sistema devolvía aciertos de caché rotos para imágenes ignorándolas, el generador criptográfico (`_generate_key`) asimila ahora los parámetros adjuntos en el hash maestro.
- **Vision Gateway Bypass**: Se parcheó `chat_service.py` para obligar al servidor a eludir cualquier memoria temporal cuando el usuario adjunta fotografías o PDFs visuales garantizando que los ojos de NOVA jamás usen la "memoria" para leer un dato fresco.

## [v11.8.3] - Intent Refinement & Interaction Guard (Abril 16, 2026)

### 🛡️ Prevención de "Proyectos Fantasma"

- **Filtro de Intenciones Hardened**: Limpieza profunda de los disparadores de `PROJECT_BUILD`. Palabras como "adelante", "hazlo" o "procede" ya no activan el motor de construcción por accidente.
- **Validación de Requerimientos**: Implementado umbral de seguridad de **5 palabras** para órdenes de desarrollo. Si la orden es ambigua o corta, NOVA solicita aclaración en modo conversacional.

## [v11.8.2] - Estabilización y Refinamiento Turbo (Abril 16, 2026)

### ⚡ Arquitectura Vectorial Asíncrona (Manual Control)

- **Zero-Block VectorDB**: Todas las operaciones vectoriales (búsqueda, indexación, borrado) han sido migradas a `async/await`. Se eliminaron los retardos en la interfaz de usuario causados por operaciones de E/S síncronas.
- **Manual Vector Injection**: Desacoplamiento total de las funciones de embedding internas de ChromaDB, permitiendo un ahorro de **~500MB de RAM** y evitando errores de configuración en tiempo de ejecución.

### 📊 Optimización de Monitoreo

- **Caché de Dashboard**: Implementada caché de **30 segundos** para el `SystemService`, reduciendo el estrés en la base de datos durante el monitoreo continuo desde el panel de administración.

### 💀 Dead Letter Queue (Gestión de Corrupción)

- **Blacklist de Archivos**: Sistema de detección de corrupción en PDFs que marca archivos malformados en `corrupt_files.json`, evitando bucles infinitos de error en el motor `Librarian`.

## [v11.8.1] - Neural Telegram Resilience (Abril 16, 2026)

### 🛸 Gestión de Mensajes Largos

- **Auto-Truncamiento e Inmortalidad**: Sistema inteligente que detecta respuestas de NOVA superiores a 4096 caracteres.
- **Fallback a Documento**: Si el mensaje excede el límite de Telegram, NOVA genera automáticamente un archivo `.txt` y lo envía como documento, garantizando que ninguna respuesta se pierda.

---

## [v11.8.0] - Turbo Performance & Local Memory (Abril 16, 2026)

### 🏎️ Optimización Masiva de Latencia

- **Local Embeddings (Aceleración 500x)**: Migración total de la generación de vectores de Ollama a la librería local `sentence-transformers`. Las búsquedas pasaron de **28,000ms a <100ms**, eliminando el "gridlock" de memoria en CPU.
- **Modelo Bibliotecario Local**: Integración del modelo `all-MiniLM-L6-v2` cargado en RAM de forma perezosa (lazy loading).

### 🚦 Arquitectura de Prioridades 3-Tier

Rediseño del orquestador para permitir multitarea real sin bloqueos:
- **Prioridad 0 (Instantánea)**: Chat y comandos del usuario.
- **Prioridad 1 (Preferente)**: Investigación activa (Planner, Explorer).
- **Prioridad 2 (Background)**: Destilación, Evolución y Thinker. Ceden el paso automáticamente ante carga pesada.
- **Concurrencia Dual**: Habilitación de 2 canales de IA simultáneos (`LLM_CONCURRENCY=2`), permitiendo investigar mientras se chatea.

### 🛡️ Estabilidad y Resiliencia Extrema

- **CPU Relief (Ryzen 7 Tuning)**: Ajuste de `OLLAMA_NUM_THREAD=4` para garantizar que el sistema operativo tenga recursos para carga de modelos durante tareas pesadas.
- **API Resilience**: Implementación de reintentos con espera exponencial (backoff) para ArXiv y Semantic Scholar, resolviendo errores `429` por exceso de velocidad.
- **Warm-up Cleanup**: Eliminación de verificaciones de manifiesto obsoletas en el arranque de Ollama.

---

## [v11.6.0] - El Auditor Híbrido & Protección CPU (Abril 15, 2026)

### 🛡️ Auditoría Híbrida (Ruff + IA)

- **Escudo Estático (Ruff)**: Integración de Ruff para validación técnica instantánea (<20ms).
- **Rechazo Ultra-Rápido**: El sistema detecta y rechaza errores de sintaxis (`invalid-syntax`) antes de activar el LLM, ahorrando ciclos de CPU y tiempo.
- **Contexto Técnico**: El Auditor de IA ahora recibe el reporte de Ruff para enfocarse exclusivamente en la lógica y arquitectura, ignorando fallos menores ya detectados.

### 🚀 Prioridad Humana Absoluta (v11.5.0)

- **Cerebro Unificado**: Eliminación de semáforos paralelos. NOVA ahora procesa una sola tarea de IA a la vez para evitar el "Gridlock" en procesadores Ryzen.
- **Master Priority Semaphore**: Implementación de cola única donde el Chat tiene precedencia absoluta sobre el fondo.
- **Pausa Global de Fondo**: Cualquier actividad del usuario (Chat/Dev) induce una pausa automática de 8s en todos los agentes de investigación y bibliotecario.
- **Modo Serial Estricto**: Concurrencia fijada en 1 para hardware basado en CPU, garantizando latencias mínimas y fluidez total.

### 🛠️ Robustez y Compatibilidad Windows

- **Fix de Codificación (Charmap)**: Eliminación de emojis en logs críticos para garantizar compatibilidad con terminales Windows sin soporte UTF-8 nativo.

---

## [v11.4.4] - Silent Resilience & Metrics Sync (Abril 15, 2026)

### 📊 Dashboard & Métricas Globales (v11.4.3)

- **Sincronización de Calidad**: El indicador de "Capacidad Total" ahora refleja la salud de los **2,448 artículos** globales, eliminando la discrepancia visual con el promedio de confianza.
- **Backend Quality Engine**: Nuevo cálculo en el servidor para el ratio de conocimiento de alta calidad (>55%).

### 🛡️ Resiliencia Silenciosa (Telegram)

- **Detector de Timeouts Inteligente**: NOVA ahora reconoce los `ReadTimeout` de red como eventos normales. Ya no se envían alertas de emergencia por retrasos temporales de conexión.
- **Refactorización de Excepciones**: El radar de red ahora analiza la clase técnica de la excepción, garantizando una clasificación precisa de fallos de integridad vs. micro-cortes de internet.

## [v11.4.2] - The Integrity & Swarm Update (Abril 15, 2026)

### 🛡️ Sistema de Integridad y Antiduplicados (NUEVO)

- **Huella Digital SHA-256**: Implementado sistema de hashing para identificar el contenido de los libros. NOVA ahora ignora automáticamente archivos duplicados aunque tengan nombres distintos.
- **Detección por Título**: Verificación cruzada contra la base de datos para evitar re-procesar el mismo archivo.
- **Alertas Inteligentes**: Interfaz de usuario con código de colores (Verde: Éxito, Ámbar: Duplicado, Rojo: Error).
- **Migración Automática**: Incluido script de actualización `migrate_v11_4_2.py` para sincronizar bases de datos existentes con el nuevo esquema.

### 🚀 Arquitectura Multi-Runtime (Desacoplamiento Total)

- **Eliminación del Singleton LLM**: El motor de inferencia ya no es un cuello de botella único. Ahora cada agente instancia su propio cliente configurado.
- **LLMRouter Centralizado**: Implementado cerebro de tráfico que redirige peticiones por agente:
    - **Chat/General**: Puerto 11434 (`qwen3:8b`).
    - **Developer**: Puerto 11435 (`qwen2.5-coder:7b`).
    - **Audit/Visión**: Puerto 11436 (`llava-llama3`).
- **Autodetección de Visión**: El Router detecta imágenes automáticamente y redirige la tarea al motor multimodal sin intervención del usuario.
- **Pausa Dinámica de Destilería**: El sistema detecta cuando el usuario está en una sesión de alta prioridad (Chat/Dev) y pausa los motores de fondo para liberar CPU.

### 📚 El Súper-Bibliotecario (Ingesta Masiva)

- **Batch Ingestion**: Optimización de carga de PDFs mediante procesamiento por lotes (25 fragmentos por lote).
- **Subida Múltiple Habilitada**: Interfaz corregida con atributo `multiple` para seleccionar colecciones enteras de una sola vez.
- **Sequential Queue**: Procesamiento ordenado para proteger los 24GB de RAM y la CPU Ryzen 7.

### 🛠️ Estabilidad y Telemetría

- **Async Telemetry v2**: Migración total de monitoreo a `httpx` asíncrono para evitar que el Panel de Admin bloquee la generación de código.
- **Arranque Automatizado**: Nuevo `start_ai_system.bat` que gestiona la limpieza de puertos (8000, 3000, 11434-11436) y el arranque secuencial de motores con warm-up de 20s.
- **CPU Tuning**: Reducción de contexto a 2048 tokens y aumento de timeouts a 600s para garantizar estabilidad en hardware local sin GPU.

---

### 🚀 Gestión avanzada de activos y versionado local

- **Snippet Cache UI**: `ProjectManager.tsx` ahora incluye pestaña **Librería** conectada a `GET /api/snippets/search`.
- **Historial Semántico**: Nueva pestaña **Historial** conectada a `GET /api/history/search` para recuperar código por similitud semántica.
- **Versionado Git automático**: Integrado flujo seguro de snapshots en `data/project_snapshots/` + auto-commit local por rutas explícitas.
- **Historial Git visible**: Nuevo endpoint `GET /api/git/history` y pestaña **Git** en frontend.
- **Inspección de cambios**: Nuevo endpoint `GET /api/git/diff/{commit_hash}` + drawer de diff en UI.
- **UX mejorada del drawer**: Cierre por overlay, botón y tecla `Escape`.

### 🛠️ Correcciones de estabilidad

- **Fix de rutas API frontend**: Corrección de llamadas `apiFetch("/api/...")` a rutas relativas correctas (`/projects/list`, `/snippets/search`, `/history/search`).
- **Manejo de errores por sección en ProjectManager**: Errores desacoplados por pestaña (`projects/snippets/history/git`) para evitar bloqueo global de la vista.
- **Validación de respuestas HTTP**: Se añadió verificación `response.ok` antes de parsear JSON en llamadas críticas.
- **Compatibilidad endpoint similares**: Se mantiene `POST /snippets/similar` y se añade `GET /snippets/similar?code=...`.

---

## [v11.1.1] - Project Manager & Auto-Tab Switching (Abril 13, 2026)

### 🚀 Sistema de Gestión de Proyectos Generados

- **Nuevo Componente Frontend**: Implementado `ProjectManager.tsx` con interfaz moderna para listar y descargar proyectos generados.
- **Cambio Automático de Pestaña**: El frontend ahora detecta automáticamente cuando un proyecto ha sido creado exitosamente y cambia de pestaña para mostrar la lista de proyectos generados.
- **Endpoint de Proyectos**: Nuevo endpoint `GET /api/projects/list` que lista todos los proyectos ZIP asociados al usuario con metadatos (tamaño, fecha de creación).
- **Flujo Mejorado**: Ya no es necesario descargar automáticamente después de crear un proyecto. Ahora el usuario puede ver todos sus proyectos en una interfaz centralizada y descargar según sea necesario.
- **Metadatos de Proyectos**: Cada proyecto muestra nombre, tamaño en formato legible, fecha de creación y opción de descarga directa.

### 📝 Cambios Específicos

- **`frontend/src/components/ProjectManager.tsx`**: Nuevo componente con grid responsive, manejo de errores y cargas asincrónicas.
- **`frontend/src/app/page.tsx`**: Lógica de detección automática de creación de proyectos en el stream de respuesta.
- **`backend/routers/chat.py`**: Nuevo endpoint `/projects/list` (línea 197).
- **`backend/services/chat_service.py`**: Mensaje actualizado que guía al usuario a la pestaña de Proyectos en lugar de descargar automáticamente.

---

## [v11.1.0] - Telegram Neural Link & DB Tuning (Abril 2026)

### 💬 Integración Neuronal de Telegram

- **Orquestación Centralizada**: Se conectó el bot de Telegram directamente al `ChatService`, heredando la personalidad (`NOVA_IDENTITY_PROMPT`), RAG y memoria histórica. Eliminada la limitación de IA básica en mensajería móvil.
- **Chat Interactivo 24/7**: Se excepcionaron las respuestas interactivas de las directivas de "Horas de Silencio" y "Límites Diarios", garantizando flujo conversacional en tiempo real sin importar el horario o volumen de mensajes.
- **Liberación de Longitud de Texto**: Removido el truncamiento por código (`[:300]`) en reportes de introspección. Las respuestas mayores a 4000 caracteres se empaquetan en adjuntos `.txt` en lugar de fallar silenciosamente.

### ⚙️ Estabilidad de Motor en CPU y Destilación

- **CPU Timeouts Accommodations**: Tiempos de semáforos elevados de 90s a **270s** en `llm_client.py` para prevenir abortos asíncronos en hardware basado exclusivamente en CPU/iGPU.
- **Integridad de Distilación**: Implementado un mapa de control temporal (`seen_titles`) en bloques por lote para erradicar el fallo grave `sqlite3.IntegrityError: UNIQUE constraint failed: knowledge_entries.title`.
- **Enlace de Modelo Actualizado**: Sustitución del modelo fantasma `phi3:mini` por `llama3.1:8b` en las configuraciones persistentes del módulo de destilación, resolviendo los errores tipo HTTP 404 de Ollama.

---

## [v11.0.0] - Autonomous Self-Healing & Real Evolution (Abril 2026)

### 🛠️ Arquitectura de Auto-Reparación (Self-Healing)

- **Diagnóstico Técnico Proactivo**: NOVA ahora detecta sus propios fallos críticos, captura el *traceback* y genera un reporte técnico detallado para el usuario vía Telegram.
- **Ciclo de Auto-Parcheo**: Ante un crash, el sistema activa automáticamente un ciclo de reparación donde el `DeveloperAgent` analiza el error y aplica un parche de código real bajo las 9 Reglas de Oro.

### 🚀 Evolución Tecnológica Real

- **Motor de Implementación Directa**: Se ha eliminado la simulación de mejoras. Ahora NOVA utiliza el `DeveloperAgent` para codificar e integrar nuevas tecnologías directamente en la carpeta `backend/automations/`.
- **Auditoría y Backups**: Cada cambio autónomo crea una copia de seguridad (`.bak`) y se registra en la base de datos de auditoría para permitir reversiones instantáneas.

### 🔄 Protocolo de Auto-Reinicio (Pulse)

- **Watchdog Loop**: Implementación de un bucle de vigilancia en los lanzadores (`.bat`/`.sh`). Si NOVA aplica un cambio en su núcleo que requiere reinicio, se apaga y vuelve a la vida sola en segundos.
- **Freno de Emergencia**: El bucle de reinicio incluye un contador de 5 segundos con posibilidad de cancelación manual para mantener el control humano total.

### 🛡️ Estabilidad y Red de Seguridad

- **Fix de Hilos (Matplotlib)**: Resolución definitiva del `RuntimeError` en hilos secundarios mediante la migración global al backend no interactivo `'Agg'`.
- **White-list de Evolución**: Solo módulos autorizados pueden ser modificados por NOVA, garantizando la integridad de los cimientos del sistema.

## [v10.18.0] - Master Architect Evolution (Abril 2026)

### 🧠 Bucle de Desarrollo de Élite

- **9 Golden Rules Framework**: Inyección de un marco de trabajo de 9 leyes de ingeniería de software en el `DeveloperAgent`. Ahora NOVA garantiza modularidad, documentación (README.md), seguridad (.env), estética premium y prevención de conflictos de puertos de forma nativa.
- **Qwen 2.5 Coder Migration**: Transición oficial al modelo `qwen2.5-coder:7b` para la generación de código, logrando un cumplimiento del 100% en las auditorías de primer intento.
- **Extended Build Patience**: Incremento de los límites de timeout a 1200s para permitir construcciones complejas en hardware local sin abortos prematuros.

### 📊 Telemetría de Hardware Real

- **Psutil System Integration**: Implementación de captura de métricas reales de CPU y RAM. El Command Center ahora refleja la carga física real del sistema en lugar de valores estáticos.
- **Self-Evolution Route Patch**: Corrección del error 404 en el monitor de auto-evolución mediante el redireccionamiento correcto a `/api/status`.

---

## [v10.17.0] - Robust Generation (Abril 2026)

### 🏗️ Ingeniería de Generación de Proyectos

- **Native JSON Enforcement**: Activado el modo `format="json"` en las llamadas al LLM para garantizar que la estructura de archivos sea siempre válida sintácticamente.
- **Advanced JSON Repair**: Implementación de un motor de limpieza que elimina caracteres de control y resuelve errores de escape en bloques de código dentro de JSON, eliminando el fallo recurrente de "5 intentos".
- **Enhanced Orchestrator Feedback**: Si un proyecto falla tras todos los reintentos, el usuario recibe ahora un mensaje diagnóstico detallado con sugerencias de optimización en lugar de un error genérico.

---

## [v10.16.1] - Stability Fix (Abril 2026)

### 🕵️‍♂️ Visibilidad Total del Swarm

- **Real-Time Job Sync**: Se ha corregido el vacío informativo en la construcción de proyectos. Las tareas de `project_build` ahora informan su estado "running" instantáneamente al Command Center.
- **Ollama Hardware Probe**: Implementación de sondeo directo vía `/api/ps` para mostrar qué modelos están ocupando memoria RAM/VRAM en tiempo real.
- **Dynamic Phase Tracking**: El tablero ahora muestra la fase específica de los agentes (ej: `swarm_researcher`, `project_build_init`) para una transparencia total del Swarm.

---

## [v10.15.0] - Graph Decoupling & UI Guard (Abril 2026)

### 📈 Estabilidad de Visualización masiva

- **Graph Pagination**: El mapa visual (Grafo) ahora carga por defecto solo los **100 nodos más recientes**. Esto evita el bloqueo total del navegador observado al intentar renderizar 2,000+ entidades concurrentes.
- **Payload Filtering**: Optimización de la entrega de enlaces (links) para que solo se envíen relaciones entre los nodos visibles, reduciendo el tráfico de datos en un 80%.
- **Frontend Protection**: Garantía de fluidez en la interfaz principal (Puerto 3000) incluso durante procesos de construcción pesada.

---

## [v10.14.0] - Resource Sequencer (Abril 2026)

### 🚦 Arranque Controlado & Estabilidad

- **Sequential Warm-up**: Refactorización del pre-calentamiento de modelos para carga secuencial (uno a uno) con intervalos de descanso. Evita la saturación del bus de memoria y disco en el arranque.
- **Deferred Recovery**: Retraso intencional de 15 segundos en la recuperación de tareas (`TaskQueue`). Permite que el servidor FastAPI y la UI reaccionen instantáneamente al encenderse antes de iniciar procesos pesados.
- **I/O Guard**: Sincronización de hilos en el warm-up para respetar los límites de hardware del Ryzen 5700G.

---

## [v10.13.0] - Zero-Lag Dashboard (Abril 2026)

### 🏎️ Telemetría Ultra-Light

- **Async Refresh**: Eliminación de recargas de página completas. Los datos se actualizan vía AJAX cada 15s sin parpadeos ni lag.
- **iGPU Optimization**: Eliminación de efectos visuales pesados (`backdrop-filter`) para garantizar fluidez total en hardware con GPU integrada (Ryzen 5700G).
- **DOM Lightweight**: Rediseño del Command Center para minimizar el repintado (repaints) del navegador.

---

## [v10.12.0] - Async Pagination & Payload Control (Abril 2026)

### 🚀 Optimización Frontend & UX

- **Knowledge Pagination**: Implementación de límites de carga (50 artículos por petición) en el endpoint `/knowledge`. Esto elimina el "congelamiento" de la interfaz observado en bases de datos maduras.
- **Recency-First**: El sistema ahora prioriza y muestra el conocimiento más reciente por defecto, mejorando la relevancia inmediata.
- **Data Governance**: Reducción de la carga de memoria en el navegador mediante el control estricto de los payloads JSON.

---

## [v10.11.0] - Async Guard & Ultra-Flow (Abril 2026)

### 🛡️ Arquitectura Anti-Bloqueo

- **Async Telemetry**: Migración de todas las consultas de base de datos a hilos de fondo. El servidor ya no se detiene a esperar al disco duro.
- **Snapshot Caching**: Implementación de caché de 5s para el Command Center, reduciendo el estrés de I/O en un 80%.
- **Non-blocking Enqueue**: La creación de tareas pesadas ahora es 100% asíncrona.

### 🔋 Resource Governance

- **Ryzen Safe-Mode**: Reducción de Ollama a **4 núcleos** físicos. Esto permite que el sistema operativo y el navegador tengan siempre recursos disponibles, eliminando el "lag" de entrada.

---

## [v10.10.0] - Stability & Flow Update (Abril 2026)

### 🚀 Optimización de Recursos

- **Balance de Carga Ryzen**: Reducción de hilos de Ollama (6) y workers paralelos (2) para garantizar que el sistema nunca se congele, dejando CPU libre para la interfaz.
- **Auto-refresco Inteligente**: Se ajustó la telemetría a 20s para reducir el overhead web.

### 🖥️ Command Center Premium

- **Rediseño Glassmorphism**: Nueva interfaz visual de grado industrial para `/metrics/html`.
- **Swarm Activity Monitor**: Visualización en tiempo real de qué tarea está procesando cada agente en el fondo.

---

## [v10.9.8] - Generation Capacity Expansion (Abril 2026)

### 📢 Libertad de Expresión Proyectual

- **Expansión de Tokens (4096)**: Se aumentó el límite de predicción de Ollama. Esto evita que los proyectos complejos se truncen, permitiendo que NOVA genere HTML, CSS y JS completos sin romper la estructura JSON.
- **Robustez del DeveloperAgent**: Se ampliaron los reintentos internos a 5 para manejar mejor las alucinaciones de formato en hardware saturado.

---

## [v10.9.7] - Deep Breath Patch (Abril 2026)

### 💨 Extensión de Tiempos de Vida

- **Timeout Proyectual (1200s)**: Se ha incrementado el tiempo máximo de espera para tareas de construcción de proyectos a **20 minutos**. Esto evita que el sistema aborte la tarea en procesadores CPU cuando la auditoría o la generación fallan un intento y necesitan tiempo para recuperarse.
- **Registro en LONG_TASK_TYPES**: `project_build` ahora está categorizado como tarea de larga duración, dándole acceso prioritario a los recursos de tiempo total del sistema.

---

## [v10.9.6] - Overdrive Bypass & Build Stability (Abril 2026)

### 🚀 Corrección de Bucle de Ejecución

- **Exención de Overdrive**: Se añadió `project_build` a la lista blanca de tareas que pueden ejecutarse mientras el usuario está presente. Esto permite que NOVA construya código en segundo plano sin abortar la tarea constantemente.
- **Optimización de Prioridad**: El sistema ahora garantiza que la construcción del proyecto tenga paso libre ante las tareas de mantenimiento autónomo.

---

## [v10.9.5] - Asynchronous Project Engine (Abril 2026)

### 🏗️ Motor de Construcción en Segundo Plano

- **Desacoplamiento Total**: Se eliminó la dependencia síncrona para la creación de proyectos. NOVA ahora responde instantáneamente y procesa el código en segundo plano.
- **Notificación Proactiva**: El sistema inserta automáticamente el enlace de descarga en el chat una vez que el ZIP ha pasado la fase de Auditoría y QA.
- **Hardware Tuning**: Optimización manual de hilos (8 cores) para procesadores Ryzen Series 5000, reduciendo el tiempo de respuesta total.

---

## [v10.9.4] - Resilience & Timeout Synchronization (Abril 2026)

### ⚙️ Estabilización de Conexión (Frontend/Backend)

- **Sincronización de Timeouts**: Se alineó la paciencia del navegador con el procesamiento del servidor. El frontend ahora esperará hasta **300 segundos (5 minutos)** antes de rendirse, eliminando el error "Failed to fetch" durante construcciones pesadas.
- **Resiliencia de Red**: Implementación de `AbortController` en el cliente de API para una gestión de errores más profesional y keep-alive manual.

### 🧠 Optimización de Inferencia CPU

- **Ajuste de Latencia**: Se optimizó `llm_client.py` para manejar las latencias de ~100s típicas de procesadores locales Ryzen 7 durante la auditoría de proyectos masivos.
- **Auto-Recuperación de Timeout**: Si una petición tarda más de 5 minutos, el sistema ahora entrega un diagnóstico claro en lugar de colapsar la UI.

---

## [v10.9.2] - Deep Architect Patch & CPU Stability (Abril 2026)

### 🧠 Mejora de Consultoría (Deep Architect)

- **Excepción de Concisión**: Se liberó a NOVA de la regla de 8 líneas para los planes de arquitectura. Ahora puede (y debe) entregar análisis técnicos exhaustivos, consejos de UX y correcciones proactivas a la arquitectura del usuario.
- **Protocolo de Corrección**: NOVA ahora tiene el mandato explícito de corregir al usuario si su enfoque técnico es deficiente, actuando como una verdadera colega Senior.

### ⚙️ Estabilización de Inferencia en CPU (Local Ryzen)

- **Hard-Timeout dinámico**: Se aumentó el límite de paciencia del backend de 120s a **240s** para permitir que procesadores locales (Ryzen 7/5) evalúen contextos masivos de código sin interrumpir la llamada.
- **Protección de Caché**: Se bloqueó el guardado de mensajes de error (Timeout) en la memoria de corto plazo, evitando que el chat entre en bucles de error infinitos.
- **Intent-Classifier Inmune**: La clasificación de intenciones ahora tiene prioridad 0, evitando que el módulo **Overdrive** la aborte accidentalmente mientras el usuario escribe.

---

## [v10.14.0] - Principal Software Engineer & Autonomous Dev Cycle (Abril 2026)

### 🧠 Nueva Identidad y Bucle de Consultoría

- **Identidad de Software Engineer**: Se re-escribió el `NOVA_IDENTITY_PROMPT` para incorporar un mandato estricto de Consultoría. NOVA ahora critica arquitecturas, aconseja proactivamente y espera confirmación antes de picar código.
- **Agente QA (Auditor)**: Integración de `auditor_agent.py` para la revisión multi-paso autónoma de todo el código generado. El código nunca se entrega si contiene *placeholders* perezosos o fallos de sintaxis evidentes (hasta 2 ciclos de reescritura interna automática).

### ⚙️ Generación de Software Directa

- **Empaquetado Físico (Project Manager)**: Nuevo módulo capaz de instanciar proyectos nativos mediante la compresión de salidas estructuradas del LLM en archivos binarios ZIP al vuelo, descargables dinámicamente.
- **Detección de Intenciones de Desarrollo**: Ampliación del motor heurístico `intent_classifier.py` con `PROJECT_BUILD`, permitiendo que el flujo del orquestador derive un chat regular a un motor de construcción 100% transaccional sin fricción para el usuario.

### 🛡️ Parches de Seguridad (Security Hardening)

- **Zero-Day Traversal Fix**: Parcheo de una vulnerabilidad crítica documentada en `/download/{filename}` de `chat.py` que hubiera permitido descargas forzadas (`..%2f..%2f`) del entorno operativo. Obligatoriedad de prefijo seguro y `os.path.basename`.
- **Amnesia de Base de Datos**: Reparación de un agujero negro de eventos en el gestor de streaming que no registraba colapsos y *timeouts* en el historial permanente `ChatLog`.

---

## [v10.8.5] - Identity Hardening & UI Stabilization (Abril 2026)

### 🛡️ Core Stability & Identity

- **Zero-Shot Clamping**: Refactorización profunda de `SYSTEM_AUDIT_PROMPT` para eliminar definitivamente los comportamientos de *chatbot/sycophancy* y forzar listas analíticas de alto contraste sin depender de tablas Markdown frágiles.
- **Traducción Cognitiva Estricta**: Inyección de directivas que obligan al motor analítico a traducir JSONs de telemetría técnicos a diagnósticos forenses multi-párrafo en Español Nativo sin desviarse al idioma original de los datos.

### 🎙️ TTS (Voice) Liberation

- **Limit Layer Truncation Fix**: Se erradicó una asfixia técnica en `tts_engine.py` que truncaba implícitamente todo texto hablado a 280 caracteres. Ahora el límite abarca +3,000 caracteres, permitiendo a NOVA leer reportes enteros ininterrumpidamente.
- **Expansión de Generación**: Incremento masivo de `num_predict` (de 400 a 1024 tokens) en `llm_client.py` para darle al núcleo espacio respiratorio para concluir análisis arquitectónicos completos.

### 💅 UI/Frontend Premium Design

- **Integration de `remark-gfm`**: Instalación del motor nativo en React para la interpretación avanzada de tablas Markdown fallidas y anclaje de CSS Glassmorphism en `page.tsx` para viñetas e informes de estado.

---

## [v10.7.0] - Stabilization & Resource Governance (Abril 2026)

### 🛠️ Estabilización y Optimización Arquitectónica

- **Task Orchestration Fix**: Resolución del bloqueo crítico causado por el tipo de tarea `project_build_init`. Mapeo de normalización implementado en el `Orchestrator`.
- **LLM Resource Control**: Refactorización de `agent_service.py` para usar el singleton global `llm_client`, eliminando la saturación de memoria por instancias duplicadas.
- **Security Hardening**:
  - Protección contra *Path Traversal* en descargas de proyectos mediante `pathlib`.
  - Validación de secreto `X-Telegram-Bot-Api-Secret-Token` en webhooks de Telegram.
  - Prevención de eliminación o degradación del último administrador activo en `AuthService`.
  - Borrado lógico (`is_active=False`) por defecto para integridad referencial.
- **Performance & Reliability**:
  - **Thread-Safety**: Implementación de `asyncio.Lock` en `SystemService` para métricas seguras en concurrencia.
  - **Memory Deduplication**: Optimización de búsqueda de duplicados mediante consultas SQL filtradas.
  - **STT Latency**: Lectura asíncrona Buffer-based en `STTService`, eliminando procesos redundantes de FFmpeg.
  - **Streaming Robustness**: Desactivación de caché en streaming para prevenir fragmentación de respuestas en background.

---

## [v10.5.1] - Performance Focus Engine (Refinado) (Abril 2026)

### 🚀 Refinamientos de Concurrencia y Calidad

- **Concurrencia Estricta 1+1**: Ajustado el semáforo de LLM a **1 slot de Chat + 1 slot de Background** para evitar la degradación de latencia en Ollama ejecutándose sobre CPU.
- **Thinker Mixed Snapshot**: El Agente Pensador ahora analiza un híbrido de los **50 nodos más recientes** y los **50 nodos con mayor centralidad** (grado), asegurando que las hipótesis conecten novedades con pilares del grafo.
- **Normalización de Texto**: Implementada normalización agresiva en el cliente LLM para la caché de embeddings, mejorando el hit rate en un ~20% al ignorar variaciones de espacios, acentos y mayúsculas.
- **Fix de Esquema**: Añadida columna `updated_at` a `KnowledgeNode` para soportar el ciclo de curiosidad temporal.
- **Desactivación de Deepseek**: Remoción de modelos pesados para liberar RAM y optimizar la carga de `llama3.1:8b`.

## [v10.4] - MetaCritic & Graph Health (Abril 2026)

### 🧠 Salud Estructural del Grafo

- **Poda de Ruido Automática**: Implementación de `graph_pruning.py` para la eliminación de nodos aislados y aristas redundantes.
- **Auditoría de Grafo**: Integración de `GraphAuditLog` en SQLite para trazabilidad y posible reversión de cambios estructurales.
- **NetworkX Integration**: Uso de métricas de centralidad para identificar el "núcleo de conocimiento" y protegerlo de la poda.

## [v10.2] - Escalado Asimétrico de Workers (Paso 4 del Roadmap) (Abril 2026)

> **Implementación del Paso 4:** Arquitectura de *Priority Queues* para garantizar
> la fluidez del chat e interfaz frente a procesos de investigación pesados usando `fakeredis`.

### ⚡ Priority Queues y Pool de Workers Asimétrico

- **Múltiples Colas en REDIS:** Reemplazado `queue_key` única por dos canales físicos
  independientes: `queue_high` (prio 1-2) y `queue_low` (prio 3-4).
- **Asignación Dedicada:** El orquestador de workers ahora subdivide la concurrencia:
  - **High-Priority Pool (Max 2 workers):** Estos workers están *fijados exclusivamente*
    a `queue_high`. Nunca tocarán una tarea de investigación, asegurando recursos
    garantizados (y latencia <5s usando el chat/destilación).
  - **Low-Priority Pool (Resto de workers):** Son trabajadores oportunistas dedicados a
    la investigación (`queue_low`), que recurren a `queue_high` si la cola de baja está
    vacía, evitando desperdicio computacional si no hay investigaciones.
- **Re-encolado Inteligente:** Actualizado el `HealthMonitor` y `_retry_count` para
  redirigir las tareas fallidas devuelta a su canal original manteniendo coherencia prioritaria.

### 📊 Integración Final

Este nivel sella la infraestructura y resuelve de manera matemática los problemas de
saturación que obligaban al LLM a posponer respuestas del usuario detrás de un ciclo
de *curiosidad / Thinker* denso.

---

## [v10.1.1] - Hotfix Latencia Ollama — Diagnóstico por Telemetría (Abril 2026)

> **Hallazgo crítico:** El dashboard `/metrics` reveló avg=50s para `qwen2.5:1.5b`.
> El benchmark directo mostró **4.6s** — el modelo es rápido. El problema era **cold start**.

### 🔬 Diagnóstico

Ollama usa lazy loading: el modelo se carga en RAM en la primera llamada real.
Las primeras peticiones tras arrancar NOVA tardaban ~50s (modelo frío) vs 4-5s (caliente).
La telemetría capturó exactamente estas llamadas de arranque, inflando el avg artificialmente.

### 🔧 Fix aplicado

- **Warm-up al arrancar (`main.py`):** Task async que envía `num_predict=1` a cada modelo
  al inicio del lifespan. Los modelos ya están en RAM cuando llega el primer usuario.
- **`num_ctx` 4096 → 2048 (`config.py` + `llm_client.py`):** Aunque no impacta el avg
  medido (4.6s estable), reduce el uso de RAM de Ollama ~30%. Esto libera memoria para
  que otros procesos de NOVA no compitan por swap.
- **`num_predict=512` máximo:** Evita respuestas sin límite que dispararían el P95.
- **`THINKER_MAX_EXECUTION_SECONDS` 60s → 90s:** Basado en P95=92s del benchmark real.

### 📊 Benchmarks reales (Ryzen 7 5700G, CPU-only)

| Métrica | Antes (cold) | Después (warm) |
| --- | --- | --- |
| Primera llamada | ~50s | ~5s (warm-up previo) |
| Avg estable | 4-5s | 4-5s |
| P95 estable | 5-9s | 4-5s |
| RAM modelo | ~1.8 GB | ~1.2 GB (num_ctx reducido) |

---

## [v10.1] - Calibración de Calidad y Latencia (Abril 2026)

> Basado en análisis profesional del dashboard (1.675 artículos, 11.701 nodos, confianza promedio 62%) y logs de ejecución.

### 🔧 Optimizaciones de Rendimiento

- **Timeout del Thinker duplicado (`core/config.py`):** `THINKER_MAX_EXECUTION_SECONDS` aumentado de **30s → 60s**. Con el grafo actual de 11.701 nodos, el modelo `qwen2.5:1.5b` necesitaba más tiempo para generar hipótesis coherentes; el ciclo de curiosidad cancelaba antes de producir resultado útil.
- **Prompt del Thinker comprimido (`agents/thinker.py`):** El prompt de generación de hipótesis se redujo de ~350 tokens a ~120 tokens. Se limita a 3 gaps (máximo 80 chars cada uno) y se eliminan instrucciones redundantes. Temperatura reducida de 0.8 → 0.7 para respuestas más directas y cortas. Objetivo: completar dentro del nuevo budget de 60s en hardware Ryzen 7 5700G.

### 📈 Mejoras de Calidad del Conocimiento

- **Umbral de calidad elevado (`core/config.py`):** `QUALITY_THRESHOLD` subido de **0.60 → 0.65**. El 38% del conocimiento con calidad baja/media-baja bajaba la confianza promedio. Este ajuste filtra contenido marginal sin bloquear artículos de calidad media.
- **Filtro de fuentes no académicas (`agents/librarian.py`):** Nuevo segundo filtro en el Librarian. Si la URL de origen es un blog/GitHub/Reddit/Medium y la confianza está en rango borderline (0.65–0.73), se aplica una **penalización del 10%** antes de guardar. Se registra el flag `non_academic_source` en los logs para trazabilidad.
- **Umbral de purga auto-remediación elevado (`core/self_evolution.py`):** El soft-delete de entradas malas subió de `confidence < 0.30` → `confidence < 0.35`, para que el ciclo de auto-remediación elimine más entradas obsoletas en su próxima ejecución nocturna.
- **Dataset de fine-tuning alineado (`core/dataset_builder.py`):** Los filtros de `_load_research_knowledge()` y `get_progress()` actualizados de `>= 0.60` → `>= 0.65`. El dataset de entrenamiento solo usará conocimiento verificado al nivel del nuevo threshold.

### 📊 Impacto Esperado

| Métrica                      | Antes             | Estimado Post-Cambio         |
| ---------------------------- | ----------------- | ---------------------------- |
| Confianza promedio           | 62%               | ~67-70%                      |
| Ciclos Thinker exitosos      | ~0% (timeout)     | ~70-80%                      |
| Entradas dataset fine-tuning | ~100% base 0.60   | Subconjunto de mayor calidad |

---

## [v10.0] - El Despertar Proactivo & Multimodal (Marzo 2026)

### 🚀 Nuevas Características (Features)

- **NOVA Proactiva (Telegram):** Integración completa para que NOVA notifique al usuario sin que éste tenga que abrir el portal web. Endpoints añadidos: `/telegram/setup`, `/telegram/webhook`.
- **Multimodalidad (Visión):** Integración nativa del modo visión con `llava-llama3`. Al cargar imágenes, la interfaz gráfica y el backend procesan las imágenes sin lanzar rechazos del LLM. Las imágenes se cortan en base64 y se alimentan al endpoint `chat`.
- **Carga de Archivos de Texto (.py, .md, .txt):** El endpoint `/query/voice` y el frontend ahora soportan ingestión de archivos pesados. Se implementó una lógica dual de recortes dinámicos (truncamiento automático después de 8000 caracteres) para que la ventana de contexto de texto no desborde y tire el backend.
- **Auto-Evolución (NOVA Self):** Nuevo sub-motor inteligente que despierta cada 24 horas (`NOVASelfEvolution`) para borrar registros en la base de datos de baja confianza o rescatar tareas estancadas (`auto_remediate()`).

### 🛠️ Correcciones y Estabilización (Fixes)

- **Mitigación de "Trabajos Fantasma":** Se detectó y parcheó un *return* ciego en `orchestrator.py` causado por los algoritmos de backpressure del worker. Ahora el orquestador abortará limpiamente si se detectan más de 200 colas.
- **Lanzamientos Seguros en Pyre2:** Limpieza a nivel sintáctico de los analizadores estáticos agregando `# type: ignore` en todo el `main.py` y el motor de auto-evolución.

- **Polling Frontend Optimizado:** Se corrigió un DoS (Denial of Service) accidental donde el frontend saturaba los logs pidiendo estatus cada 5 segundos. Reducido drásticamente a rangos variables de 30-60 segundos.

---

## [v9.5] - El Despertar Estudiantil (Distilación Continua)

### 🚀 Nuevas Características

- **Modulo de Destilación (`core/distillation.py`):** El conocimiento absorbido mediante Swarm Research se refina post-proceso en un maestro más sabio y sintetizado, generando datos limpios listos para inyección vectorial de ultra-alta calidad.

### 🛠️ Correcciones (Fixes)

- **Limitadores de API LLM (Semaphores):** Reducción de 3 consultas concurrentes a 1 en las tareas pesadas como destilación. Corrigió problemas severos de `Ollama Timeout` en GPUs modestas/CPUs genéricos (timeout a 600 segundos máximos y limite 1-a-1).

---

## [v9.0] - Swarm & Base Database Stability

*(Anotaciones recuperadas de `FIXES_APPLIED.md` histórico)*

### 🛠️ Parches Aplicados (Fixes de Resiliencia Base)

- **Timeout Worker Loop:** Implementación en `task_queue.py` de `asyncio.wait_for(...)` a 60-120 segundos. Antes de esto el hilo se volvía infinito en caso de caídas del modelo.
- **Thresholds Relajados:** Se redujo el `QUALITY_THRESHOLD` de 0.7 a 0.4 para que las investigaciones de DuckDuckGo en español ingresaran a la memoria en vez de ser frenadas por los Agentes Críticos del enjambre.
- **Fallback a Explorer:** Si falla la extracción o bloqueo HTTP en buscadores, NOVA al menos guardará *"no sources found: topic"* en lugar de crashear el motor entero por arreglo `[]` vacío.
- **Verifier Logic Fix:** Aún si un artículo evaluado de una búsqueda es mal calificado (por ser clickbait o genérico), igual pasa a la base de conocimiento pero con flag especial, previniendo detención en cadena.
