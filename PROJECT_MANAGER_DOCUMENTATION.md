# Documentación del Project Manager (v11.1.2)

## Overview

El **Project Manager** es un sistema centralizado para gestionar activos de desarrollo generados por NOVA. En v11.1.2 incluye cuatro vistas: **Proyectos**, **Librería** (snippets), **Historial** (semántico) y **Git** (commits + diff).

---

## Arquitectura

### Frontend (React/Next.js)

#### Componente: `ProjectManager.tsx`
- **Ubicación**: `frontend/src/components/ProjectManager.tsx`
- **Responsabilidades**:
  - Listar proyectos del usuario autenticado
  - Buscar snippets reutilizables
  - Buscar historial semántico de código
  - Mostrar historial Git local y diffs por commit
  - Formatear metadatos (tamaño, fecha)
  - Manejar descargas de archivos ZIP
  - Gestionar estados de carga y errores

**Props Aceptadas**: Ninguno (usa contexto de autenticación y hooks)

**State Principal**:
```typescript
const [projects, setProjects] = useState<Project[]>([]);
const [loadingProjects, setLoadingProjects] = useState(true);
const [projectsError, setProjectsError] = useState<string | null>(null);
const [snippetsError, setSnippetsError] = useState<string | null>(null);
const [historyError, setHistoryError] = useState<string | null>(null);
const [gitError, setGitError] = useState<string | null>(null);
```

**Métodos Clave**:
- `loadProjects()`: Obtiene lista de proyectos del API
- `searchSnippets()`: Consulta `GET /api/snippets/search`
- `searchHistory()`: Consulta `GET /api/history/search`
- `loadGitHistory()`: Consulta `GET /api/git/history`
- `loadDiff()`: Consulta `GET /api/git/diff/{commit_hash}`
- `formatFileSize(bytes)`: Convierte bytes a formato legible
- `formatDate(timestamp)`: Convierte timestamp Unix a fecha local
- `handleDownload(url)`: Inicia descarga del ZIP

#### Lógica de Cambio Automático: `page.tsx`
- **Ubicación**: `frontend/src/app/page.tsx` (líneas 400-415)
- **Mecanismo**: Detector de mensajes en el stream de respuesta

```typescript
if (data.text.includes("Ve a la pestaña 'Proyectos'")) {
    setActiveTab("projects");
}
```

**Trigger**: Message chunk que contiene exactamente la cadena `"Ve a la pestaña 'Proyectos'"`

---

### Backend (FastAPI/Python)

#### Endpoint: `GET /api/projects/list`
- **Ubicación**: `backend/routers/chat.py` (línea 197)
- **Autenticación**: Requiere token JWT válido
- **Respuesta**:

```json
{
  "projects": [
    {
      "filename": "nova_project_1_nombre.zip",
      "size": 52428,
      "created": 1713033600.123456,
      "download_url": "/api/download/nova_project_1_nombre.zip"
    }
  ]
}
```

**Implementación**:
```python
@router.get("/projects/list")
async def list_user_projects(current_user: User = Depends(get_current_user)):
    """
    Lista todos los proyectos ZIP disponibles para el usuario actual.
    """
    from pathlib import Path
    
    projects_dir = Path("data/projects")
    if not projects_dir.exists():
        return {"projects": []}
    
    # Buscar archivos ZIP del usuario
    user_projects = []
    for file_path in projects_dir.glob(f"nova_project_{current_user.id}_*.zip"):
        if file_path.is_file():
            stat = file_path.stat()
            user_projects.append({
                "filename": file_path.name,
                "size": stat.st_size,
                "created": stat.st_ctime,
                "download_url": f"/api/download/{file_path.name}"
            })
    
    return {"projects": user_projects}
```

**Filtrado**: Solo archivos ZIP nombrados como `nova_project_{user_id}_*.zip`

#### Endpoints nuevos (v11.1.2)

- `GET /api/snippets/search?query=...`
- `GET /api/history/search?query=...`
- `GET /api/git/history?limit=30&snapshots_only=true`
- `GET /api/git/diff/{commit_hash}`

---

#### Flow de Creación de Proyecto

1. **Usuario solicita proyecto** (chat)
   ```
   "Crea una aplicación web de lista de tareas en React"
   ```

2. **ChatService detecta intent = "PROJECT_BUILD"**
   - Ubicación: `backend/services/chat_service.py` línea ~213

3. **DeveloperAgent genera código**
   - Genera múltiples archivos (src/, package.json, etc.)
   - Realiza reintentos inteligentes en caso de fallos

4. **AuditorAgent valida**
   - Revisa estructura, dependencias y compilabilidad
   - Puede rechazar si hay problemas críticos

5. **ProjectManager empaqueta**
   - Crea ZIP con todos los archivos
   - Guarda en `data/projects/nova_project_{user_id}_timestamp.zip`

6. **ChatService envía respuesta**
   - Mensaje especial que incluye: `"Ve a la pestaña 'Proyectos'"`
   - Frontend detecta y cambia tab automáticamente

---

## Flujo de datos

```
Usuario → Chat Input
    ↓
ChatService._handle_project_build()
    ↓
DeveloperAgent.build_project()
    ↓
AuditorAgent.audit()
    ↓
ProjectManager.package_project()
    ↓
Guardar ZIP en data/projects/
    ↓
ChatService.yield() → "✅ Proyecto creado... Ve a la pestaña 'Proyectos'"
    ↓
Frontend detecta messageStream
    ↓
setActiveTab("projects")
    ↓
ProjectManager.loadProjects()
    ↓
GET /api/projects/list
    ↓
Mostrar entrada en interfaz
```

