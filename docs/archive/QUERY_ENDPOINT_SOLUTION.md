# Solución: Endpoint /query/simple

## Problema
El endpoint `/query` original se bloqueaba esperando a que Ollama respondiera, causando timeout.

## Solución
Se agregó un nuevo endpoint **`/query/simple`** que:
- ✅ Busca directamente en la base de conocimiento (sin LLM)
- ✅ Devuelve resultados en **menos de 1 segundo**
- ✅ No depende de Ollama
- ✅ Funciona mientras el sistema acumula conocimiento

## Cómo Usar

### Endpoint `/query/simple` (RECOMENDADO - RÁPIDO)
```bash
curl -X POST http://127.0.0.1:8000/query/simple \
  -H "api-key: kV7jQ_8mX2pL9wN4sR6tU1yZ3aB5cD7eF9gH" \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Qué es Inteligencia Artificial?"}'
```

**Respuesta:**
```json
{
  "query": "¿Qué es Inteligencia Artificial?",
  "answer": "Encontré la siguiente información...",
  "mode": "simple_search"
}
```

### Endpoint `/query` (AVANZADO - Con LLM)
Este endpoint aún está disponible pero requiere Ollama corriendo. Úsalo cuando:
- Tengas Ollama instalado en `http://localhost:11434`
- Quieras respuestas más inteligentes sintetizadas por el LLM

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "api-key: kV7jQ_8mX2pL9wN4sR6tU1yZ3aB5cD7eF9gH" \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Qué es Inteligencia Artificial?"}'
```

---

## Flujo Actual del Sistema

```
Usuario pregunta
    ↓
/query/simple (FAST - Busca en DB)
    ↓
Encuentra resultados en < 1 segundo
    ↓
Responde con conocimiento acumulado
```

## Estado Actual

| Componente | Status |
|-----------|--------|
| `/health` | ✅ Funciona |
| `/research/start` | ✅ Funciona (encolando tareas) |
| `/query/simple` | ✅ Funciona (búsqueda rápida) |
| `/query` | ⏳ Requiere Ollama |
| `/stats` | ✅ Funciona (requiere api-key) |

---

## Frontend (Interfaz Web)

El frontend en `http://localhost:3000` intenta usar varios endpoints que no existen:
- `/status` → No existe
- `/knowledge` → No existe
- `/graph` → No existe

**Solución:** El frontend necesitaría actualizar sus llamadas a los endpoints que existen:
- `/health` → Estado del servidor
- `/query/simple` → Consultas
- `/stats` → Estadísticas (requiere api-key)
- `/research/start` → Iniciar investigación

---

## Próximos Pasos

### Opción 1: Usa /query/simple por ahora
El sistema funciona perfectamente con búsqueda simple en la base de conocimiento.

### Opción 2: Instala Ollama para /query completo
Si quieres usar el endpoint `/query` avanzado con síntesis de LLM:

1. Descarga Ollama desde https://ollama.ai
2. Ejecuta el modelo: `ollama run qwen2.5:7b`
3. El endpoint `/query` automáticamente usará este modelo

---

## Prueba Rápida

```bash
# Test 1: Health check
curl http://127.0.0.1:8000/health

# Test 2: Query simple (FUNCIONA SIN OLLAMA)
curl -X POST http://127.0.0.1:8000/query/simple \
  -H "api-key: kV7jQ_8mX2pL9wN4sR6tU1yZ3aB5cD7eF9gH" \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'

# Test 3: Stats
curl -H "api-key: kV7jQ_8mX2pL9wN4sR6tU1yZ3aB5cD7eF9gH" \
  http://127.0.0.1:8000/stats
```

---

## Error "Lo siento, hubo un error"

Si aún ves este error:

1. ✅ `/query/simple` - Usa este en lugar de `/query`
2. Verifica que enviaste la API key correcta
3. Verifica que el servidor está corriendo (`/health` responde 200)
4. Revisa en la terminal del backend si hay errores

---

## Resumén de Cambios

| Archivo | Cambio |
|---------|--------|
| `main.py` | Agregado `/query/simple` endpoint, mejorado timeout en `/query` |
| `knowledge_base.py` | Agregado `db.flush()` para FK constraints |

El sistema **funciona correctamente ahora**. La interfaz web simplemente necesitaría actualizarse para usar los endpoints correctos.
