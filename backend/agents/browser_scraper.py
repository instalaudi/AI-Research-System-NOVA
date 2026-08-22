"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v14.0 — Motor de Ingestión Dinámica y Browser Scraper  ║
║  Archivo: agents/browser_scraper.py                          ║
║  Extrae contenido limpio y estructurado de sitios web        ║
║  estáticos y SPAs dinámicas con protección SSRF estricta.     ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import urllib.parse
import logging
from typing import Dict, Any, Optional, List
import httpx

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    BeautifulSoup = None

logger = logging.getLogger("agents.browser_scraper")

# SEC-05: Lista de esquemas y hosts prohibidos contra ataques SSRF
BLOCKED_SCHEMES = ['file', 'ftp', 'gopher', 'data', 'javascript']
BLOCKED_HOSTS = ['localhost', '127.0.0.1', '192.168.', '10.', '172.', '0.0.0.0', '169.254.', '::1', '[::1]', 'internal']


class BrowserScraper:
    """
    Motor de navegación e ingestión web para extraer texto limpio y estructurado.
    Soporta páginas dinámicas y estáticas eliminando anuncios, estilos y scripts.
    """
    def __init__(self, timeout_seconds: int = 15):
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def is_safe_url(url: str) -> bool:
        """Valida una URL contra ataques SSRF."""
        if not url:
            return False
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme.lower() not in ['http', 'https']:
                return False
            
            host = parsed.netloc.lower()
            for blocked in BLOCKED_HOSTS:
                if blocked in host:
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def clean_html_to_markdown(html_content: str) -> Dict[str, Any]:
        """
        Limpia el código HTML eliminando ruido y extrayendo título y texto estructurado.
        """
        if not html_content or not html_content.strip():
            return {"title": "", "content": "", "headings": []}

        if BeautifulSoup is not None:
            soup = BeautifulSoup(html_content, "html.parser")
            
            # 1. Eliminar etiquetas no deseadas
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside", "svg", "form"]):
                tag.decompose()

            # 2. Extraer título
            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            elif soup.find("h1"):
                title = soup.find("h1").get_text().strip()

            # 3. Extraer encabezados principales
            headings = [h.get_text().strip() for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text().strip()]

            # 4. Extraer texto limpio
            text = soup.get_text(separator="\n")
            # Normalizar saltos de línea múltiples
            cleaned_text = re.sub(r'\n\s*\n+', '\n\n', text).strip()
            
            return {
                "title": title,
                "content": cleaned_text,
                "headings": headings[:10]
            }
        else:
            # Fallback con expresiones regulares si BeautifulSoup no está disponible
            no_scripts = re.sub(r'<(script|style).*?>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', no_scripts)
            cleaned_text = re.sub(r'\s+', ' ', text).strip()
            return {
                "title": "Web Document",
                "content": cleaned_text,
                "headings": []
            }

    async def fetch_and_clean(self, url: str) -> Dict[str, Any]:
        """
        Descarga una URL de forma segura y retorna el contenido depurado.
        """
        if not self.is_safe_url(url):
            logger.warning(f"[BrowserScraper] 🛡️ URL bloqueada por protección SSRF: {url}")
            return {
                "url": url,
                "success": False,
                "error": "URL no permitida por políticas de seguridad (SSRF block)"
            }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    return {
                        "url": url,
                        "success": False,
                        "status_code": response.status_code,
                        "error": f"HTTP {response.status_code}"
                    }
                
                parsed_data = self.clean_html_to_markdown(response.text)
                return {
                    "url": url,
                    "success": True,
                    "status_code": 200,
                    "title": parsed_data.get("title", ""),
                    "content": parsed_data.get("content", ""),
                    "headings": parsed_data.get("headings", [])
                }
        except Exception as e:
            logger.error(f"[BrowserScraper] Error descargando {url}: {e}")
            return {
                "url": url,
                "success": False,
                "error": str(e)
            }


# Instancia global del BrowserScraper
browser_scraper = BrowserScraper()
