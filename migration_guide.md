# Guía de Migración de NOVA v11.9.5

Migrar NOVA es un proceso sencillo, pero como es un ecosistema que depende de motores externos (Python, Node, Ollama), no basta con solo copiar la carpeta. Aquí tienes los pasos exactos para llevarte todo tu progreso a otra computadora.

## 1. Copia de Archivos (La Carpeta Principal)
Copia la carpeta completa `AI-Research-System`. 

> [!IMPORTANT]
> No es necesario copiar la carpeta `.venv` ni `node_modules`, ya que es mejor generarlas de nuevo en la computadora de destino para asegurar compatibilidad con el hardware.

**Archivos Críticos que DEBES llevar contigo:**
- `knowledge.db`: Contiene la base de datos de conocimiento.
- `backend/data/`: Carpeta con los índices vectoriales (Memoria RAG).
- `control_center/nova_launcher.json`: Tu configuración personalizada del centro de control.

## 2. Preparación en la Nueva Computadora
Antes de iniciar, asegúrate de instalar:
1. **Python 3.11+** (Asegúrate de marcar "Add to PATH").
2. **Node.js** (LTS recomendado).
3. **Ollama**: Instálalo y asegúrate de que el comando `ollama` funcione en la terminal.

## 3. Rehidratación del Entorno
Una vez copiada la carpeta, abre una terminal dentro de `AI-Research-System` y ejecuta:

### A. Python (Backend)
```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

### B. Node (Frontend)
```bash
cd frontend
npm install
cd ..
```

### C. Ollama (Modelos)
NOVA intentará descargarlos, pero para ahorrar tiempo puedes hacerlo manualmente:
```bash
ollama pull qwen2.5:7b
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

## 4. Lanzamiento
Ejecuta el archivo `start_NOVA.bat` o inicia el servidor manualmente:
```bash
python control_center/launcher_server.py
```

## Preguntas Frecuentes de Migración

> [!TIP]
> **¿Puedo migrar los modelos de Ollama sin descargarlos de nuevo?**
> Sí. En Windows, copia la carpeta `%USERPROFILE%\.ollama` a la misma ubicación en la nueva PC. Esto te ahorrará GBs de descarga.

> [!CAUTION]
> **Hardware Diferente**: Si la nueva PC tiene menos RAM o una CPU diferente (ej. pasas de un Ryzen 7 a un Intel i5), recuerda ajustar el `OLLAMA_NUM_THREAD` en la pestaña de **Configuración** del Control Center para evitar ralentizaciones.
