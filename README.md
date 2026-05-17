# 🤖 Neural Autonomous Versatile Agent (NOVA) v13.9.0 "Sensory Awareness & Neural Voice"

## Identity: Principal Software Engineer & Autonomous Researcher

### Hardware Target: Local CPU/Ryzen Swarm Infrastructure (Turbo Optimized)

Bienvenido a la versión **v13.9.0** de **NOVA**. Esta actualización mayor transforma a NOVA en un sistema con **Consciencia Sensorial y Voz Neuronal**, integrando visión en tiempo real, síntesis de audio neural local y automatización empresarial.

![Dashboard Preview](https://imgshields.io/badge/Versi%C3%B3n-13.9.0-green?style=for-the-badge&logo=ai)
![Stack](https://imgshields.io/badge/Stack-Next.js%20|%20FastAPI%20|%20Ollama%20|%20Kokoro-green?style=for-the-badge)

El sistema ha evolucionado de un chat tradicional a un **Cerebro Digital** con capas cognitivas:

- **Persistent Vision Eye (Ojo Persistente)**: Daemon en segundo plano (`core/vision_monitor.py`) con detección facial de OpenCV, comparación por Distancia de Hamming (pHash) y alertas proactivas ante anomalías o cambios de presencia.
- **Kokoro-82M Voice Synthesis**: Motor neural local de alta fidelidad que ofrece síntesis de voz en español fluida y de muy bajo consumo en CPU, con fallback automático.
- **Google Workspace & OAuth2**: Integración segura de APIs de Google (Gmail, Calendar) para automatizar la gestión y filtrado de comunicaciones de manera autónoma.
- **Cognitive Controller**: El motor lógico central que decide el modo de ejecución (SYSTEM, RESEARCH, KNOWLEDGE) de forma determinista, reduciendo la dependencia del LLM para el ruteo.
- **Prompt Pipeline (Multifase)**: Fragmenta el razonamiento en etapas de **Interpretación**, **Planeación** y **Generación**, lo que garantiza respuestas estructuradas y precisas.
- **Reflection Layer**: Capa de auto-auditoría que revisa respuestas y código contra los hechos reales del sistema para corregir alucinaciones.

## 🌐 Memoria y Grafo de Conocimiento Dinámico

- **Knowledge Graph (LightRAG)**: Extracción de tripletas semánticas (Sujeto -> Relación -> Objeto) y memoria visual a largo plazo persistida en grafos de conocimiento.
- **Memoria de 3 Capas**:
  - **Episódica**: Contexto conversacional reciente optimizado.
  - **Semántica**: RAG dinámico + Graph Enrichment.
  - **Operativa**: Conciencia total del propio estado (agentes, documentos, carga de sistema).

## 🛠️ Swarm de Agentes, Desarrollo y Sandbox
- **Swarm Investigador**: Planner, Explorer, Analyzer, Critic y Librarian trabajando en paralelo con deduplicación vectorial.
- **Swarm Desarrollador (Developer Loop)**: DeveloperAgent y AuditorAgent (QA) iteran sobre el código recién escrito hasta que compila perfecto.
- **Gestor de Activos**: Pestañas de **Proyectos**, **Librería** (snippets), **Historial** (semántico) y **Git** (commits locales + diff).
- **Versionado Git Automático**: Cada build exitoso guarda snapshot local y crea commit automático seguro por rutas explícitas.
- **Auto-Reparación (Self-Healing)**: Motor de diagnóstico proactivo que detecta crashes, analiza tracebacks y aplica auto-parches de emergencia.
- **Telegram Neural Link**: Integración total del bot conversacional móvil con el Cerebro Central, dotándolo de memoria a largo plazo (RAG), personalidad sólida e inmunidad horaria interactiva.
- **NIAW (NOVA Immutable & Atomic Writes)**: Blindaje de datos contra cortes de energía. Sistema de escritura Write-Flush-Fsync-Replace que garantiza integridad atómica y backups automáticos (.bak).
- **IntegrityGuard (Watchdog)**: Guardián de arranque que escanea archivos críticos, detecta bytes nulos/vacíos y restaura estados automáticamente notificando por voz (TTS).
- **Monitor de Salud Total**: Panel de auditoría persistente y transaccional que centraliza fallos de infraestructura, errores de conectividad (Ollama) y corrupción de datos con alertas visuales dinámicas (pulsos Red/Amber) y auto-limpieza inteligente de registros operativos.
- **Evolución Real**: Capacidad nativa para integrar nuevas tecnologías y módulos en el núcleo sin intervención humana.
- **Watchdog Protection**: Bucle de vigilancia de procesos que garantiza un uptime del 99.9% mediante reinicios autónomos tras actualizaciones de núcleo.
- **Sandbox Seguro**: Ejecución aislada de Python y JS para verificar datos mediante computación real, integrada en el flujo cognitivo.
- **STT & Visión**: Control por voz (Whisper) y análisis visual avanzado.

---

## 🛠️ Cómo Comenzar (Instalación)

### Requisitos Previos

- **Python 3.12+** (Recomendable entornos virtuales activos)
- **Node.js 18+**
- **Ollama** (Instalado y con los modelos `qwen2.5:1.5b`, `qwen2.5-coder:3b` y `llava` descargados)

### Inicio Rápido (Windows)

Simplemente ejecuta el script de inicio oficial de NOVA:

```powershell
./start_NOVA.bat
```

1. Configurará Bases de Datos (Evolucionado SQLite modo WAL + Chroma DB Local Storage + LightRAG).
2. Conectará persistencias y cargará el Ojo Persistente (si está activo en `.env`).
3. Iniciará Microservicios asíncronos concurrentes.

---

## 📂 Estructura del Proyecto

- `/backend`: Servidor FastAPI, Motor de LLMs, Worker Queue (Redis/In-Memory), VectorDB (ChromaDB) y SQLite.
- `/frontend`: Interfaz Next.js moderna, Server-Sent Events (Streaming), Glassmorphism UX.

---

## ⚡ Comandos Útiles

**Backend:**

```bash
cd backend
venv\Scripts\activate
uvicorn main:app --reload
```

**Frontend:**

```bash
cd frontend
npm run dev
```

---

## 🧪 Notas de Estabilización (Edición v13.9.0)

Esta edición está diseñada para máxima estabilidad y rendimiento local en CPU. Se implementa concurrencia serializada estricta para evitar la saturación de núcleos durante inferencias Ollama concurrentes, optimización de base de datos SQLite en modo WAL de alta velocidad con RAG dinámico (LightRAG), blindaje de integridad de archivos críticos (IntegrityGuard) y exclusión segura de archivos pesados y credenciales en el control de versiones.

---

### Novedades v13.9.0

- **Persistent Vision Eye:** Detección de movimiento y reconocimiento facial ligero (pHash + Hamming Distance) con OpenCV y notificaciones proactivas en Telegram.
- **Motor de Voz Kokoro-82M:** Síntesis neural local ultra-rápida y natural en español optimizada para CPU.
- **Google Workspace & OAuth2:** Integración segura con Gmail y Calendar para lectura y automatización de correo.
- **Launcher Control Center:** Interfaz unificada de consola interactiva para el inicio, apagado y monitoreo de servicios del enjambre.

_Desarrollado con ❤️ para la investigación predictiva escalable._
