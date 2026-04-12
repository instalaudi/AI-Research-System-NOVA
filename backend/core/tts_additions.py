# ════════════════════════════════════════════════════════════════
#  VOZ DE NOVA — Agregar a main.py
# ════════════════════════════════════════════════════════════════

# 1. IMPORT — agregar junto a los otros imports al inicio:

from core.tts_engine import nova_voice
from fastapi.responses import Response

# 2. EN lifespan() — agregar después de stt_model:

    print("Inicializando voz de NOVA (TTS)...")
    try:
        await nova_voice.initialize()
        print("✅ Voz de NOVA lista")
    except Exception as e:
        print(f"⚠ TTS no disponible: {e}")

# 3. NUEVOS ENDPOINTS — pegar antes de /health:

# ── NOVA habla: texto → audio WAV ────────────────────────────────
@app.post("/tts")
async def text_to_speech(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    NOVA convierte texto a voz.
    Devuelve audio WAV listo para reproducir en el navegador.
    """
    body  = await request.json()
    text  = body.get("text", "").strip()
    speed = float(body.get("speed", 1.0))

    if not text:
        raise HTTPException(status_code=400, detail="Texto vacío")

    audio = await nova_voice.synthesize(text, speed=speed)

    if not audio:
        raise HTTPException(
            status_code=503,
            detail="Voz no disponible. Instala piper-tts: pip install piper-tts"
        )

    return Response(
        content      = audio,
        media_type   = "audio/wav",
        headers      = {"Content-Disposition": "inline; filename=nova_voice.wav"}
    )


# ── NOVA habla: respuesta completa de chat con voz ────────────────
@app.post("/query/voice")
@limiter.limit("30/60s")
async def ask_with_voice(
    request: Request,
    req: QueryRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Endpoint combinado: NOVA responde con texto Y audio.
    El frontend puede mostrar el texto y reproducir la voz.
    """
    # Obtener respuesta de texto (usando el sistema existente)
    db = SessionLocal()
    text_response = ""

    try:
        # Obtener contexto y generar respuesta
        knowledge_context, _, _ = get_knowledge_context(db, req.query)
        history_context = get_chat_history_context(db, req.query)

        from core.prompts import KNOWLEDGE_QUERY_PROMPT
        full_context = f"{history_context}\n{knowledge_context}"

        prompt = KNOWLEDGE_QUERY_PROMPT.format(
            query         = req.query,
            context       = full_context[:2000],
            image_context = ""
        )

        text_response = await llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.7
        )

    except Exception as e:
        text_response = f"Hubo un error procesando tu pregunta: {str(e)[:100]}"
    finally:
        db.close()

    if not text_response:
        text_response = "No pude generar una respuesta en este momento."

    # Guardar en historial
    background_tasks.add_task(store_chat_message, "user",      req.query,     current_user.id)
    background_tasks.add_task(store_chat_message, "assistant", text_response, current_user.id)

    # Generar audio de la respuesta
    audio = await nova_voice.synthesize(text_response)

    if audio:
        import base64
        audio_b64 = base64.b64encode(audio).decode("utf-8")
        return {
            "text":       text_response,
            "audio_b64":  audio_b64,
            "audio_type": "audio/wav",
            "has_audio":  True
        }
    else:
        return {
            "text":      text_response,
            "has_audio": False
        }


# ── Estado del motor de voz ───────────────────────────────────────
@app.get("/tts/status")
async def tts_status(current_user: User = Depends(get_current_user)):
    """Estado del motor de voz de NOVA."""
    return nova_voice.get_status()


# ── Cambiar voz de NOVA ───────────────────────────────────────────
@app.post("/tts/voice")
async def set_nova_voice(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Cambia la voz de NOVA."""
    body  = await request.json()
    voice = body.get("voice", "es_MX-claude-high")
    nova_voice.set_voice(voice)
    # Reinicializar con la nueva voz
    await nova_voice.initialize(voice)
    return {"status": "ok", "voice": voice}


# ── Limpiar caché de audio ────────────────────────────────────────
@app.delete("/tts/cache")
async def clear_tts_cache(admin: User = Depends(get_current_admin)):
    """Limpia el caché de audio de NOVA."""
    nova_voice.clear_cache()
    return {"status": "Caché de audio limpiado"}