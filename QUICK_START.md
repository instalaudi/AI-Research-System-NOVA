# AI-Research-System - Guía de Inicio Rápido (v11.1.1)

## 1. Configuración de Modelos (CRÍTICO)

El sistema NOVA está optimizado para **Qwen3:8b** con fallback a **DeepSeek-R1:8b**. Asegúrate de que Ollama esté instalado y ejecutándose.

```bash
# Descargar modelos recomendados
ollama pull qwen:3-8b
ollama pull deepseek-r1:8b
ollama pull llava-llama3
```

---

## 2. Configurar Variables de Entorno

### Editar backend/.env

```env
# LLM Configuration (NOVA Optimizer)
LLM_MODEL_NAME=qwen:3-8b
OLLAMA_URL=http://localhost:11434/api/chat
LLM_FAST_MODEL=qwen:3-8b

# Ambiente
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

---

## 3. Verificación de Arquitectura NOVA (v11.1.1)

Una vez iniciado el sistema, puedes verificar las nuevas capas cognitivas y el gestor de proyectos:

### Consulta de Estado del Sistema (Cognitive Controller)

El backend devuelve metadatos estructurados sin usar el LLM para consultas de infraestructura.

```bash
curl http://127.0.0.1:8000/api/status
```

### Crear un Proyecto

Simplemente escribe en el chat:
```
Crea una aplicación web simple de lista de tareas en React
```

El sistema:
1. Generará el código automáticamente usando el DeveloperAgent
2. Detectará la creación exitosa
3. Cambiará automáticamente a la pestaña **"Proyectos"**
4. Mostrará el proyecto en la lista con metadatos de tamaño y fecha

### Listar Proyectos (API)

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://127.0.0.1:8000/api/projects/list
```

**Respuesta típica:**
```json
{
  "projects": [
    {
      "filename": "nova_project_1_lista-tareas.zip",
      "size": 52428,
      "created": 1713033600,
      "download_url": "/api/download/nova_project_1_lista-tareas.zip"
    }
  ]
}
```

### Gestión de Proyectos UI

1. **Crear Proyecto**: Escribe la solicitud en el chat
2. **Cambio Automático**: El frontend te lleva a la pestaña "Proyectos"
3. **Ver Detalles**: Nombre, tamaño, fecha de creación
4. **Descargar**: Haz clic en el botón de descarga para obtener el ZIP

### Probar Auto-Reflexión

Pregunta algo sobre temas desconocidos. El sistema activará el Swarm de Agentes si su capa de auto-reflexión detecta que no tiene datos suficientes en el RAG.

### Verificar Knowledge Graph

Consulta las conexiones semánticas extraídas automáticamente:

```bash
curl http://127.0.0.1:8000/api/graph
```

---

## 4. Estructura de Memoria Experta

NOVA utiliza una memoria de 3 capas:

1. **Episódica**: (Contexto reciente) - SQLite.
2. **Semántica**: (Conocimiento profundo) - ChromaDB + Graph.
3. **Operativa**: (Estado del sistema) - Backend Metadata.

---

## 5. Novedades de v11.1.1

### ✨ Project Manager
- **Gestión Centralizada**: Todos los proyectos generados en un solo lugar
- **Cambio Automático de Pestaña**: Se activa automáticamente al crear un proyecto
- **Metadatos Dinámicos**: Tamaño formateado, fecha en zona horaria local
- **Interfaz Responsiva**: Grid adaptable a cualquier tamaño de pantalla
- **Descarga Flexible**: Elige cuándo descargar en lugar de descarga automática

### 🎯 Mejoras de UX
- Flujo streamlined: Crear → Detectar → Navegar
- Sin intervención manual requerida
- Mejor organización de proyectos generados

---

**Estado Final:** 💎 **NOVA v11.1.1 WITH PROJECT MANAGER ACTIVE**

**Última Actualización:** 2026-04-13

**Modo Operativo:** Tool-First + Reflection Layer + Project Management
