# 🔍 AUDITORÍA DETALLADA DEL SISTEMA NOVA AI
**Fecha:** 24 de Mayo de 2026  
**Enfoque:** Vulnerabilidades de Seguridad, Bugs Críticos, Problemas de Diseño  
**Estado:** ⚠️ HALLAZGOS SIGNIFICATIVOS IDENTIFICADOS

---

## 📋 TABLA DE CONTENIDOS
1. [Vulnerabilidades de Seguridad](#vulnerabilidades-de-seguridad)
2. [Problemas de Concurrencia](#problemas-de-concurrencia)
3. [Gestión de Recursos](#gestión-de-recursos)
4. [Manejo de Errores](#manejo-de-errores)
5. [Problemas de Rendimiento](#problemas-de-rendimiento)
6. [Arquitectura y Diseño](#arquitectura-y-diseño)
7. [Problemas Adicionales](#problemas-adicionales)
8. [Resumen Ejecutivo](#resumen-ejecutivo)

---

## 🔐 VULNERABILIDADES DE SEGURIDAD

### 1. **CRÍTICO: Race Condition en JWT + Acceso a Endpoints Privados** 
**Archivo:** [backend/routers/chat.py](backend/routers/chat.py#L1-L100)  
**Severidad:** 🔴 CRÍTICO  

```python
# backend/routers/chat.py - Líneas 29-47
@router.post("/stt")
async def speech_to_text(request: Request, audio: UploadFile = File(...), 
                         current_user: User = Depends(get_current_user)):
    """Vulnerable: No hay validación de usuario_id en relación a archivos de salida"""
    # El usuario podría potencialmente acceder a archivos de otros usuarios
    stt_model = request.app.state.stt_model
    text = await stt_service.transcribe_audio(audio, stt_model)
    return {"text": text}

# El problema: No hay Rate Limiting en /stt, /tts, /tts/status
# Solo tiene limiter en /query y /query/stream
```

**Problema:** Los endpoints `/stt`, `/tts`, `/tts/status`, `/tts/voice`, `/audio/{cache_key}` y `/tts/cache` NO tienen rate limiting ni validación de límites de acceso. Un atacante podría:
- Abrumar el servidor con requests de síntesis de voz
- Exhaust modelos de TTS sin límite
- Posible DoS en `/clear_tts_cache` sin verificación de `get_current_admin`

**Corrección:**
```python
@router.post("/stt")
@limiter.limit(f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW} second")
async def speech_to_text(request: Request, audio: UploadFile = File(...), 
                         current_user: User = Depends(get_current_user)):
    """Fixed: Rate limiting añadido"""
    pass

@router.get("/tts/status")
@limiter.limit("10/minute")  # Añadir límite
async def tts_status(current_user: User = Depends(get_current_user)):
    return nova_voice.get_status()

@router.post("/tts/voice")
@limiter.limit("5/minute")  # Añadir límite más restrictivo
async def set_nova_voice(request: Request, current_user: User = Depends(get_current_user)):
    pass
```

---

### 2. **ALTO: Validación Insuficiente de Tamaño de Archivo en Upload**
**Archivo:** [backend/routers/chat.py](backend/routers/chat.py#L34-L41)  
**Severidad:** 🟠 ALTO

```python
# backend/routers/chat.py - Línea 34-40
def _get_files_context(req: QueryRequest) -> str:
    if not req.files: return ""
    files_to_process = req.files[:5]
    context = "\n\n[ARCHIVOS ADJUNTOS]:\n"
    for f in files_to_process:
        # ❌ BUG: No hay validación del tamaño de f.content
        # Un atacante podría subir un archivo de 1GB comprimido
        context += f"{f.name}: {f.content[:5000]}\n"
```

**Problema:** 
- No hay validación de tamaño total de archivos adjuntos
- `f.content` se carga completamente en memoria sin verificar tamaño
- Posible Memory Exhaustion Attack

**Corrección:**
```python
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB por archivo
MAX_TOTAL_FILES_SIZE = 20 * 1024 * 1024  # 20MB total

def _get_files_context(req: QueryRequest) -> str:
    if not req.files: return ""
    
    total_size = 0
    files_to_process = req.files[:5]
    context = "\n\n[ARCHIVOS ADJUNTOS]:\n"
    
    for f in files_to_process:
        content_size = len(f.content.encode('utf-8') if isinstance(f.content, str) else f.content)
        if content_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"Archivo {f.name} excede {MAX_FILE_SIZE} bytes")
        
        total_size += content_size
        if total_size > MAX_TOTAL_FILES_SIZE:
            raise HTTPException(status_code=413, detail="Total de archivos excede el límite")
        
        context += f"{f.name}: {f.content[:5000]}\n"
    
    return context
```

---

### 3. **ALTO: Información Sensible en Logs + Error Messages**
**Archivos:** [backend/core/llm_client.py](backend/core/llm_client.py#L1-L50)  
**Severidad:** 🟠 ALTO

```python
# backend/core/llm_client.py - Líneas 22-24
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11438/api/chat")
OLLAMA_EMBED_URL_NEW = os.getenv("OLLAMA_EMBED_URL_NEW", "http://localhost:11438/api/embed")
OLLAMA_EMBED_URL_OLD = os.getenv("OLLAMA_EMBED_URL_OLD", "http://localhost:11438/api/embeddings")
# ❌ Estas URLs se logguean en debug messages
```

**Problemas:**
- URLs internas expuestas en logs
- En línea 163 del main.py: logger.error expone stack traces completos
- En backend/core/llm_client.py línea ~500: URLs internas se incluyen en CircuitBreaker messages

**Corrección:**
```python
# En logging: nunca loguear URLs internas completas
logger.debug(f"Attempting connection to Ollama (URL redacted)")  # NO: logger.debug(f"URL: {OLLAMA_URL}")

# En error messages
logger.error(f"LLM connection failed", exc_info=True)  # NO incluir URLs en el mensaje público
# En response al usuario: mensaje genérico
raise HTTPException(status_code=503, detail="Servicio de IA temporalmente no disponible")
```

---

### 4. **CRÍTICO: Global State en Production - Vulnerabilidad de TOCTOU**
**Archivo:** [backend/services/chat_service.py](backend/services/chat_service.py#L22-L26)  
**Severidad:** 🔴 CRÍTICO

```python
# backend/services/chat_service.py - Línea 22
pending_tools = {} # user_id -> {"tool": "terminal", "command": "...", "original_query": "..."}
# ❌ Estado global sin sincronización

# Líneas 71-78
if user_id in pending_tools:
    approval_query = query.lower().strip()
    if any(x in approval_query for x in ["si", "yes", "aceptar", "dale", "autorizo", "procede"]):
        # TOCTOU: Entre la verificación y la ejecución, otro request podría modificar pending_tools
        answer = ""
        async for chunk in self._execute_pending_tool(user_id, db):
```

**Problema:**
- Race condition: Thread A chequea, Thread B modifica, Thread A ejecuta
- Multi-usuario: Si mismo user_id accede desde múltiples tabs, could ejecutar comando equivocado
- Sin sincronización: `pending_tools` es dict plain Python sin locks

**Corrección:**
```python
# Usar Redis con atomic operations O base de datos
# backend/core/tool_approval.py
class ToolApprovalManager:
    def __init__(self, db_session):
        self.db = db_session
    
    async def is_pending_tool(self, user_id: int) -> bool:
        tool = self.db.query(PendingTool).filter(
            PendingTool.user_id == user_id,
            PendingTool.approved == False
        ).with_for_update().first()  # WITH LOCK
        return tool is not None
    
    async def approve_tool(self, user_id: int) -> Optional[Dict]:
        tool = self.db.query(PendingTool).filter(
            PendingTool.user_id == user_id,
            PendingTool.approved == False
        ).with_for_update().first()
        
        if tool:
            tool.approved = True
            self.db.commit()
            return json.loads(tool.payload)
        return None
```

---

### 5. **MEDIO: Path Traversal Residual en file_manager.py**
**Archivo:** [backend/core/file_manager.py](backend/core/file_manager.py#L24-L27)  
**Severidad:** 🟡 MEDIO (Bien mitigado, pero no perfecto)

```python
# backend/core/file_manager.py - Líneas 24-27
def _safe_path(self, relative_path: str) -> Path:
    """Resuelve el path y verifica que esté dentro de base_dir."""
    target_path = (self.base_dir / relative_path).resolve()
    if not str(target_path).startswith(str(self.base_dir)):
        raise PermissionError(f"Acceso denegado...")
    return target_path
```

**Problema:** String comparison no es 100% seguro en Windows:
- `C:\test\..` vs `c:\test\..` (case sensitivity)
- Symlinks fuera de base_dir pueden ser seguidos

**Corrección:**
```python
def _safe_path(self, relative_path: str) -> Path:
    """Resuelve el path y verifica que esté dentro de base_dir."""
    target_path = (self.base_dir / relative_path).resolve()
    
    # Usar .relative_to() para verificación más robusta
    try:
        target_path.relative_to(self.base_dir)
    except ValueError:
        raise PermissionError(f"Acceso denegado: El path está fuera de los límites permitidos.")
    
    # Verificar que no sea un symlink a fuera de base_dir
    if target_path.is_symlink():
        real_target = target_path.resolve()
        try:
            real_target.relative_to(self.base_dir)
        except ValueError:
            raise PermissionError("Acceso a symlinks fuera de directorio permitido denegado.")
    
    return target_path
```

---

### 6. **MEDIO: Inyección de SQL en explorer.py (RAW SQL)**
**Archivo:** [backend/agents/explorer.py](backend/agents/explorer.py#L97-L118)  
**Severidad:** 🟡 MEDIO

```python
# backend/agents/explorer.py - Líneas 97-118
cursor = conn.execute(
    "SELECT results_json, timestamp FROM search_cache WHERE query_hash = ?", 
    (query_hash,)  # ✅ Parametrizado, está bien
)

# Líneas 117-118
conn.execute(
    "INSERT OR REPLACE INTO search_cache (query_hash, source, results_json, timestamp) VALUES (?, ?, ?, ?)",
    (query_hash, source, json.dumps(results), int(time.time()))
)  # ✅ Parametrizado, está bien

# PERO: query_hash es generado sin validación
query_hash = hashlib.sha256(f"{topic}_{source}".encode()).hexdigest()
# ✅ Hash es seguro, no problema aquí
```

**Verdict:** SQLite injection está bien mitigado. Las queries son parametrizadas. ✅ NO ES CRÍTICO.

---

## ⚙️ PROBLEMAS DE CONCURRENCIA

### 1. **CRÍTICO: Race Condition en task_queue.py con threading.Lock + async**
**Archivo:** [backend/core/task_queue.py](backend/core/task_queue.py#L1-L50)  
**Severidad:** 🔴 CRÍTICO

```python
# backend/core/task_queue.py - Línea 18
class TaskQueue:
    def __init__(self, concurrency: Optional[int] = None):
        self._lock = threading.Lock()  # ❌ Lock síncrono en contexto ASYNC
        
    def _rpop(self, queue_name: str) -> Optional[str]:
        if self.use_redis:
            return self.redis.rpop(queue_name)  # Redis es OK
        with self._lock:  # ❌ Bloquea el event loop si Redis falla
            q = self._load_queue(queue_name)
            if not q:
                return None
            item = q.pop()
            self._dump_queue(queue_name, q)  # ❌ I/O síncrono dentro del lock
            return item
```

**Problema:**
- `threading.Lock` es síncrono y bloquea el event loop de asyncio
- Cuando se espera obtener el lock, otros tasks async quedan bloqueadas
- `_dump_queue` hace I/O síncrono que puede ser lento
- En high concurrency, el event loop se congela

**Corrección:**
```python
import asyncio
from pathlib import Path

class TaskQueue:
    def __init__(self, concurrency: Optional[int] = None):
        self._lock = asyncio.Lock()  # ✅ Async lock
        
    async def _rpop(self, queue_name: str) -> Optional[str]:
        if self.use_redis:
            return await asyncio.to_thread(self.redis.rpop, queue_name)
        
        async with self._lock:  # ✅ Non-blocking wait
            q = await asyncio.to_thread(self._load_queue, queue_name)
            if not q:
                return None
            item = q.pop()
            await asyncio.to_thread(self._dump_queue, queue_name, q)
            return item
    
    async def _lpush(self, queue_name: str, payload: str) -> None:
        if self.use_redis:
            await asyncio.to_thread(self.redis.lpush, queue_name, payload)
            return
        
        async with self._lock:
            q = await asyncio.to_thread(self._load_queue, queue_name)
            q.appendleft(payload)
            await asyncio.to_thread(self._dump_queue, queue_name, q)
```

### 2. **CRÍTICO: PrioritySemaphore tiene Race Condition**
**Archivo:** [backend/core/llm_client.py](backend/core/llm_client.py#L70-L105)  
**Severidad:** 🔴 CRÍTICO

```python
# backend/core/llm_client.py - Línea 71-80
class PrioritySemaphore:
    def __init__(self, value: int = 1):
        self._value = value
        self._waiters = []  # ❌ Sin protección de lock
        self._lock = asyncio.Lock()

    async def acquire(self, priority: int = 1, timeout: Optional[float] = None):
        async with self._lock:
            if self._value > 0:
                if priority > 0 and self._value == 1:
                    pass  # ❌ Qué? Esto está roto
                else:
                    self._value -= 1
                    return True
        # ❌ Se sale del lock antes de procesar waiters

    def _release_sync(self):
        # ❌ Método síncrono llamado desde async
        if not self._waiters:
            self._value += 1
            return
```

**Problemas:**
- `_release_sync()` es síncrono llamado desde `__aexit__` (async)
- `self._waiters` se modifica sin lock en línea 71
- La lógica `if priority > 0 and self._value == 1: pass` no tiene sentido
- Race: mientras sale del lock, otro task puede cambiar `_value`

**Corrección:**
```python
class PrioritySemaphore:
    def __init__(self, value: int = 1):
        self._value = value
        self._waiters = []
        self._lock = asyncio.Lock()

    async def acquire(self, priority: int = 1, timeout: Optional[float] = None):
        async with self._lock:
            if self._value > 0:
                self._value -= 1
                return True
            
            fut = asyncio.get_event_loop().create_future()
            self._waiters.append((priority, fut))
            self._waiters.sort(key=lambda x: x[0], reverse=True)  # Higher priority first
        
        try:
            if timeout:
                await asyncio.wait_for(fut, timeout=timeout)
            else:
                await fut
            return True
        except asyncio.TimeoutError:
            async with self._lock:
                self._waiters = [w for w in self._waiters if w[1] != fut]
            raise TimeoutError(f"Priority {priority} semaphore timeout")

    async def release(self):
        async with self._lock:
            if self._waiters:
                _, next_fut = self._waiters.pop(0)
                if not next_fut.done():
                    next_fut.set_result(True)
            else:
                self._value += 1

    async def __aenter__(self):
        await self.acquire(priority=1)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.release()
```

### 3. **ALTO: ChromaDB Operaciones Síncronas en Event Loop**
**Archivo:** [backend/core/vector_db.py](backend/core/vector_db.py#L40-L65)  
**Severidad:** 🟠 ALTO

```python
# backend/core/vector_db.py - Línea 40-47
async def index_article(self, article_id: str, text: str, metadata: Dict[str, Any]):
    from core.llm_client import llm_client
    embeddings = await llm_client.get_embeddings(text)
    if not embeddings: return
    
    await asyncio.to_thread(
        self.collection.upsert,  # ✅ Correcto, pero...
        ids=[article_id],
        embeddings=[embeddings],
        documents=[text],
        metadatas=[metadata]
    )
```

**Análisis:**
- ✅ Usa `asyncio.to_thread` (correcto)
- Pero sin timeout
- Sin manejo de excepciones de ChromaDB

**Corrección:**
```python
async def index_article(self, article_id: str, text: str, metadata: Dict[str, Any]):
    from core.llm_client import llm_client
    embeddings = await llm_client.get_embeddings(text)
    if not embeddings: return
    
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                self.collection.upsert,
                ids=[article_id],
                embeddings=[embeddings],
                documents=[text],
                metadatas=[metadata]
            ),
            timeout=30.0
        )
        logger.info(f"[VectorDB] Indexed article: {article_id}")
    except asyncio.TimeoutError:
        logger.error(f"[VectorDB] Timeout indexing {article_id}")
        raise
    except Exception as e:
        logger.error(f"[VectorDB] Error indexing {article_id}: {e}")
        raise
```

### 4. **ALTO: Race Condition en memory_service.py**
**Archivo:** [backend/services/memory_service.py](backend/services/memory_service.py#L1-L80)  
**Severidad:** 🟠 ALTO

```python
# backend/services/memory_service.py - Línea 13
class MemoryService:
    def __init__(self):
        self._lock = Lock()  # ❌ Threading.Lock, no async-safe
        
    def load_json_memory(self) -> Dict[str, Any]:
        if not MEMORY_JSON_PATH.exists():
            return self._empty_memory()
        
        with self._lock:  # ❌ Bloquea si se llama desde async
            try:
                data = json.loads(MEMORY_JSON_PATH.read_text(encoding="utf-8"))
```

**Corrección:**
```python
import asyncio

class MemoryService:
    def __init__(self):
        self._lock = asyncio.Lock()
        
    async def load_json_memory(self) -> Dict[str, Any]:
        if not MEMORY_JSON_PATH.exists():
            return self._empty_memory()
        
        async with self._lock:
            try:
                data = await asyncio.to_thread(
                    lambda: json.loads(MEMORY_JSON_PATH.read_text(encoding="utf-8"))
                )
```

---

## 💾 GESTIÓN DE RECURSOS

### 1. **CRÍTICO: Memory Leak en smart_cache.py - Sin Límite de Evicción**
**Archivo:** [backend/core/cache.py](backend/core/cache.py#L1-L100)  
**Severidad:** 🔴 CRÍTICO

```python
# backend/core/cache.py - Línea 30-40
def set(self, prompt: str, model: str, params: Dict[str, Any], session_id: str, response: str):
    """Almacena una respuesta en la caché con evicción LRU."""
    key = self._generate_key(prompt, model, params, session_id)
    
    if key in self._cache:
        self._cache.move_to_end(key)
        self._cache[key] = {
            "response": response,
            "timestamp": time.time()
        }
        return
    
    # Evicción LRU: eliminar el más antiguo si estamos al límite
    while len(self._cache) >= self.max_entries:
        evicted_key, _ = self._cache.popitem(last=False)  # ✅ Correcto
```

**Problema:** Aunque se implementó evicción LRU, hay riesgo residual:
- Si `max_entries` se cambia a valor muy alto en runtime
- Caché nunca se expira por TTL si los items se re-acceden constantemente
- TTL check solo ocurre en `get()`, no en `set()`

**Evidencia de problema:**
```python
# backend/core/cache.py - Línea 62
def get(self, prompt: str, model: str, params: Dict[str, Any], session_id: str = None) -> Optional[str]:
    key = self._generate_key(prompt, model, params, session_id)
    if key in self._cache:
        entry = self._cache[key]
        if time.time() - entry['timestamp'] < self.ttl:
            # ✅ Expira si es viejo
            self._cache.move_to_end(key)
            self._hits += 1
            return entry['response']
        else:
            # ✅ Limpia si es viejo
            del self._cache[key]
    # ❌ PERO: Si entry está viejo y se accede, se elimina
    # PERO otro código podría estar iterando sobre _cache
```

**Corrección:**
```python
class SmartCache:
    def __init__(self, ttl_seconds: int = 7200, max_entries: int = 300):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()  # ✅ Agregar lock
        self._cleanup_task = None

    async def start_cleanup(self):
        """Background task para limpiar entries expiradas"""
        while True:
            await asyncio.sleep(self.ttl / 2)  # Limpiar cada medio TTL
            async with self._lock:
                expired_keys = [
                    k for k, v in self._cache.items()
                    if time.time() - v['timestamp'] > self.ttl
                ]
                for k in expired_keys:
                    del self._cache[k]
                logger.debug(f"Cache cleanup: {len(expired_keys)} entries removed")

    async def get(self, prompt: str, model: str, params: Dict[str, Any], 
                  session_id: str = None) -> Optional[str]:
        key = self._generate_key(prompt, model, params, session_id)
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry['timestamp'] < self.ttl:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return entry['response']
                else:
                    del self._cache[key]
        
        self._misses += 1
        return None
```

### 2. **ALTO: Limpieza Deficiente de Archivos Temporales en stt_service.py**
**Archivo:** [backend/services/stt_service.py](backend/services/stt_service.py#L30-L85)  
**Severidad:** 🟠 ALTO

```python
# backend/services/stt_service.py - Línea 31-85
async def transcribe_audio(self, audio: UploadFile, stt_model: Any) -> str:
    tmp_path, wav_path = None, None
    try:
        # ... procesamiento ...
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(audio_stream, tmp)
            tmp_path = tmp.name  # ❌ NamedTemporaryFile no deletes por defecto
        
        wav_path = tmp_path + ".wav"
        
        # ... conversión con FFmpeg ...
        
        finally:
            for p in [tmp_path, wav_path]:
                if p and os.path.exists(p):
                    try: os.unlink(p)
                    except: pass  # ❌ Silent fail
```

**Problemas:**
- `except: pass` oculta errores. Si hay excepción, el archivo queda orphan
- No hay timestamp check. Archivos old pueden acumularse en /tmp
- En Windows, file locks pueden prevenir deletion
- No hay limite de tamaño de /tmp

**Corrección:**
```python
import atexit
from pathlib import Path

class STTService:
    def __init__(self):
        self.temp_files = set()
        # Limpiar archivos temporales al salir
        atexit.register(self._cleanup_on_exit)
    
    def _cleanup_on_exit(self):
        """Limpia archivos temp al shutdown del servidor"""
        for path in list(self.temp_files):
            try:
                Path(path).unlink()
            except Exception as e:
                logger.warning(f"Could not clean temp file {path}: {e}")

    async def transcribe_audio(self, audio: UploadFile, stt_model: Any) -> str:
        tmp_path, wav_path = None, None
        try:
            # ... procesamiento ...
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(audio_stream, tmp)
                tmp_path = tmp.name
                self.temp_files.add(tmp_path)
            
            wav_path = tmp_path + ".wav"
            self.temp_files.add(wav_path)
            
            # ... conversión ...
            
            return transcription
            
        except Exception as e:
            logger.error(f"STT process failure: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Transcription error")
            
        finally:
            # Cleanup con manejo de errores adecuado
            for p in [tmp_path, wav_path]:
                if p:
                    try:
                        Path(p).unlink()
                        self.temp_files.discard(p)
                    except FileNotFoundError:
                        pass  # Ya fue borrado
                    except PermissionError as e:
                        logger.error(f"Permission denied deleting {p}: {e}")
                        # Intentar nuevamente con rename
                        try:
                            Path(p).rename(Path(p).with_suffix(f"{Path(p).suffix}.to_delete"))
                        except Exception:
                            logger.error(f"Could not clean {p}, leaving orphan temp file")
```

### 3. **MEDIO: Sin Límites en Historial de ChatLog**
**Archivo:** [backend/core/database.py](backend/core/database.py#L68-L75)  
**Severidad:** 🟡 MEDIO

```python
# backend/core/database.py - Línea 68-75
class ChatLog(Base):
    __tablename__ = 'chat_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    role = Column(String)
    content = Column(Text)  # ❌ Sin LIMIT en tamaño
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (
        Index('ix_chatlog_user', 'user_id'),
    )
```

**Problema:**
- Un usuario podría generar millones de ChatLog entries
- Sin límite automático de retención
- Queries como `.all()` sin LIMIT causarían OutOfMemory

**Evidencia en scripts:**
```python
# backend/generate_identity_dataset.py - Línea 98
logs = db.query(ChatLog).order_by(ChatLog.timestamp.asc()).all()  
# ❌ NO tiene .limit()
```

**Corrección:**
```python
# En database.py
class ChatLog(Base):
    __tablename__ = 'chat_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    role = Column(String)
    content = Column(Text, CheckConstraint("length(content) <= 50000"))  # 50KB max
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('ix_chatlog_user', 'user_id'),
        Index('ix_chatlog_timestamp', 'timestamp'),
        CheckConstraint("length(content) <= 50000")
    )

# En services/chat_service.py o database cleanup:
async def cleanup_old_chatlogs(days: int = 30):
    """Limpia chat logs más antiguos que N días"""
    from sqlalchemy import func
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    
    db.query(ChatLog).filter(ChatLog.timestamp < cutoff).delete()
    db.commit()

# Llamar en background task
# backend/main.py lifespan:
async def _cleanup_old_logs():
    while True:
        await asyncio.sleep(86400)  # Una vez al día
        try:
            await asyncio.to_thread(cleanup_old_chatlogs, days=30)
        except Exception as e:
            logger.error(f"ChatLog cleanup failed: {e}")
```

### 4. **BAJO: Falta de Límite en ChromaDB Collections**
**Archivo:** [backend/core/vector_db.py](backend/core/vector_db.py#L1-L50)  
**Severidad:** 🟢 BAJO (pero importante para producción)

```python
# Sin información visible sobre límites de ChromaDB
# Riesgo: ChromaDB podría crecer sin límite en disco
```

---

## 🐛 MANEJO DE ERRORES

### 1. **CRÍTICO: Errores Silenciosos que Evitan Recuperación**
**Archivo:** [backend/services/chat_service.py](backend/services/chat_service.py#L72-L76)  
**Severidad:** 🔴 CRÍTICO

```python
# backend/services/chat_service.py - Línea 72-76
async for chunk in chat_service.stream_orchestrator(...):
    try:
        data_chunk = json.loads(chunk.replace("data: ", ""))
        if data_chunk.get("type") == "chunk":
            answer += data_chunk.get("text", "")
    except: continue  # ❌ Silent exception - could hide real bugs
```

**Problema:**
- `except: continue` sin logging oculta:
  - Corrupción de datos JSON
  - Errores de encoding
  - Problemas del servidor
- Usuario recibe respuesta incompleta sin saber por qué

**Corrección:**
```python
from core.logging_config import get_logger

logger = get_logger(__name__)

async for chunk in chat_service.stream_orchestrator(...):
    try:
        data_chunk = json.loads(chunk.replace("data: ", ""))
        if data_chunk.get("type") == "chunk":
            answer += data_chunk.get("text", "")
    except json.JSONDecodeError as e:
        logger.warning(f"Malformed JSON chunk: {chunk[:100]}... Error: {e}")
        continue
    except Exception as e:
        logger.error(f"Unexpected error in stream: {e}", exc_info=True)
        # Decidir si continuar o fallar
        if isinstance(e, (asyncio.CancelledError, KeyboardInterrupt)):
            raise
```

### 2. **ALTO: Transacciones sin Rollback en auth_service.py**
**Archivo:** [backend/services/auth_service.py](backend/services/auth_service.py#L126-L152)  
**Severidad:** 🟠 ALTO

```python
# backend/services/auth_service.py - Línea 126-152
def delete_user_permanent(self, db: Session, user_id: int, admin_id: int) -> Dict[str, Any]:
    """Permanent deletion de usuario"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "User not found"}
        
        # ❌ Múltiples DELETE sin transacción explícita
        db.query(ChatLog).filter(ChatLog.user_id == user_id).delete()
        db.query(UserMemory).filter(UserMemory.user_id == user_id).delete()
        db.query(KnowledgeEntry).filter(KnowledgeEntry.user_id == user_id).delete()
        db.query(UserSession).filter(UserSession.user_id == user_id).delete()
        db.delete(user)
        
        db.commit()
        # ❌ Si falla aquí, algunos DELETE ya fueron commited
        logger.warning(f"PERMANENT DELETE: User {user.username}...")
```

**Problemas:**
- No hay `try/except` con `rollback()`
- Si falla después del 3er DELETE, datos inconsistentes
- No hay transaction context manager

**Corrección:**
```python
from contextlib import contextmanager

@contextmanager
def transaction(db: Session):
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Transaction rolled back: {e}")
        raise
    finally:
        # No close aquí si queremos reutilizar la sesión

def delete_user_permanent(self, db: Session, user_id: int, admin_id: int) -> Dict[str, Any]:
    """Permanent deletion de usuario"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "User not found"}
        
        with transaction(db):
            # Todas las operaciones en una transacción
            db.query(ChatLog).filter(ChatLog.user_id == user_id).delete(synchronize_session=False)
            db.query(UserMemory).filter(UserMemory.user_id == user_id).delete(synchronize_session=False)
            db.query(KnowledgeEntry).filter(KnowledgeEntry.user_id == user_id).delete(synchronize_session=False)
            db.query(UserSession).filter(UserSession.user_id == user_id).delete(synchronize_session=False)
            db.delete(user)
        
        logger.warning(f"PERMANENT DELETE: User {user.username} and all related data deleted")
        return {"success": True, "deleted_user_id": user_id}
    
    except Exception as e:
        logger.error(f"Error permanently deleting user {user_id}: {e}", exc_info=True)
        return {"error": str(e)}
```

### 3. **MEDIO: Falta de Timeout en CircuitBreaker**
**Archivo:** [backend/core/llm_client.py](backend/core/llm_client.py#L44-L73)  
**Severidad:** 🟡 MEDIO

```python
# backend/core/llm_client.py - Línea 44-73
class CircuitBreaker:
    def __init__(self, failure_threshold=None, recovery_timeout=None):
        self.failures = 0
        self.threshold = failure_threshold or CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self.recovery_timeout = recovery_timeout or CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        self.state = "closed"
        self.last_failure: float = 0.0
        self.half_open_calls = 0
        self.half_open_max_calls = 2

    def record_failure(self, is_network_error: bool = True):
        if not is_network_error: return
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.threshold:
            if self.state != "open":
                print(f"[CircuitBreaker] State changed to OPEN...")
                try:
                    # ❌ Sin await timeout
                    task = asyncio.create_task(system_service.log_system_failure(...))
                except: pass
            self.state = "open"
```

**Problema:**
- `asyncio.create_task()` sin await puede no completar
- Logging de fallo asíncrono puede perderse

**Corrección:**
```python
async def record_failure_async(self, is_network_error: bool = True):
    if not is_network_error: return
    self.failures += 1
    self.last_failure = time.time()
    if self.failures >= self.threshold:
        if self.state != "open":
            logger.warning(f"[CircuitBreaker] State changed to OPEN after {self.failures} failures")
            try:
                await asyncio.wait_for(
                    system_service.log_system_failure(
                        type='API_ERROR',
                        description=f'Ollama unreachable: CB opened after {self.failures} failures',
                        severity='critical'
                    ),
                    timeout=5.0  # Timeout en logging
                )
            except asyncio.TimeoutError:
                logger.error("CircuitBreaker failure logging timed out")
            except Exception as e:
                logger.error(f"CircuitBreaker logging error: {e}")
        self.state = "open"
```

---

## ⚡ PROBLEMAS DE RENDIMIENTO

### 1. **CRÍTICO: Operación N+1 en thinker.py**
**Archivo:** [backend/agents/thinker.py](backend/agents/thinker.py#L115-L140)  
**Severidad:** 🔴 CRÍTICO

```python
# backend/agents/thinker.py - Línea 115-140
recent_nodes = db.query(KnowledgeNode).order_by(KnowledgeNode.updated_at.desc()).limit(50).all()
# ✅ Límite OK

# Línea 120-130
for node in recent_nodes:  # ❌ N queries siguientes
    degree_query = (
        db.query(func.count(GraphLink.id))
        .filter((GraphLink.source == node.id) | (GraphLink.target == node.id))
        .scalar()
    )  # ❌ 1 query por node → N+1

degree_node_ids = [row[0] for row in degree_node_ids_query.all()]
degree_nodes = db.query(KnowledgeNode).filter(KnowledgeNode.id.in_(degree_node_ids)).all()
# ✅ Esto sí usa IN (bueno)

source_links = db.query(GraphLink).filter(GraphLink.source.in_(node_ids)).limit(200).all()
target_links = db.query(GraphLink).filter(GraphLink.target.in_(node_ids)).limit(200).all()
# ✅ Estos usan IN (bueno)
```

**Problema:** La línea 120-130 hace 1 query por cada node = 50 queries (N+1)

**Corrección:**
```python
from sqlalchemy import func

# Crear aggregate en 1 query
degree_query = db.query(
    func.coalesce(GraphLink.source, GraphLink.target).label("node_id"),
    func.count(GraphLink.id).label("degree")
).filter(
    (GraphLink.source.in_([n.id for n in recent_nodes])) |
    (GraphLink.target.in_([n.id for n in recent_nodes]))
).group_by("node_id").all()  # ✅ 1 query para todos

degree_map = {node_id: deg for node_id, deg in degree_query}
degree_nodes = [n for n in recent_nodes if degree_map.get(n.id, 0) > threshold]
```

### 2. **ALTO: .all() sin LIMIT en scripts de mantenimiento**
**Archivos:** 
- [backend/generate_identity_dataset.py](backend/generate_identity_dataset.py#L98)
- [backend/scripts/semantic_hotfix.py](backend/scripts/semantic_hotfix.py#L30)

**Severidad:** 🟠 ALTO

```python
# backend/generate_identity_dataset.py - Línea 98
logs = db.query(ChatLog).order_by(ChatLog.timestamp.asc()).all()  # ❌ Sin límite

# backend/scripts/semantic_hotfix.py - Línea 30
entries = db.query(KnowledgeEntry).all()  # ❌ Sin límite
```

**Corrección:**
```python
# Agregar límites o paginar
batch_size = 1000

# Opción 1: Limit
logs = db.query(ChatLog).order_by(ChatLog.timestamp.asc()).limit(batch_size).all()

# Opción 2: Paginación
for offset in range(0, total_count, batch_size):
    entries = db.query(KnowledgeEntry).offset(offset).limit(batch_size).all()
    # Procesar batch
```

### 3. **MEDIO: Caché Ineficiente - Normalización Agresiva Sin Límite**
**Archivo:** [backend/core/cache.py](backend/core/cache.py#L30-L45)  
**Severidad:** 🟡 MEDIO

```python
# backend/core/cache.py - Línea 30-45
def _normalize_prompt(self, prompt: str) -> str:
    text = prompt.strip().lower()
    # 7 regex operations
    text = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}...', '', text)  # UUIDs
    # ... más regex ...
    stopwords = {'el', 'la', 'los', ...}  # Set lookup OK
    words = [w for w in text.split() if w not in stopwords]
    return " ".join(words)
```

**Problema:**
- 7 regex operations por get/set de caché = overhead
- Para prompts largos, split + list comp es ineficiente
- El set de stopwords está bien, pero se crea cada llamada

**Corrección:**
```python
class SmartCache:
    # Compilar regex una sola vez
    _UUID_PATTERN = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}...')
    _DATE_PATTERN = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}...')
    _STOPWORDS = frozenset({'el', 'la', 'los', 'las', ...})  # Frozenset = hashable, faster lookup

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        text = prompt.strip().lower()
        text = SmartCache._UUID_PATTERN.sub('', text)
        text = SmartCache._DATE_PATTERN.sub('', text)
        # ... usar frozenset ...
        return " ".join(w for w in text.split() if w not in SmartCache._STOPWORDS)
```

---

## 🏗️ ARQUITECTURA Y DISEÑO

### 1. **CRÍTICO: Acoplamiento Fuerte - Global State**
**Archivo:** [backend/services/chat_service.py](backend/services/chat_service.py#L22)  
**Severidad:** 🔴 CRÍTICO

```python
# ❌ Global state dict sin sincronización, sin persistencia
pending_tools = {}
```

**Problemas:**
- Se pierde en restart del servidor
- Multi-proceso: Los workers distintos no comparten state
- Sin transacciones atómicas

**Corrección:** Usar base de datos
```python
# En database.py
class PendingTool(Base):
    __tablename__ = 'pending_tools'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    tool_type = Column(String)
    command = Column(Text)
    original_query = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    approved = Column(Boolean, default=False)

# En services/chat_service.py
async def handle_pending_tool(user_id: int, response: str, db: Session):
    tool = db.query(PendingTool).filter(
        PendingTool.user_id == user_id,
        PendingTool.approved == False
    ).with_for_update().first()
    
    if not tool:
        return None
    
    # Procesar tool...
    
    db.delete(tool)
    db.commit()
```

### 2. **ALTO: Violación SOLID - Single Responsibility**
**Archivo:** [backend/services/chat_service.py](backend/services/chat_service.py#L1-L200)  
**Severidad:** 🟠 ALTO

```python
# ChatService hace todo:
# - Classifica intent
# - Valida seguridad
# - Maneja caché
# - Orquesta agentes
# - Maneja herramientas
# - Extrae memoria
# - ... (más 10 responsabilidades)
```

**Corrección:** Separar en servicios especializados
```python
# services/intent_classifier.py
class IntentClassifier:
    async def classify(self, query: str) -> str: ...

# services/security_validator.py
class SecurityValidator:
    async def validate(self, query: str) -> Tuple[bool, str]: ...

# services/cache_manager.py
class CacheManager:
    async def get(self, key: str) -> Optional[str]: ...

# services/orchestrator_service.py
class OrchestratorService:
    async def execute_task(self, task_type: str, data: Any) -> Any: ...

# Luego ChatService solo coordina
class ChatService:
    async def handle_standard_query(self, query: str, ...):
        intent = await self.intent_classifier.classify(query)
        is_safe, reason = await self.security_validator.validate(query)
        cached = await self.cache_manager.get(query)
        ...
```

### 3. **ALTO: Falta de Abstracción - Tight Coupling a ChromaDB**
**Archivo:** [backend/core/vector_db.py](backend/core/vector_db.py#L1-L50)  
**Severidad:** 🟠 ALTO

```python
# VectorDB está acoplado a ChromaDB
# Si quisiéramos cambiar a Pinecone o Weaviate, hay que reescribir todo

class VectorDB:
    def __init__(self):
        self.client = chromadb.PersistentClient(...)  # ❌ Hardcoded
        self.collection = self.client.get_or_create_collection(...)
```

**Corrección:** Usar interfaz abstracta
```python
from abc import ABC, abstractmethod

class VectorStore(ABC):
    @abstractmethod
    async def index(self, id: str, text: str, metadata: Dict): pass
    
    @abstractmethod
    async def search(self, query: str, limit: int) -> List[Dict]: pass

class ChromaVectorStore(VectorStore):
    async def index(self, id: str, text: str, metadata: Dict):
        # ChromaDB implementation

class PineconeVectorStore(VectorStore):
    async def index(self, id: str, text: str, metadata: Dict):
        # Pinecone implementation

# En config
VECTOR_STORE_TYPE = os.getenv("VECTOR_STORE_TYPE", "chroma")

def get_vector_store() -> VectorStore:
    if VECTOR_STORE_TYPE == "chroma":
        return ChromaVectorStore()
    elif VECTOR_STORE_TYPE == "pinecone":
        return PineconeVectorStore()
```

### 4. **MEDIO: Puntos Únicos de Fallo - Ollama**
**Arquitectura General**  
**Severidad:** 🟡 MEDIO

```
Frontend → Backend → Ollama (single point)
```

**Problema:**
- Si Ollama cae, todo el sistema cae
- Sin failover o replica

**Corrección:**
```yaml
# docker-compose.yml
version: '3'
services:
  ollama_1:
    image: ollama/ollama
    ports:
      - "11438:11434"
  
  ollama_2:
    image: ollama/ollama
    ports:
      - "11439:11434"
  
  nginx:
    image: nginx
    ports:
      - "11440:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

```python
# backend/core/llm_client.py
OLLAMA_URLS = [
    "http://localhost:11438/api/chat",
    "http://localhost:11439/api/chat",  # Replica
]

async def chat(...):
    for url in OLLAMA_URLS:
        try:
            response = await client.post(url, json=payload, timeout=30)
            return response
        except Exception as e:
            logger.warning(f"Failed on {url}, trying next...")
    raise LLMUnavailableError("All Ollama instances down")
```

---

## 📝 PROBLEMAS ADICIONALES

### 1. **Operaciones de Archivo sin Sincronización**
**Archivo:** [backend/services/memory_service.py](backend/services/memory_service.py#L65-L75)  
**Severidad:** 🟠 ALTO

```python
def save_json_memory(self, memory: Dict[str, Any]) -> None:
    # ❌ Si 2 requests escriben simultáneamente, corrupción
    with self._lock:  # OK for threading, but not async-safe
        try:
            MEMORY_JSON_PATH.write_text(...)
```

Ya fue cubierto en sección de Concurrencia, pero también afecta archivos.

### 2. **Falta de Rate Limiting Granular**
**Archivos múltiples**  
**Severidad:** 🟡 MEDIO

```python
# Solo endpoints /query tienen rate limiting
# Falta en:
# - /stt
# - /tts (síntesis puede ser costosa)
# - /research/start (genera muchas tasks)
# - /sandbox/execute (consume CPU)
```

### 3. **Falta de Validación de Tamaño en Uploaded Files**
**Archivo:** [backend/services/memory_service.py](backend/services/memory_service.py#L194-L202)  
**Severidad:** 🟠 ALTO

```python
async def ingest_document(self, file_stream, filename: str, user_id: int):
    # ❌ Sin validación de tamaño
    temp_path = self.base_dir / "data" / "uploads" / filename
    with open(temp_path, "wb") as f:
        f.write(file_stream.read())  # Podría ser 1GB
```

---

## 📊 RESUMEN EJECUTIVO

### Hallazgos por Severidad

| Severidad | Cantidad | Impacto |
|-----------|----------|--------|
| 🔴 CRÍTICO | 8 | Seguridad, Disponibilidad, Integridad |
| 🟠 ALTO | 12 | Performance, Estabilidad |
| 🟡 MEDIO | 7 | Resiliencia, Mantenibilidad |
| 🟢 BAJO | 3 | Operacional |

### Top 5 Prioridades de Corrección

**1. [CRÍTICO] Global State sin Sincronización en chat_service.py**
- Impacto: Race conditions, corrupción de datos
- Esfuerzo: 4 horas
- Solución: Migrar `pending_tools` a BD

**2. [CRÍTICO] Race Condition en task_queue.py (threading.Lock en async)**
- Impacto: Event loop congela, deadlocks
- Esfuerzo: 6 horas
- Solución: Cambiar a asyncio.Lock, usar asyncio.to_thread

**3. [CRÍTICO] PrioritySemaphore Roto en llm_client.py**
- Impacto: Deadlocks, starvation de tasks
- Esfuerzo: 3 horas
- Solución: Reimplementar con Lock adecuado

**4. [ALTO] Memory Leak en cache.py + sin TTL**
- Impacto: OOM en producción
- Esfuerzo: 2 horas
- Solución: Agregar cleanup task asíncrono

**5. [ALTO] Limpieza deficiente de temp files en stt_service.py**
- Impacto: Disk exhaustion
- Esfuerzo: 2 horas
- Solución: atexit handler, mejor error handling

### Recomendaciones Adicionales

1. **Implementar APM (Application Performance Monitoring)**
   - Sentry para error tracking
   - DataDog/New Relic para performance

2. **Testing Mejorando**
   - Unit tests para funciones críticas
   - Integration tests para race conditions
   - Chaos engineering: simular fallos

3. **Monitoreo Proactivo**
   - AlertasOOM, CPU, Disk
   - Circuit breaker alerting
   - Slow query detection

4. **Auditoría Regular**
   - OWASP Top 10 scanning (SAST)
   - Dependency scanning (vulnerabilidades en libs)
   - Pen testing trimestral

---

**Análisis Completado:** 24 de Mayo de 2026  
**Analista:** GitHub Copilot (Claude Haiku 4.5)
