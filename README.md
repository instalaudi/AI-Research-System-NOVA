# 🤖 Neural Autonomous Versatile Agent (NOVA) v12.0.0 "Agentic Skills & Persistence"

## Identity: Principal Software Engineer & Autonomous Researcher

### Hardware Target: Local CPU/Ryzen Swarm Infrastructure (Turbo Optimized)

Bienvenido a la versión **v12.0.0** de **NOVA**. Esta actualización mayor integra el motor de habilidades agenticas (**Agentic Skills Integration**). El sistema ahora incorpora **Chunking Semántico** de documentos, un **Sistema Autónomo de Lecciones Aprendidas** (Memoria Muscular para evitar repetir errores en builds) y **Protocolos Handoff** para asegurar cero pérdida de contexto entre el enjambre de agentes.

![Dashboard Preview](https://imgshields.io/badge/Versi%C3%B3n-12.0.0-green?style=for-the-badge&logo=ai)
![Stack](https://imgshields.io/badge/Stack-Next.js%20|%20FastAPI%20|%20Ollama%20|%20ST-green?style=for-the-badge)

El sistema ha evolucionado de un chat tradicional a un **Cerebro Digital** con capas cognitivas:

- **Cognitive Controller**: El motor lógico central que decide el modo de ejecución (SYSTEM, RESEARCH, KNOWLEDGE) de forma determinista, reduciendo la dependencia del LLM para el ruteo.
- **Prompt Pipeline (Multifase)**: Fragmenta el razonamiento en etapas de **Interpretación**, **Planeación** y **Generación**, lo que garantiza respuestas estructuradas y precisas.
- **Reflection Layer (Post-Verificación)**: Una capa de auto-auditoría que revisa la respuesta generada contra los hechos reales del sistema para detectar y corregir alucinaciones post-procesamiento.
- **Tool-First Strategy**: El sistema siempre prioriza la recolección de evidencia (RAG, Grafos, Estado del Sistema) antes de iniciar cualquier proceso creativo.

## 🌐 Memoria y Grafo de Conocimiento Dinámico

- **Knowledge Graph**: Extracción automática de tripletas semánticas (Sujeto -> Relación -> Objeto) durante el aprendizaje para crear una red de conceptos interconectados.
- **Memoria de 3 Capas**:
  - **Episódica**: Contexto conversacional reciente optimizado.
  - **Semántica**: RAG dinámico + Graph Enrichment.
  - **Operativa**: Conciencia total del propio estado (agentes, documentos, carga de sistema).

## 🛠️ Swarm de Agentes, Desarrollo y Sandbox

- **Swarm Investigador**: Planner, Explorer, Analyzer, Critic y Librarian trabajando en paralelo con deduplicación vectorial.
- **Swarm Desarrollador (Developer Loop)**: DeveloperAgent y AuditorAgent (QA) iteran sobre el código recién escrito hasta que compila perfecto.
- **Gestor de Activos (v11.1.2)**: Pestañas de **Proyectos**, **Librería** (snippets), **Historial** (semántico) y **Git** (commits locales + diff).
- **Versionado Git Automático**: Cada build exitoso guarda snapshot local y crea commit automático seguro por rutas explícitas.
- **Auto-Reparación (Self-Healing)**: Motor de diagnóstico proactivo que detecta crashes, analiza tracebacks y aplica auto-parches de emergencia.
- **Telegram Neural Link**: Integración total del bot conversacional móvil con el Cerebro Central, dotándolo de memoria a largo plazo (RAG), personalidad sólida e inmunidad horaria interactiva.
- **NIAW (NOVA Immutable & Atomic Writes)**: Blindaje de datos contra cortes de energía. Sistema de escritura Write-Flush-Fsync-Replace que garantiza integridad atómica y backups automáticos (.bak).
- **IntegrityGuard (Watchdog)**: Guardián de arranque que escanea archivos críticos, detecta bytes nulos/vacíos y restaura estados automáticamente notificando por voz (TTS).
- **Monitor de Salud Total (v11.0)**: Panel de auditoría persistente y transaccional que centraliza fallos de infraestructura, errores de conectividad (Ollama) y corrupción de datos con alertas visuales dinámicas (pulsos Red/Amber) y auto-limpieza inteligente de registros operativos.
- **Evolución Real**: Capacidad nativa para integrar nuevas tecnologías y módulos en el núcleo sin intervención humana.
- **Watchdog Protection**: Bucle de vigilancia de procesos que garantiza un uptime del 99.9% mediante reinicios autónomos tras actualizaciones de núcleo.
- **Sandbox Seguro**: Ejecución aislada de Python y JS para verificar datos mediante computación real, integrada en el flujo cognitivo.
- **STT & Visión**: Control por voz (Whisper) y análisis visual avanzado.

---

## 🛠️ Cómo Comenzar (Instalación)

### Requisitos Previos

- **Python 3.10+** (Recomendable entornos virtuales activos)
- **Node.js 18+**
- **Ollama** (Instalado y con los modelos `deepseek-r1:8b` y `llava-llama3` descargados)

### Inicio Rápido (Windows)

Simplemente ejecuta el script de consolidación:

```powershell
./start_ai_system.bat
```

1. Configurará Bases de Datos (Evolucionado SQLite modo WAL + Chroma DB Local Storage).
2. Conectará persistencias.
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

## 🧪 Notas de Estabilización (Edición v9.0)

Esta edición elimina por completo fugas históricas de sockets HTTP, caídas del Pool de sesiones transaccionales y colapsos sincrónicos originarios de la arquitectura anterior, rindiendo un uptime estable sin degradación del LLM Context. Se integró _Provenance Tracking_ que indexa internamente URLs verificables a nivel Base de Datos (Source Truth).

---

### Novedades v11.1.2

- Snippet cache funcional con búsqueda y reutilización directa desde UI.
- Historial semántico de código con endpoint `/api/history/search`.
- Git history endpoint `/api/git/history` y diff endpoint `/api/git/diff/{commit_hash}`.
- Drawer de diff con overlay clickeable y cierre por tecla Escape.

_Desarrollado con ❤️ para la investigación predictiva escalable._
