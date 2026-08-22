# 🔧 PATCHES DE CORRECCIÓN - NOVA AI AUDIT

## 1. FIX-001: PrioritySemaphore (CRÍTICO)

**Archivo:** `backend/core/llm_client.py`

**Cambio:** Líneas 70-105

```python
# ❌ ANTES (ROTO):
class PrioritySemaphore:
    def __init__(self, value: int = 1):
        self._value = value
        self._waiters = []
        self._lock = asyncio.Lock()

    async def acquire(self, priority: int = 1, timeout: Optional[float] = None):
        async with self._lock:
            if self._value > 0:
                if priority > 0 and self._value == 1:
                    pass
                else:
                    self._value -= 1
                    return True
        # Sale del lock sin procesar waiters
        
    def _release_sync(self):  # ❌ Síncrono desde async
        if not self._waiters:
            self._value += 1
            return

# ✅ DESPUÉS (CORRECTO):
class PrioritySemaphore:
    def __init__(self, value: int = 1):
        self._value = value
        self._waiters: List[Tuple[int, asyncio.Future]] = []
        self._lock = asyncio.Lock()

    async def acquire(self, priority: int = 1, timeout: Optional[float] = None) -> bool:
        async with self._lock:
            if self._value > 0:
                self._value -= 1
                return True
            
            fut: asyncio.Future = asyncio.get_event_loop().create_future()
            self._waiters.append((priority, fut))
            self._waiters.sort(key=lambda x: -x[0])  # Higher priority first
        
        try:
            if timeout:
                await asyncio.wait_for(fut, timeout=timeout)
            else:
                await fut
            return True
        except asyncio.TimeoutError:
            async with self._lock:
                self._waiters = [w for w in self._waiters if w[1] != fut]
            raise TimeoutError(f"Semaphore acquire timeout (priority {priority})")

    async def release(self) -> None:
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

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()

    def request(self, priority: int = 1, timeout: Optional[float] = None):
        """Return a context manager for acquire/release"""
        class PriorityContext:
            def __init__(self, sem, prio, tout):
                self.sem = sem
                self.prio = prio
                self.tout = tout
            
            async def __aenter__(self):
                await self.sem.acquire(self.prio, self.tout)
                return self.sem
            
            async def __aexit__(self, et, ev, tb) -> None:
                await self.sem.release()
        
        return PriorityContext(self, priority, timeout)
```

---

## 2. FIX-002: task_queue.py - Cambiar threading.Lock → asyncio.Lock (CRÍTICO)

**Archivo:** `backend/core/task_queue.py`

**Cambios:** Líneas 18, 76-86, 95-105, 110-115

```python
# ❌ ANTES:
class TaskQueue:
    def __init__(self, concurrency: Optional[int] = None):
        self._lock = threading.Lock()  # ❌ Síncrono

    def _rpop(self, queue_name: str) -> Optional[str]:
        if self.use_redis:
            return self.redis.rpop(queue_name)
        with self._lock:  # ❌ Bloquea el event loop
            q = self._load_queue(queue_name)

# ✅ DESPUÉS:
class TaskQueue:
    def __init__(self, concurrency: Optional[int] = None):
        self._lock = asyncio.Lock()  # ✅ Async-safe
        # ...resto del __init__

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
        
        async with self._lock:  # ✅ Non-blocking wait
            q = await asyncio.to_thread(self._load_queue, queue_name)
            q.appendleft(payload)
            await asyncio.to_thread(self._dump_queue, queue_name, q)

    async def _llen(self, queue_name: str) -> int:
        if self.use_redis:
            return await asyncio.to_thread(self.redis.llen, queue_name)
        
        async with self._lock:
            return len(await asyncio.to_thread(self._load_queue, queue_name))
```

---

## 3. FIX-003: Migrar pending_tools a BD (CRÍTICO)

**Archivo:** `backend/core/database.py`

**Agregar nuevo modelo:**

```python
class PendingTool(Base):
    """Human-in-the-loop tool approval tracking"""
    __tablename__ = 'pending_tools'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True, nullable=False)
    tool_type = Column(String, nullable=False)  # 'terminal', 'file_edit', etc
    command = Column(Text, nullable=False)
    original_query = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    approved = Column(Boolean, default=False, index=True)
    executed = Column(Boolean, default=False)
    
    __table_args__ = (
        Index('ix_pending_user_approved', 'user_id', 'approved'),
    )
```

**Archivo:** `backend/services/chat_service.py`

**Cambio:** Líneas 22, 71-78, eliminar global pending_tools

