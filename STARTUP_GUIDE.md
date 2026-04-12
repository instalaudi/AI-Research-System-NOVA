# Cómo Iniciar el Sistema

## Opción 1: Usando venv local (RECOMENDADO)
```bash
start_ai_system.bat
```

**Ventajas:**
- Aislado del resto del sistema
- Fácil de reinstalar sin afectar otros proyectos
- Automáticamente libera puertos 8000 y 3000
- Script actualizado para instalar dependencias cada vez

**Cómo funciona:**
1. Libera automáticamente puertos 8000 (backend) y 3000 (frontend)
2. Crea un venv local en `backend/venv/` (si no existe)
3. **Siempre actualiza las dependencias** de `requirements.txt`
4. Inicia backend en puerto 8000
5. Inicia frontend en puerto 3000 (después de 3 segundos)
6. Abre navegador automáticamente en http://localhost:3000

## Opción 2: Usando Python global
```bash
start_ai_system_global.bat
```

**Ventajas:**
- Más simple, sin necesidad de venv
- Usa el Python global que ya tiene TODO instalado
- Sin problemas de módulos faltantes
- También libera puertos automáticamente

**Cuándo usar:**
- Si tienes problemas con el venv
- Si prefieres evitar ambientes virtuales

---

## Si Aún Tienes Error "Puerto 8000 en uso"

### SOLUCIÓN 1: Ejecutar script de limpieza
```bash
limpiar_puertos.bat
```

Este script mata automáticamente cualquier proceso en puertos 8000 y 3000.

### SOLUCIÓN 2: Limpiar manualmente
```bash
# En PowerShell (como Admin) o CMD
netstat -ano | findstr ":8000"
taskkill /PID <PID> /F
```

---

## Si Aún Tienes Error de "slowapi"

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

