"""
Pruebas Unitarias Automatizadas para Audio Streaming Chunked & TTS en Tiempo Real (Fase 3)
"""

import pytest
import asyncio
from core.tts_engine import NOVAVoiceEngine


def test_segment_text_for_streaming():
    """Valida la segmentación de texto por oraciones y cláusulas fonéticas."""
    text = (
        "Hola Juan Ramón. He terminado el análisis del sistema de seguridad. "
        "Encontré tres puntos críticos, los cuales he procedido a corregir inmediatamente. "
        "¿Deseas que revise algo más?"
    )
    segments = NOVAVoiceEngine._segment_text_for_streaming(text)
    
    assert len(segments) >= 2
    assert "Hola Juan Ramón." in segments[0] or "análisis" in segments[0]
    for seg in segments:
        assert len(seg.strip()) > 0


def test_segment_text_short():
    """Valida que textos cortos no se fragmenten innecesariamente."""
    short_text = "Todo el sistema está operativo."
    segments = NOVAVoiceEngine._segment_text_for_streaming(short_text)
    assert len(segments) == 1
    assert segments[0] == short_text


@pytest.mark.asyncio
async def test_synthesize_stream_generator():
    """Valida que synthesize_stream funcione como un generador asíncrono emitiendo bytes."""
    engine = NOVAVoiceEngine()
    
    # Mocking synthesize para prueba unitaria rápida y determinista
    async def mock_synth(clause, speed=None, speaker=0):
        return b"RIFF" + clause.encode("utf-8") + b"WAVE"
    
    engine.synthesize = mock_synth
    
    text = "Primera frase de prueba. Segunda frase de confirmación."
    chunks = []
    async for chunk in engine.synthesize_stream(text):
        chunks.append(chunk)
        
    assert len(chunks) == 2
    assert chunks[0].startswith(b"RIFF")
    assert chunks[1].startswith(b"RIFF")