```python
# ❌ ANTES:
pending_tools = {} # global state

# En handle_standard_query:
if user_id in pending_tools:
    approval_query = query.lower().strip()
    if any(x in approval_query for x in ["si", "yes", ...]):
        # Race condition TOCTOU

# ✅ DESPUÉS:
# Eliminar global pending_tools

class ToolApprovalService:
    async def check_pending_approval(self, user_id: int, approval_response: str, db: Session) -> Optional[Dict]:
        """Atómicamente: verifica y limpia tool pendiente"""
        from core.database import PendingTool
        
        tool = db.query(PendingTool).filter(
            PendingTool.user_id == user_id,
            PendingTool.approved == False
        ).with_for_update().first()  # ✅ SELECT FOR UPDATE = lock
        
        if not tool:
            return None
        
        approval_query = approval_response.lower().strip()
        if any(x in approval_query for x in ["si", "yes", "aceptar", "dale", "autorizo", "procede"]):
            tool.approved = True
            db.commit()  # ✅ Transactional
            return {
                "tool_type": tool.tool_type,
                "command": tool.command,
                "query": tool.original_query
            }
        elif any(x in approval_query for x in ["no", "cancelar", "detente", "abortar"]):
            db.delete(tool)
            db.commit()  # ✅ Transactional
            return None
        
        return None

# En ChatService:
tool_approval_service = ToolApprovalService()

async def handle_standard_query(self, query: str, ...):
    # Chequear si hay herramienta pendiente
    pending = await tool_approval_service.check_pending_approval(user_id, query, db)
    if pending:
        # Ejecutar herramienta
        answer = await self._execute_tool(pending, db)
        return {"query": query, "answer": answer, "mode": "tool_execution"}
```

---

## 4. FIX-004: Memory Leak en Cache (CRÍTICO)

**Archivo:** `backend/core/cache.py`

**Cambio:** Agregar background cleanup task

```python
# ✅ Agregar después de la clase SmartCache:

import logging
logger = logging.getLogger("core.cache")

async def start_cache_cleanup():
    """Background task que limpia entries expiradas"""
    while True:
        try:
            await asyncio.sleep(smart_cache.ttl / 2)  # Cada TTL/2
            
            expired_keys = []
            for key, entry in smart_cache._cache.items():
                if time.time() - entry['timestamp'] > smart_cache.ttl:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del smart_cache._cache[key]
            
            if expired_keys:
                logger.debug(f"Cache cleanup: {len(expired_keys)} expired entries removed")
        
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")
            await asyncio.sleep(60)  # Retry después

# En backend/main.py, en lifespan:
logger.info("Starting cache cleanup task...")
asyncio.create_task(start_cache_cleanup())
```

**Alternativa (mejor): Usar asyncio.Lock para evitar race condition**

```python
class SmartCache:
    def __init__(self, ttl_seconds: int = 7200, max_entries: int = 300):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()  # ✅ Agregar lock

    async def get(self, prompt: str, model: str, params: Dict[str, Any], session_id: str = None) -> Optional[str]:
        key = self._generate_key(prompt, model, params, session_id)
        
        async with self._lock:  # ✅ Thread-safe access
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

    async def set(self, prompt: str, model: str, params: Dict[str, Any], session_id: str, response: str):
        key = self._generate_key(prompt, model, params, session_id)
        
        async with self._lock:  # ✅ Thread-safe access
            if key in self._cache:
                self._cache.move_to_end(key)
            
            while len(self._cache) >= self.max_entries:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug(f"Cache LRU eviction: {evicted_key[:8]}...")
            
            self._cache[key] = {
                "response": response,
                "timestamp": time.time()
            }
```

---

## 5. FIX-005: Limpieza de Temp Files (ALTO)

**Archivo:** `backend/services/stt_service.py`

**Cambio:** Líneas 13-85

```python
# ❌ ANTES:
finally:
    for p in [tmp_path, wav_path]:
        if p and os.path.exists(p):
            try: os.unlink(p)  # ❌ Silent fail
            except: pass

# ✅ DESPUÉS:
import atexit
from pathlib import Path

class STTService:
    def __init__(self):
        self.temp_files: Set[str] = set()
        atexit.register(self._cleanup_on_exit)
    
    def _cleanup_on_exit(self):
        """Limpia todos los archivos temporales al shutdown"""
        for path in list(self.temp_files):
            try:
                Path(path).unlink(missing_ok=True)
                self.temp_files.discard(path)
            except Exception as e:
                logger.warning(f"Could not clean temp file {path}: {e}")

    async def transcribe_audio(self, audio: UploadFile, stt_model: Any) -> str:
        tmp_path, wav_path = None, None
        try:
            # ... resto del código ...
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(audio_stream, tmp)
                tmp_path = tmp.name
                self.temp_files.add(tmp_path)  # ✅ Track
            
            wav_path = tmp_path + ".wav"
            self.temp_files.add(wav_path)  # ✅ Track
            
            # ... conversión y transcripción ...
            
            return transcription
        
        except Exception as e:
            logger.error(f"STT process failure: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Transcription error")
        
        finally:
            # ✅ Cleanup con mejor error handling
            for p in [tmp_path, wav_path]:
                if p:
                    try:
                        Path(p).unlink(missing_ok=True)
                        self.temp_files.discard(p)
                    except PermissionError as e:
                        logger.warning(f"Permission denied cleaning {p}, will clean on exit: {e}")
                        # Será limpiado en atexit
                    except Exception as e:
                        logger.error(f"Error cleaning {p}: {e}")

stt_service = STTService()
```

