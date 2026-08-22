import os
import re
import shutil
import tempfile
import asyncio
import subprocess
from io import BytesIO
from fastapi import UploadFile, HTTPException
from typing import Any, Optional
from core.logging_config import get_logger

logger = get_logger("services.stt")

class STTService:
    def __init__(self):
        pass

    async def transcribe_audio(self, audio: UploadFile, stt_model: Any) -> str:
        """
        Processes an audio file and transcribes it using the provided model.
        """
        if not stt_model:
            raise HTTPException(status_code=503, detail="STT model not loaded")

        tmp_path, wav_path = None, None
        try:
            # 1. Save incoming audio (v10.7.0: Async read + BytesIO for seekability)
            audio_content = await audio.read()
            audio_stream = BytesIO(audio_content)
            
            filename = audio.filename if audio.filename else "audio.webm"
            suffix = os.path.splitext(filename)[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(audio_stream, tmp)
                tmp_path = tmp.name
            
            # 2. Convert to standard WAV format (16kHz, mono)
            wav_path = tmp_path + ".wav"
            
            # v10.7.0: Step removed (FFmpeg volumedetect) to reduce latency and event loop load.
            
            cmd_conv = ['ffmpeg', '-y', '-i', tmp_path, '-ar', '16000', '-ac', '1', wav_path]
            result = await asyncio.to_thread(
                subprocess.run,
                cmd_conv,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            if result.returncode != 0:
                logger.warning(f"FFmpeg conversion warning: {result.stderr[:200]}")

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1000:
                logger.warning("WAV conversion failed or file too small.")
                return ""

            # 3. Transcription using Whisper
            # Whisper transcription is a heavy CPU task. Run in a thread pool to avoid blocking.
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: stt_model.transcribe(
                wav_path, 
                fp16=False, 
                language="es",
                temperature=0.0,
                no_speech_threshold=0.1,  
                logprob_threshold=-1.0,   
                condition_on_previous_text=False
            ))
            
            transcription = result["text"].strip()
            logger.info(f"Transcription completed: '{transcription[:50]}...'")
            return transcription

        except Exception as e:
            logger.error(f"STT process failure: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}")
        finally:
            # Cleanup temp files
            for p in [tmp_path, wav_path]:
                if p and os.path.exists(p):
                    try: os.unlink(p)
                    except: pass

stt_service = STTService()
