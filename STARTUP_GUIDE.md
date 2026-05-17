# Cómo Iniciar el Sistema (v11.4.2 - Swarm Edition)

## Opción 1: Arranque Total Automatizado (RECOMENDADO)
```bash
start_ai_system.bat
```

**Lo que NOVA hace por ti (v11.4.0):**
1. **Limpieza Forense**: Libera automáticamente los puertos 8000, 3000 y los puertos de motores 11434, 11435, 11436.
2. **Arranque del Enjambre**: Lanza el script `scripts/start_multi_engines.bat`.
3. **Warm-up de Motores**: Espera **20 segundos** para asegurar que los motores de Chat, Dev y Audit estén en RAM antes de iniciar el cerebro.
4. **Dashboard & Cerebro**: Inicia el Backend (8000), el Frontend (3000) y abre tu navegador listo para trabajar.

---

## Estructura de Motores Ollama (v11.4.0)

Para el máximo rendimiento en tu Ryzen 7, NOVA distribuye la carga así:

| Puerto | Agente / Función | Modelo Sugerido |
|--------|------------------|-----------------|
| **11434** | Chat & General | `qwen3:8b` |
| **11435** | Developer (Código)| `qwen2.5-coder:7b` |
| **11436** | Auditoría & Visión| `llava-llama3` |

---

### Crear un Proyecto

1. En el chat, escribe una solicitud de proyecto:
   ```
   Crea una aplicación web de lista de tareas en React con Tailwind CSS
   ```

2. NOVA automáticamente:
   - Genera el código usando el `DeveloperAgent`
   - Valida con el `AuditorAgent`
   - Empaqueta en un ZIP con el `ProjectManager`
   - **Cambia automáticamente a la pestaña "Proyectos"**

3. Ver tu proyecto en la lista:
   - Nombre formateado automáticamente
   - Tamaño en unidades legibles (KB, MB, etc.)
   - Fecha de creación en tu zona horaria local
   - Botón de descarga directa

### Descargar un Proyecto

1. Ve a la pestaña **"Proyectos"** en la interfaz
2. Busca el proyecto en la lista
3. Haz clic en el botón de **descargar** (icono Download)
4. El archivo ZIP se guardará en tu carpeta de descargas

### Acceder a Proyectos Anteriores

- Todos tus proyectos siempre están disponibles en la pestaña "Proyectos"
- No necesitas crear uno nuevo para acceder a los anteriores
- Los proyectos se almacenan en `data/projects/` del servidor

### Librería, Historial y Git (nuevo)

- **Librería**: Busca snippets guardados por texto y reutilízalos directo en el chat.
- **Historial**: Búsqueda semántica en código histórico con `/api/history/search`.
- **Git**: Visualiza commits automáticos locales y abre diff por commit.
- **Drawer de Diff**: Se cierra con botón, clic fuera (overlay) o tecla `Escape`.

---

## Si Aún Tienes Error \"Puerto 8000 en uso\"

### SOLUCIÓN 1: Ejecutar script de limpieza
```bash
limpiar_puertos.bat
```

Este script mata automáticamente cualquier proceso en puertos 8000 y 3000.

### SOLUCIÓN 2: Limpiar manualmente
```bash
# En PowerShell (como Admin) o CMD
netstat -ano | findstr \":8000\"
taskkill /PID <PID> /F
```

---

## Si Aún Tienes Error de \"slowapi\"

### SOLUCIÓN 1: El script lo instala automáticamente
El script `start_ai_system.bat` ahora **SIEMPRE** ejecuta `pip install -r requirements.txt`, así que slowapi será instalado automáticamente.

### SOLUCIÓN 2: Limpiar y reinstalar venv manualmente
```bash
cd backend
rmdir /S venv
cd ..
start_ai_system.bat
```

### SOLUCIÓN 3: Verificar instalación manual

```bash
# Con Python global
python -m pip list | findstr slowapi

# Con venv local (primero activar)
cd backend
venv\Scripts\activate
pip list | findstr slowapi
```

---

## Novedades de v11.1.2

✨ **Gestor de Activos + Git Local**
- Interface moderna para gestionar proyectos generados
- Cambio automático de pestaña cuando creas un proyecto
- Metadatos completos (tamaño, fecha, nombre formateado)
- Descarga flexible en lugar de automática
- Librería de snippets reutilizables
- Historial semántico de código
- Historial de commits Git + visualización de diffs

Debe mostrar: `slowapi 0.1.9`

---

## URLs de Acceso

Una vez iniciado:
- **Frontend**: http://localhost:3000
- **API**: http://localhost:8000
- **Health Check**: http://127.0.0.1:8000/health

---

## Archivos Importantes

| Archivo | Propósito |
|---------|-----------|
| `start_ai_system.bat` | Script principal (con venv) |
| `start_ai_system_global.bat` | Script alternativo (Python global) |
| `limpiar_puertos.bat` | Limpia manualmente los puertos |
| `backend/.env` | Configuración del API (API_KEY, etc) |
| `backend/requirements.txt` | Dependencias Python |
| `frontend/package.json` | Dependencias Node.js |

---

## Troubleshooting

### Error: "Python no esta instalado"
- Descarga Python desde https://www.python.org/
- Asegúrate de marcar "Add Python to PATH"

### Error: "Node.js no esta instalado"
- Descarga Node.js desde https://nodejs.org/
- Requiere Node 16+

### Error: "ModuleNotFoundError: No module named 'slowapi'"
- Ejecutar `start_ai_system.bat` de nuevo
- El script instalará slowapi automáticamente

### Error: "[Errno 10048] error while attempting to bind"
- Significa que el puerto 8000 está en uso
- Ejecutar `limpiar_puertos.bat`
- O esperar 30 segundos y reintentar

### Backend lento o no responde
- Verificar que Ollama esté corriendo en `http://localhost:11434`
- Asegúrate de haber descargado el modelo: `ollama pull deepseek-r1:8b`
- Revisar `.env` que `LLM_MODEL_NAME` sea `deepseek-r1:8b`

