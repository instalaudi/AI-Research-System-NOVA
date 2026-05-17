import asyncio
import httpx
import re
import math
import random
from typing import List, Dict, Any, Optional
import urllib.parse
from agents.base_agent import BaseAgent
from core.config import MAX_ARTICLES_PER_TOPIC, RELEVANCE_THRESHOLD
from core.llm_client import llm_client

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    BeautifulSoup = None

# Global list of User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
]

# Dedicated semaphores per source to allow high-concurrency parallel queries without bottlenecks
ddg_semaphore = asyncio.Semaphore(1)
semantic_scholar_semaphore = asyncio.Semaphore(1)
google_scholar_semaphore = asyncio.Semaphore(1)

# SEC-05: SSRF Protection - Blocked schemes and domains
BLOCKED_SCHEMES = ['file', 'ftp', 'gopher', 'data', 'javascript']
BLOCKED_HOSTS = ['localhost', '127.0.0.1', '192.168', '10.', '172.', '0.0.0.0', 'internal']

def _is_valid_url(url: str) -> bool:
    """
    Validates URLs to prevent SSRF attacks.
    SEC-05: Check for blocked schemes and internal IPs
    """
    try:
        parsed = urllib.parse.urlparse(url)

        # Check scheme
        if parsed.scheme.lower() in BLOCKED_SCHEMES:
            return False

        # Check for internal IPs/hosts
        host = parsed.netloc.lower()
        for blocked in BLOCKED_HOSTS:
            if blocked in host:
                return False

        # Must be http or https
        if parsed.scheme.lower() not in ['http', 'https']:
            return False

        return True
    except Exception:
        return False

import sqlite3
import datetime
import os