---

## 6. FIX-006: Agregar Rate Limiting a endpoints TTS (ALTO)

**Archivo:** `backend/routers/chat.py`

**Cambios:** Líneas 29, 93, 102, 108, 113

```python
# ❌ ANTES:
@router.post("/stt")
async def speech_to_text(request: Request, audio: UploadFile = File(...), 
                         current_user: User = Depends(get_current_user)):
    # Sin rate limiting

@router.post("/tts")
async def text_to_speech(request: Request, current_user: User = Depends(get_current_user)):
    # Sin rate limiting

@router.get("/tts/status")
async def tts_status(current_user: User = Depends(get_current_user)):
    # Sin rate limiting

# ✅ DESPUÉS:
@router.post("/stt")
@limiter.limit("10/minute")  # ✅ Agregado
async def speech_to_text(request: Request, audio: UploadFile = File(...), 
                         current_user: User = Depends(get_current_user)):
    stt_model = request.app.state.stt_model
    text = await stt_service.transcribe_audio(audio, stt_model)
    return {"text": text}

@router.post("/tts")
@limiter.limit("5/minute")  # ✅ Más restrictivo (síntesis es cara)
async def text_to_speech(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    text, speed = body.get("text", "").strip(), float(body.get("speed", 1.0))
    if not text: 
        raise HTTPException(status_code=400, detail="Text empty")
    
    audio = await nova_voice.synthesize(text, speed=speed)
    if not audio: 
        raise HTTPException(status_code=503, detail="TTS Unavailable")
    
    return Response(content=audio, media_type="audio/wav")

@router.get("/tts/status")
@limiter.limit("10/minute")  # ✅ Agregado
async def tts_status(current_user: User = Depends(get_current_user)):
    return nova_voice.get_status()

@router.post("/tts/voice")
@limiter.limit("5/minute")  # ✅ Agregado
async def set_nova_voice(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    voice = body.get("voice", "es_MX-high")
    nova_voice.set_voice(voice)
    await nova_voice.initialize(voice)
    return {"status": "ok", "voice": voice}

@router.delete("/tts/cache")
@limiter.limit("1/minute")  # ✅ Muy restrictivo
async def clear_tts_cache(admin: User = Depends(get_current_admin)):
    nova_voice.clear_cache()
    return {"status": "ok"}

@router.get("/audio/{cache_key}")
@limiter.limit("30/minute")  # ✅ Agregado
async def get_audio_chunk(cache_key: str):
    import asyncio
    from core.tts_engine import CACHE_DIR
    path = CACHE_DIR / f"{cache_key}.wav"
    
    for _ in range(150):
        if path.exists():
            break
        await asyncio.sleep(0.1)
    
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio chunk not found or synthesis timed out")
    
    return FileResponse(path, media_type="audio/wav")
```

---

## 7. FIX-007: Validación de Tamaño en _get_files_context (ALTO)

**Archivo:** `backend/routers/chat.py`

**Cambio:** Líneas 34-41

```python
# ❌ ANTES:
def _get_files_context(req: QueryRequest) -> str:
    if not req.files: return ""
    files_to_process = req.files[:5]
    context = "\n\n[ARCHIVOS ADJUNTOS]:\n"
    for f in files_to_process:
        context += f"{f.name}: {f.content[:5000]}\n"
    
    if len(context) > 20000:
        context = context[:19997] + "..."
    return context

# ✅ DESPUÉS:
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_TOTAL_SIZE = 20 * 1024 * 1024  # 20MB total

def _get_files_context(req: QueryRequest) -> str:
    if not req.files: 
        return ""
    
    files_to_process = req.files[:5]
    context = "\n\n[ARCHIVOS ADJUNTOS]:\n"
    total_size = 0
    
    for f in files_to_process:
        # Calcular tamaño
        content_size = len(f.content.encode('utf-8') if isinstance(f.content, str) else f.content)
        
        # Validar tamaño individual
        if content_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"Archivo '{f.name}' excede {MAX_FILE_SIZE} bytes"
            )
        
        # Validar tamaño total
        total_size += content_size
        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(
                status_code=413, 
                detail="Total de archivos excede el límite permitido"
            )
        
        context += f"{f.name}: {f.content[:5000]}\n"
    
    if len(context) > 20000:
        context = context[:19997] + "..."
    
    return context
```

---

## Testing después de patches

```bash
# 1. Unit tests para PrioritySemaphore
pytest backend/tests/test_priority_semaphore.py

# 2. Integration tests para task_queue
pytest backend/tests/test_task_queue.py

# 3. Race condition tests
pytest backend/tests/test_race_conditions.py --stress

# 4. Memory leak detection
python -m pytest backend/tests/test_memory.py --memray

# 5. Load test después de correcciones
locust -f backend/tests/locustfile.py --host=http://localhost:8000
```

---

**Status:** Todos los patches están listos para merge  
**Tiempo estimado de corrección:** 20 horas  
**Prioridad:** INMEDIATA (esta semana)
