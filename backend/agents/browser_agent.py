"""
Browser Agent - Navegacion Autonoma para NOVA
Utiliza browser-use 0.12.x + Playwright para interactuar con la web.
Imports diferidos para no bloquear el backend si las dependencias no estan.
"""
import os
import asyncio
from typing import Dict, Any
from core.logging_config import get_logger
from core.logger import agent_logger

logger = get_logger("agents.browser")

# ---------------------------------------------------------------------------
# Flags de disponibilidad (lazy check)
# ---------------------------------------------------------------------------
_BROWSER_USE_AVAILABLE = False

try:
    from browser_use import Agent, Browser, BrowserProfile, ChatOllama  # type: ignore
    _BROWSER_USE_AVAILABLE = True
except ImportError:
    Agent = Browser = BrowserProfile = ChatOllama = None  # type: ignore


class BrowserAgent:
    """
    Agente de Navegacion Autonoma de NOVA.
    Usa browser-use (v0.12+) con Ollama local para navegar la web.
    """

    def __init__(self):
        self._available = _BROWSER_USE_AVAILABLE

        if not self._available:
            logger.warning(
                "[BrowserAgent] Desactivado - 'browser-use' no instalado. "
                "Instala con: pip install browser-use playwright && playwright install chromium"
            )

    # ------------------------------------------------------------------
    #  Ejecucion de tareas
    # ------------------------------------------------------------------

    async def run_task(self, objective: str, user_id: int = 0) -> Dict[str, Any]:
        """
        Ejecuta una tarea de navegacion con reporte de estado y fallback de seguridad.
        """
        await agent_logger.set_state("Browser", "working")
        await agent_logger.log("Browser", f"Iniciando navegación: {objective[:50]}...")
        
        if not self._available:
            logger.warning("[BrowserAgent] 'browser-use' no disponible. Usando fallback de búsqueda.")
            return await self._duckduckgo_fallback(objective)

        logger.info(f"[BrowserAgent] Iniciando tarea: {objective}")
        browser_model = os.getenv("NOVA_BROWSER_MODEL", "qwen2.5:3b")
        llm = ChatOllama(model=browser_model)  # type: ignore

        browser = None
        try:
            if Browser is not None:
                browser = Browser(
                    headless=True,
                    disable_security=True,
                )
        except Exception as e:
            logger.error(f"[BrowserAgent] Error al iniciar Browser: {e}")

        if browser is None:
            await agent_logger.log("Browser", "Error inicializando navegador. Usando fallback...")
            return await self._duckduckgo_fallback(objective)

        agent = Agent(
            task=objective,
            llm=llm,
            browser=browser,
            use_vision=False,
            use_thinking=False,
            llm_timeout=180,
            max_actions_per_step=1,
            extend_system_message=(
                "CRITICAL INSTRUCTIONS:\n"
                "1. YOUR GOAL is to find specific data (e.g., a name, a price, a date).\n"
                "2. The 'done' action MUST contain the actual information found.\n"
                "4. If a page doesn't have the info, use the search bar or navigate to a search engine.\n"
            ),
        )

        try:
            history = await agent.run(max_steps=15)
            result = history.final_result()
            
            # v13.5: Si el resultado es muy corto o vacío, intentar fallback
            if not result or len(str(result).strip()) < 10:
                logger.warning("[BrowserAgent] Resultado autónomo vacío o inválido. Intentando fallback...")
                return await self._duckduckgo_fallback(objective)

            await agent_logger.log("Browser", "Tarea completada con éxito.")
            return {
                "success": True,
                "result": result,
                "steps": len(history.history),
                "agent": "browser-use"
            }
        except Exception as e:
            logger.error(f"[BrowserAgent] Error: {e}")
            await agent_logger.log("Browser", "Fallo en navegación. Intentando fallback...")
            return await self._duckduckgo_fallback(objective)
        finally:
            try:
                if browser:
                    await browser.close()
            except Exception as close_err:
                logger.debug(f"[BrowserAgent] Error cerrando navegador: {close_err}")
            await agent_logger.set_state("Browser", "idle")

    async def _duckduckgo_fallback(self, objective: str) -> Dict[str, Any]:
        """Búsqueda simple vía DuckDuckGo para emergencias."""
        try:
            import httpx
            from bs4 import BeautifulSoup
            import urllib.parse
            
            logger.info(f"[BrowserAgent] Ejecutando fallback DDG para: {objective}")
            search_query = objective.replace("Navega a ", "").replace("Busca ", "")
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
            
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    results = []
                    for res in soup.find_all("div", class_="result")[:3]:
                        title = res.find("a", class_="result__a")
                        snippet = res.find("a", class_="result__snippet")
                        if title and snippet:
                            results.append(f"• {title.get_text().strip()}: {snippet.get_text().strip()}")
                    
                    if results:
                        summary = "\n".join(results)
                        await agent_logger.log("Browser", "Fallback de búsqueda exitoso.")
                        return {
                            "success": True,
                            "result": f"[BÚSQUEDA TRADICIONAL - FALLBACK]\n\n{summary}",
                            "agent": "duckduckgo_fallback"
                        }
            
            return {"success": False, "error": "No se encontraron resultados en el fallback de búsqueda."}
        except Exception as e:
            return {"success": False, "error": f"Error crítico en fallback: {str(e)}"}

    async def close(self):
        if getattr(self, "_browser", None) is not None:
            try:
                await self._browser.close()
            except:
                pass
            self._browser = None


# Instancia global
browser_agent = BrowserAgent()