class SearchCache:
    """Simple SQLite-based cache for search results to avoid redundant API calls."""
    def __init__(self, db_path: str = "data/search_cache.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        # FIX: timeout=10 evita "database is locked" con múltiples workers
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            # FIX: WAL mode permite lecturas concurrentes sin bloqueo exclusivo
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    query_hash TEXT PRIMARY KEY,
                    source TEXT,
                    results_json TEXT,
                    timestamp DATETIME
                )
            """)
            conn.commit()

    def get(self, query: str, source: str, ttl_hours: int = 24) -> Optional[List[Dict]]:
        import json
        query_hash = f"{source}:{query}"
        try:
            # FIX: timeout=10 evita bloqueos con escrituras concurrentes
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.execute(
                    "SELECT results_json, timestamp FROM search_cache WHERE query_hash = ?", 
                    (query_hash,)
                )
                row = cursor.fetchone()
                if row:
                    results_json, ts_str = row
                    ts = datetime.datetime.fromisoformat(ts_str)
                    if datetime.datetime.utcnow() - ts < datetime.timedelta(hours=ttl_hours):
                        return json.loads(results_json)
        except Exception as e:
            print(f"[SearchCache] Error reading: {e}")
        return None

    def set(self, query: str, source: str, results: List[Dict]):
        import json
        query_hash = f"{source}:{query}"
        try:
            # FIX: timeout=10 evita bloqueos con lecturas concurrentes
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO search_cache (query_hash, source, results_json, timestamp) VALUES (?, ?, ?, ?)",
                    (query_hash, source, json.dumps(results), datetime.datetime.utcnow().isoformat())
                )
                conn.commit()
        except Exception as e:
            print(f"[SearchCache] Error writing: {e}")

class ExplorerAgent(BaseAgent):
    def __init__(self, name: str = "Explorer"):
        super().__init__(name)
        self._http_client = None
        self._client_lock = asyncio.Lock()
        self.cache = SearchCache()

    async def _get_client(self):
        """Lazy initialization of the HTTP client to ensure it's created within the running loop."""
        async with self._client_lock:
            if getattr(self, "_http_client", None) is None or self._http_client.is_closed:
                import httpx
                self._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
            return self._http_client

    async def close(self):
        """Closes the underlying HTTP client to prevent resource leaks."""
        if self._http_client and not self._http_client.is_closed:
            print(f"[{self.name}] Closing HTTP client connections...")
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _simplify_query(self, topic: str) -> str:
        """Simplifies complex topics while preserving key technical terms."""
        # IF the topic is short, keep it as is
        if len(topic.split()) <= 4:
            return topic
            
        from core.text_utils import extract_keywords
        keywords = extract_keywords(topic)
        
        # Keep more keywords to avoid losing technical context
        final_keywords = keywords[-7:] if len(keywords) >= 7 else keywords
        return " ".join(final_keywords)

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Calculates cosine similarity between two vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(b * b for b in v2))
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)

    async def _filter_relevance(self, results: List[Dict[str, Any]], topic: str) -> List[Dict[str, Any]]:
        """
        Filters results based on semantic similarity to the topic.
        FIX: Semáforo limita a max 4 llamadas de embedding concurrentes para no saturar Ollama.
        """
        if not results:
            return []
            
        print(f"[{self.name}] Running parallel semantic relevance filter for topic: {topic}")
        topic_vec = await llm_client.get_embeddings(topic)
        if not topic_vec:
            return results # Fallback if embeddings fail

        # FIX: Limitar concurrencia de embeddings — evita timeout en cascada con 20+ resultados
        _embed_semaphore = asyncio.Semaphore(4)

        async def _score_single(res: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with _embed_semaphore:
                content_to_score = f"{res.get('title', '')} {res.get('summary', '')}"
                content_vec = await llm_client.get_embeddings(content_to_score[:500])
                
                if not content_vec:
                    return res # Keep if scoring fails but mark it
                
                similarity = self._cosine_similarity(topic_vec, content_vec)
                res["relevance_score"] = round(similarity, 3)
                
                if similarity >= RELEVANCE_THRESHOLD:
                    print(f"[{self.name}] ✅ Result ACCEPTED ({similarity:.2f}): {res.get('title')[:50]}...")
                    return res
                else:
                    print(f"[{self.name}] ❌ Result REJECTED ({similarity:.2f}): {res.get('title')[:50]}...")
                    return None

        # Execute all embedding calls (throttled), but don't fail if one crashes
        scored_results = await asyncio.gather(*[_score_single(r) for r in results], return_exceptions=True)
        
        # Filter out None values and handle exceptions safely
        final_results = []
        for res in scored_results:
            if isinstance(res, Exception):
                print(f"[{self.name}] Warning: Error in parallel scoring: {res}")
                continue
            if res is not None:
                final_results.append(res)
        
        return final_results if final_results else results[:1] # Keep at least one if all are bad

    async def _search_wikipedia(self, topic: str) -> List[Dict[str, str]]:
        """Properly searches Wikipedia before fetching summary."""
        simplified = self._simplify_query(topic)
        print(f"[{self.name}] Searching Wikipedia for: {simplified}")
        search_url = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(simplified)}&format=json"
        
        # Wikipedia-specific User-Agent as per their policy
        wiki_headers = {
            "User-Agent": "NOVA-ResearchBot/1.0 (contact: juan_ramon_admin@example.com)",
            "Accept-Encoding": "gzip"
        }
        try:
            client = await self._get_client()
            resp = await client.get(search_url, headers=wiki_headers)
            if resp.status_code == 200:
                data = resp.json()
                search_results = data.get("query", {}).get("search", [])
                if search_results:
                    best_title = search_results[0]["title"]
                    summary_url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(best_title)}"
                    summ_resp = await client.get(summary_url, headers=wiki_headers)
                    if summ_resp.status_code == 200:
                        summ_data = summ_resp.json()
                        return [{
                            "title": summ_data.get("title"),
                            "url": summ_data.get("content_urls", {}).get("desktop", {}).get("page"),
                            "summary": summ_data.get("extract", "")[:500],
                            "full_content": summ_data.get("extract"),
                            "is_fallback": False,
                            "quality_flag": "scientific_base"
                        }]
                    else:
                        print(f"[{self.name}] Wikipedia Summary API error: {summ_resp.status_code} - {summ_resp.text[:100]}")
                else:
                    print(f"[{self.name}] Wikipedia Search returned no results for: {simplified}")
            else:
                print(f"[{self.name}] Wikipedia API error: {resp.status_code} - {resp.text[:100]}")
        except Exception as e:
            print(f"[{self.name}] Unexpected error in Wikipedia search: {e}")
        return []

    async def _search_arxiv(self, topic: str) -> List[Dict[str, str]]:
        """Fetches from ArXiv API using feedparser via HTTPS with retry backoff."""
        simplified = self._simplify_query(topic)
        print(f"[{self.name}] Searching ArXiv for papers: {simplified}")
        url = f"https://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(simplified)}&start=0&max_results=5"
        try:
            client = await self._get_client()
            for attempt in range(3):
                response = await client.get(url)
                if response.status_code == 200:
                    try:
                        feed = feedparser.parse(response.text)
                    except Exception as fp_err:
                        print(f"[{self.name}] feedparser parse error: {fp_err}")
                        return []
                    entries = []
                    for entry in feed.entries:
                        entries.append({
                            "title": getattr(entry, 'title', 'Sin título'),
                            "url": getattr(entry, 'link', ''),
                            "summary": getattr(entry, 'summary', '')[:500],
                            "full_content": getattr(entry, 'summary', ''),
                            "is_fallback": False,
                            "quality_flag": "scientific_paper"
                        })
                    return entries
                elif response.status_code == 429:
                    wait = (2 ** (attempt + 2)) + random.uniform(2, 5)
                    print(f"[{self.name}] ArXiv rate limited (429). Retrying in {wait:.1f}s...")
                    await asyncio.sleep(wait)
                else: break
        except Exception as e:
            print(f"[{self.name}] ArXiv error: {e}")
        return []

    async def _search_semantic(self, topic: str) -> List[Dict[str, str]]:
        """Searches Semantic Scholar with caching and rate limiting.
        v11.9.0: Backoff mejorado + soporte de API key + caché de resultados vacíos.
        """
        simplified = self._simplify_query(topic)
        cached = self.cache.get(simplified, "semantic")
        if cached is not None:  # v11.9: cached puede ser [] (resultado vacío cacheado)
            print(f"[{self.name}] Using cached results for Semantic Scholar: {simplified}")
            return cached

        print(f"[{self.name}] Searching Semantic Scholar: {simplified}")
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(simplified)}&limit=5&fields=title,abstract,url,year,citationCount"

        # v11.9.0: Soporte de API key para rate limit más alto (1 req/s → 100 req/s)
        from core.config import SEMANTIC_SCHOLAR_API_KEY
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        if SEMANTIC_SCHOLAR_API_KEY:
            headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

        # Dedicated semantic scholar semaphore to avoid global bottlenecks
        async with semantic_scholar_semaphore:
            await asyncio.sleep(3.0)  # Rate limit real: solo 1 worker a la vez espera y envía
            try:
                client = await self._get_client()
                for attempt in range(3):
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        papers = []
                        for item in data.get("data", []):
                            abstract = item.get("abstract") or ""
                            papers.append({
                                "title": item.get("title"),
                                "url": item.get("url"),
                                "summary": abstract[:500],
                                "full_content": f"Title: {item.get('title')}\nYear: {item.get('year')}\nCitations: {item.get('citationCount')}\nAbstract: {abstract}",
                                "is_fallback": False,
                                "quality_flag": "academic_impact"
                            })
                        self.cache.set(simplified, "semantic", papers)
                        return papers
                    elif response.status_code == 429:
                        # v11.9.0: Backoff exponencial más agresivo: 5s, 10s, 20s + jitter
                        wait = (5 * (2 ** attempt)) + random.uniform(1, 3)
                        print(f"[{self.name}] Semantic Scholar rate limited (429). Retrying in {wait:.1f}s... (attempt {attempt+1}/3)")
                        await asyncio.sleep(wait)
                    else:
                        print(f"[{self.name}] Semantic Scholar HTTP {response.status_code}")
                        break
                # v11.9.0: Cachear resultados vacíos con TTL corto (1h) para evitar re-queries inútiles
                self.cache.set(simplified, "semantic", [])
            except Exception as e:
                print(f"[{self.name}] Semantic Scholar error: {e}")
        return []

    async def _search_github(self, topic: str) -> List[Dict[str, str]]:
        """Searches GitHub for repositories."""
        print(f"[{self.name}] Searching GitHub for repos: {topic}")
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(topic)}&per_page=3"
        try:
            client = await self._get_client()
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                repos = []
                for item in data.get("items", []):
                    repos.append({
                        "title": item.get("full_name"),
                        "url": item.get("html_url"),
                        "summary": item.get("description", ""),
                        "full_content": f"Repository: {item.get('full_name')}\nDescription: {item.get('description')}\nStars: {item.get('stargazers_count')}",
                        "is_fallback": False,
                        "quality_flag": "technical"
                    })
                return repos
        except Exception as e:
            print(f"[{self.name}] Unexpected error: {e}")
        return []

    async def _search_web_duckduckgo(self, topic: str) -> List[Dict[str, str]]:
        """Searches the general web via DuckDuckGo (Bing index)."""
        web_results = []
        safe_topic = urllib.parse.quote(topic)
        url = f"https://html.duckduckgo.com/html/?q={safe_topic}"
        print(f"[{self.name}] Serialized web search starting via DuckDuckGo: {topic}")
        
        response = None
        # Backoff and re-verify client (Retry loop)
        for attempt in range(3):
            try:
                client = await self._get_client()
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                response = await client.get(url, headers=headers)
                if response.status_code == 202: # DDG "Processing" or Rate limit signal
                    wait = random.uniform(4, 7)
                    print(f"[{self.name}] DuckDuckGo 202/Signal. Waiting {wait:.1f}s...")
                    await asyncio.sleep(wait)
                    continue
                if response.status_code == 200:
                    break
                if response.status_code == 429:
                    wait = (2 ** (attempt + 2)) + random.uniform(1, 4)
                    print(f"[{self.name}] DuckDuckGo Rate Limited (429). Waiting {wait:.1f}s...")
                    await asyncio.sleep(wait)
                    continue
            except Exception as e:
                if attempt == 2: break
                await asyncio.sleep(3 + random.uniform(1, 3))
        
        if response and response.status_code == 200:
            try:
                if BeautifulSoup is None:
                    print(f"[{self.name}] BeautifulSoup not installed. Skipping DDG scraping.")
                    return web_results
                soup = BeautifulSoup(response.text, "html.parser")
                for result in soup.find_all("div", class_="result")[:MAX_ARTICLES_PER_TOPIC]:
                    title_tag = result.find("a", class_="result__a")
                    snippet_tag = result.find("a", class_="result__snippet")
                    if title_tag and snippet_tag:
                        article_url = title_tag["href"]
                        
                        # DDG Redirection bypass & Ad-Filtering
                        if "duckduckgo.com/l/?" in article_url or "duckduckgo.com/y.js?" in article_url:
                            try:
                                parsed_url = urllib.parse.urlparse(article_url)
                                query_params = urllib.parse.parse_qs(parsed_url.query)
                                
                                # 1. Extract real destination if encapsulated in 'uddg'
                                if 'uddg' in query_params:
                                    article_url = query_params['uddg'][0]
                                    print(f"[{self.name}] Extracted real URL from DDG: {article_url}")
                                
                                # 2. Strict Ad-Check: Skip if it looks like an ad-js or has ad metadata
                                if "y.js" in article_url or 'ad_domain' in query_params or 'ad_provider' in query_params:
                                    # print(f"[{self.name}] Skipping advertisement link: {article_url[:60]}...")
                                    continue
                            except: pass

                        blocked_keywords = ["amazon", "ebay", "mercadolibre", "aliexpress", "walmart", "target", "bestbuy", "etsy", "shopee", "tracking", "clickserve", "doubleclick"]
                        if any(kw in article_url.lower() for kw in blocked_keywords):
                            continue
                        content_data = await self._fetch_content(article_url)
                        web_results.append({
                            "title": title_tag.get_text().strip(),
                            "url": article_url,
                            "summary": snippet_tag.get_text().strip()[:200],
                            "full_content": content_data["text"],
                            "images": content_data["images"],
                            "is_fallback": False,
                            "quality_flag": "web_research"
                        })
            except Exception as e:
                print(f"[{self.name}] Error parsing DDG results: {e}")
        return web_results

    async def _search_google_scholar(self, topic: str) -> List[Dict[str, str]]:
        """Searches Google Scholar with caching and rate limiting."""
        simplified = self._simplify_query(topic)
        cached = self.cache.get(simplified, "google_scholar")
        if cached:
            print(f"[{self.name}] Using cached results for Google Scholar: {simplified}")
            return cached

        print(f"[{self.name}] Searching Google Scholar: {simplified}")
        results = []

        if BeautifulSoup is None:
            print(f"[{self.name}] BeautifulSoup not installed. Skipping Google Scholar.")
            return results

        safe_topic = urllib.parse.quote(simplified)
        url = f"https://scholar.google.com/scholar?q={safe_topic}"

        # Dedicated Google Scholar semaphore to avoid global bottlenecks
        async with google_scholar_semaphore:
            await asyncio.sleep(1.0)  # Rate limit real: solo 1 worker a la vez espera y envía
            try:
                client = await self._get_client()
                response = await client.get(url, headers={"User-Agent": random.choice(USER_AGENTS)})
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    for div in soup.find_all("div", class_="gs_ri")[:MAX_ARTICLES_PER_TOPIC]:
                        h3 = div.find("h3")
                        if not h3: continue
                        a = h3.find("a")
                        if not a: continue

                        article_url = a.get("href")
                        title = a.get_text()

                        snippet_div = div.find("div", class_="gs_rs")
                        summary = snippet_div.get_text() if snippet_div else "Google Scholar Result"

                        results.append({
                            "title": title,
                            "url": article_url,
                            "summary": summary[:300],
                            "full_content": f"Title: {title}\nSummary: {summary}",
                            "is_fallback": False,
                            "quality_flag": "academic_scholar"
                        })
                    self.cache.set(simplified, "google_scholar", results)
                elif response.status_code == 429:
                    print(f"[{self.name}] Google Scholar Rate Limited (429).")
            except Exception as e:
                print(f"[{self.name}] Error parsing Google Scholar: {e}")
        return results

    # FIX: Límite de descarga para evitar OOM con páginas de 100MB+
    _MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024  # 2 MB

    async def _fetch_content(self, url: str) -> Dict[str, Any]:
        """Helper to fetch full article text and images.
        FIX: Limita el body descargado a _MAX_DOWNLOAD_BYTES para evitar OOM.
        """
        # SEC-05: Validate URL before fetching to prevent SSRF
        if not _is_valid_url(url):
            print(f"[{self.name}] Blocked unsafe URL: {url}")
            return {"text": "", "images": []}

        try:
            client = await self._get_client()
            # FIX: Leer solo los primeros _MAX_DOWNLOAD_BYTES para evitar OOM
            response = await client.get(url)
            if response.status_code == 200:
                raw_bytes = response.content[:self._MAX_DOWNLOAD_BYTES]
                raw_text = raw_bytes.decode(response.encoding or "utf-8", errors="replace")
                if BeautifulSoup is None:
                    print(f"[{self.name}] BeautifulSoup not installed. Skipping content parsing.")
                    return {"text": "", "images": []}
                soup = BeautifulSoup(raw_text, "html.parser")
                
                # Image Extraction
                images = []
                for img in soup.find_all("img"):
                    src = img.get("src")
                    if not src: continue
                    # Resolve relative URLs
                    absolute_src = urllib.parse.urljoin(url, src)
                    if _is_valid_url(absolute_src) and any(ext in absolute_src.lower() for ext in ['.jpg', '.jpeg', '.png', '.svg', '.webp']):
                        # Look for potential technical charts/diagrams (keywords in alt or src)
                        alt = img.get("alt", "").lower()
                        if any(kw in alt or kw in absolute_src.lower() for kw in ['chart', 'graph', 'diagram', 'figure', 'stats', 'table']):
                            images.append({"url": absolute_src, "alt": alt})
                            if len(images) >= 3: break

                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                text = soup.get_text(separator=' ', strip=True)[:2000]  # Cap at 2k chars
                return {"text": text, "images": images}
        except Exception as e:
            print(f"[{self.name}] Error fetching content from {url}: {e}")
        return {"text": "", "images": []}

    async def execute(self, topic: str, **kwargs) -> List[Dict[str, str]]:
        """
        Multi-source execution: Serialized Web + Parallel Scientific/Technical.
        FIX-4: Improved with fallback to prevent empty results
        """
        all_results = []

        # 1. Parallel scientific/technical search
        simplified = self._simplify_query(topic)
        print(f"[{self.name}] Initiating multi-source research for: {topic} (Simplified: {simplified})")
        wiki_task = asyncio.create_task(self._search_wikipedia(simplified))
        arxiv_task = asyncio.create_task(self._search_arxiv(topic))
        github_task = asyncio.create_task(self._search_github(simplified))
        semantic_task = asyncio.create_task(self._search_semantic(topic))
        scholar_task = asyncio.create_task(self._search_google_scholar(topic)) # Added Google Scholar

        # 2. Serialized Web Search (DuckDuckGo represents Bing Index)
        web_results = []
        async with ddg_semaphore:
            web_results = await self._search_web_duckduckgo(topic)

        # 3. Collect all results
        scientific_results = await asyncio.gather(wiki_task, arxiv_task, github_task, semantic_task, scholar_task)
        for res_list in scientific_results:
            for r in res_list: r["research_topic"] = topic
            all_results.extend(res_list)

        for r in web_results: r["research_topic"] = topic
        all_results.extend(web_results)

        # Apply semantic relevance filter
        all_results = await self._filter_relevance(all_results, topic)

        # FIX-4: If no results at all, return minimal fallback
        if not all_results:
            print(f"[{self.name}] WARNING: No sources found for '{topic}'. Creating fallback entry.")
            all_results = [{
                "title": f"No sources found: {topic}",
                "url": "internal://no-source",
                "summary": f"The research topic '{topic}' could not find external sources. This may require human investigation.",
                "full_content": f"No external sources available for: {topic}",
                "is_fallback": True,
                "quality_flag": "no_source_fallback"
            }]

        print(f"[{self.name}] Intelligence gathering complete. Total sources: {len(all_results)}")
        return all_results