---

## Estructura de Archivos

```
data/
├── projects/
│   ├── nova_project_1_lista-tareas.zip
│   ├── nova_project_1_calculadora.zip
│   ├── nova_project_2_blog.zip
│   └── ...
├── tts_cache/
├── tts_voices/
├── nova_dataset/
└── nova_export/

backend/
├── routers/
│   └── chat.py           # Endpoint /projects/list
├── services/
│   └── chat_service.py   # Flow PROJECT_BUILD
├── agents/
│   ├── developer_agent.py
│   ├── auditor_agent.py
│   └── ...
└── core/
    └── project_manager.py

frontend/
├── src/
│   ├── components/
│   │   └── ProjectManager.tsx  # Nuevo componente
│   └── app/
│       └── page.tsx            # Lógica cambio tab
```

---

## Configuración

### Variables de Entorno

No requiere variables especiales, pero asegúrate de:
- `CORS_ORIGINS` incluye localhost:3000
- `ENVIRONMENT` configurado apropiadamente

### Permisos de Archivos

La carpeta `data/projects/` debe existir y ser escribible:
```bash
mkdir -p data/projects
chmod 755 data/projects
```

---

## Mejoras Futuras (Roadmap)

1. **Búsqueda y Filtrado**
   - Buscar por nombre de proyecto
   - Ordenar por fecha/tamaño

2. **Edición de Proyectos**
   - Previsualizador inline de código
   - Reenvío de proyectos para mejoras

3. **Compartir Proyectos**
   - Generar enlaces públicos
   - Control de acceso granular

4. **Estadísticas**
   - Gráfico de proyectos creados por día
   - Tamaño total de almacenamiento usado

5. **Limpieza Automática**
   - Archivar proyectos antiguos
   - Comprimir ZIP con niveles de compresión variable

6. **Versionado**
   - Historial de cambios en cada proyecto
   - Rollback a versiones anteriores

---

## Testing

### Test Manual

1. Abrir http://localhost:3000
2. Autenticarse
3. En chat: "Crea un botón interactivo simple en HTML/CSS/JS"
4. Esperar respuesta
5. Verificar que la tab cambia automáticamente a "Proyectos"
6. Verificar que el proyecto aparece en la lista
7. Descargar el ZIP
8. Verificar que el contenido es correcto

### Test Automatizado (Próximo)

```python
# test_project_manager.py
import requests
import json

def test_create_and_list_project():
    """Test completo del flujo PROJECT_BUILD"""
    
    # 1. Autenticarse
    token = authenticate_user()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Crear proyecto vía chat
    response = requests.post(
        "http://localhost:8000/api/query/stream",
        json={"query": "Crea una app de calculadora simple"},
        headers=headers,
        stream=True
    )
    
    # 3. Verificar mensaje "Ve a la pestaña"
    messages = parse_stream(response)
    assert any("Ve a la pestaña 'Proyectos'" in msg for msg in messages)
    
    # 4. Listar proyectos
    list_response = requests.get(
        "http://localhost:8000/api/projects/list",
        headers=headers
    )
    
    # 5. Verificar que el nuevo proyecto aparece
    projects = list_response.json()["projects"]
    assert len(projects) > 0
```

---

## Troubleshooting

### Problema: "Error al cargar proyectos"

**Causa 1**: Token expirado o inválido
```bash
# Solución: Volver a autenticarse
```

**Causa 2**: Carpeta `data/projects/` no existe
```bash
# Solución:
mkdir -p data/projects
```

**Causa 3**: Permisos insuficientes
```bash
# Solución:
chmod 755 data/projects
```

### Problema: El tab no cambia automáticamente

**Solución**: El mensaje debe contener exactamente:
```
"Ve a la pestaña 'Proyectos'"
```

Verificar en `backend/services/chat_service.py` línea ~213 que el mensaje sea correcto.

### Problema: ZIP descargado está vacío o corrupto

**Causa**: El `ProjectManager.package_project()` no capturó todos los archivos.

**Solución**:
1. Verificar en `backend/core/project_manager.py`
2. Revisar logs del backend
3. Verificar que `data/projects/` no está full de disco

---

## API Reference

### GET /api/projects/list

**Headers**:
```
Authorization: Bearer <token>
```

**Query Parameters**: Ninguno

**Response (200)**:
```json
{
  "projects": [
    {
      "filename": "nova_project_1_ejemplo.zip",
      "size": 102400,
      "created": 1713033600.5,
      "download_url": "/api/download/nova_project_1_ejemplo.zip"
    }
  ]
}
```

**Errores**:
- `401 Unauthorized`: Token inválido o expirado
- `403 Forbidden`: Usuario no tiene permiso

---

## Version History

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 11.1.2  | 2026-04-13 | Librería de snippets, historial semántico, Git history + diff drawer, UX overlay/Escape |
| 11.1.1  | 2026-04-13 | Implementación inicial, cambio automático de tab, metadatos completos |
| 11.1.0  | 2026-04-01 | Base del sistema de creación de proyectos |

---

**Última actualización**: 2026-04-13
