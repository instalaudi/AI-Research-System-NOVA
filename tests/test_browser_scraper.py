"""
Pruebas Unitarias Automatizadas para Browser Scraper & Ingestión Dinámica (Fase 4)
"""

import pytest
from agents.browser_scraper import BrowserScraper


def test_is_safe_url_valid():
    """Valida que URLs públicas legítimas sean aprobadas."""
    valid_urls = [
        "https://arxiv.org/abs/2401.00001",
        "https://github.com/fastapi/fastapi",
        "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "http://example.com/docs"
    ]
    for url in valid_urls:
        assert BrowserScraper.is_safe_url(url) is True


def test_is_safe_url_blocked_ssrf():
    """Valida el bloqueo estricto de URLs privadas, cloud metadata y loopbacks (SSRF)."""
    blocked_urls = [
        "http://localhost:8000/api",
        "http://127.0.0.1:3000/secret",
        "http://192.168.1.1/admin",
        "http://10.0.0.1/internal",
        "http://172.16.0.1/db",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:8080/dashboard",
        "file:///etc/passwd",
        "ftp://internal.server/file",
        "javascript:alert(1)"
    ]
    for url in blocked_urls:
        assert BrowserScraper.is_safe_url(url) is False


def test_clean_html_to_markdown():
    """Valida la sanitización de HTML eliminando scripts, publicidad y extrayendo estructura."""
    raw_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Investigación sobre Redes Neuronales</title>
        <script>alert('malware');</script>
        <style>body { color: red; }</style>
    </head>
    <body>
        <nav><a href="/home">Inicio</a></nav>
        <header><h1>Header del Sitio</h1></header>
        
        <main>
            <h1>Introducción al Deep Learning</h1>
            <p>Las redes neuronales convolucionales son ideales para procesamiento de imágenes.</p>
            
            <h2>Arquitecturas Modernas</h2>
            <p>Los Transformers han revolucionado el procesamiento de lenguaje natural (NLP).</p>
        </main>
        
        <footer>Copyright 2026</footer>
    </body>
    </html>
    """
    result = BrowserScraper.clean_html_to_markdown(raw_html)
    
    assert "Investigación sobre Redes Neuronales" in result["title"] or "Header del Sitio" in result["title"]
    assert "Introducción al Deep Learning" in result["content"]
    assert "Transformers" in result["content"]
    
    # Verificar que scripts y estilos fueron eliminados
    assert "alert('malware')" not in result["content"]
    assert "color: red" not in result["content"]
    assert len(result["headings"]) >= 2


@pytest.mark.asyncio
async def test_fetch_and_clean_ssrf_block():
    """Valida que fetch_and_clean rechace peticiones SSRF sin realizar conexión HTTP."""
    scraper = BrowserScraper()
    res = await scraper.fetch_and_clean("http://169.254.169.254/latest/meta-data/")
    assert res["success"] is False
    assert "SSRF" in res.get("error", "")
