# AI-Research-System - Guía de Inicio Rápido (v10.0 JARVIS)

## 1. Configuración de Modelos (CRÍTICO)

El sistema JARVIS está optimizado para **DeepSeek-R1**. Asegúrate de que Ollama esté instalado y ejecutándose.

```bash
# Descargar modelos recomendados
ollama pull deepseek-r1:8b
ollama pull llava-llama3
```

---

## 2. Configurar Variables de Entorno

### Editar backend/.env

```env
# LLM Configuration (JARVIS Optimizer)
LLM_MODEL_NAME=deepseek-r1:8b
OLLAMA_URL=http://localhost:11434/api/chat

# Ambiente
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

---

## 3. Verificación de Arquitectura JARVIS

Una vez iniciado el sistema, puedes verificar las nuevas capas cognitivas:

### Consulta de Estado del Sistema (Cognitive Controller)

El backend devuelve metadatos estructurados sin usar el LLM para consultas de infraestructura.

```bash
curl http://127.0.0.1:8000/status
```

### Probar Auto-Reflexión

Pregunta algo sobre temas desconocidos. El sistema activará el Swarm de Agentes si su capa de auto-reflexión detecta que no tiene datos suficientes en el RAG.

### Verificar Knowledge Graph

Consulta las conexiones semánticas extraídas automáticamente:

```bash
curl http://127.0.0.1:8000/graph
```

---

## 4. Estructura de Memoria Experta

JARVIS utiliza una memoria de 3 capas:

1. **Episódica**: (Contexto reciente) - SQLite.
2. **Semántica**: (Conocimiento profundo) - ChromaDB + Graph.
3. **Operativa**: (Estado del sistema) - Backend Metadata.

---

**Estado Final:** 💎 **JARVIS ARCHITECTURE ACTIVE**

**Última Actualización:** 2026-03-16

**Modo Operativo:** Tool-First + Reflection Layer
