"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v10.1 — Router de Telemetría                           ║
║  Archivo: routers/metrics.py                                 ║
║  Endpoints: GET /metrics (JSON) + GET /metrics/html (vista)  ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse

from core.auth import get_current_admin
from core.telemetry import nova_telemetry  # type: ignore

router = APIRouter(prefix="/metrics", tags=["telemetry"])


# ════════════════════════════════════════════════════════════════
#  JSON ENDPOINT
# ════════════════════════════════════════════════════════════════

@router.get("", summary="Métricas del sistema NOVA en tiempo real", dependencies=[Depends(get_current_admin)])
async def get_metrics():
    """
    Devuelve un snapshot completo del estado de NOVA:
    - workers activos / ocupados / idle
    - latencia por modelo LLM (avg + p95)
    - cache hit rate de embeddings
    - confianza promedio del conocimiento (evolución diaria)
    - estado de Ollama (/api/tags)
    - uptime del proceso
    """
    snapshot = await nova_telemetry.get_snapshot()
    return JSONResponse(content=snapshot)


# ════════════════════════════════════════════════════════════════
#  HTML DASHBOARD (para debug visual desde el navegador)
# ════════════════════════════════════════════════════════════════

@router.get("/html", response_class=HTMLResponse,
            summary="Dashboard de telemetría (vista navegador)",
            dependencies=[Depends(get_current_admin)])
async def get_metrics_html():
    """
    v10.13.0: Edición 'Ultra-Light' & Asíncrona. 
    Optimizado para Ryzen iGPU (0% GPU Lag). Actualización vía JS Fetch.
    """
    snapshot = await nova_telemetry.get_snapshot()
    from core.config import OLLAMA_NUM_THREAD

    # Helper para renderizado inicial de modelos
    llm_data = snapshot.get("llm", {})
    models_rows = "".join([
        f"<tr><td><code>{k}</code></td><td id='model-{k}-lat'>{v['avg_latency_ms']} ms</td><td id='model-{k}-calls'>{v['calls_total']}</td></tr>" 
        for k,v in llm_data.get('models', {}).items()
    ]) or "<tr><td colspan='3'>No hay modelos activos</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NOVA — Command Center v12.0.0</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=JetBrains+Mono:wght@400;700&display=swap');
        
        :root {{
            --bg: #03060a;
            --card-bg: #161b22; /* Sólido para evitar GPU Lag */
            --border: #30363d;
            --primary: #58a6ff;
            --success: #3fb950;
            --error: #f85149;
            --text: #e6edf3;
            --text-muted: #8b949e;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', system-ui, sans-serif;
            background: var(--bg);
            background-image: radial-gradient(circle at 50% -20%, #111827 0%, #03060a 100%);
            color: var(--text);
            padding: 20px;
            min-height: 100vh;
            overflow-x: hidden;
        }}

        header {{
            display: flex; justify-content: space-between; align-items: center;
            padding-bottom: 15px; border-bottom: 1px solid var(--border); margin-bottom: 25px;
        }}
        .brand {{ display: flex; align-items: center; gap: 12px; }}
        .brand .icon {{ width: 28px; height: 28px; background: var(--primary); border-radius: 6px; box-shadow: 0 0 10px var(--primary); }}
        .brand h1 {{ font-size: 18px; font-weight: 600; }}

        .main-layout {{ display: grid; grid-template-columns: 1fr 320px; gap: 20px; }}
        @media (max-width: 900px) {{ .main-layout {{ grid-template-columns: 1fr; }} }}

        .grid-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 15px; }}

        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px;
        }}
        .card h2 {{
            font-size: 10px; font-weight: 600; color: var(--text-muted);
            text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;
            display: flex; align-items: center; gap: 6px;
        }}

        .stat-row {{
            display: flex; justify-content: space-between; padding: 6px 0;
            border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 13px;
        }}
        .update-flash {{ animation: flash 0.5s ease-out; }}
        @keyframes flash {{ from {{ color: var(--primary); }} to {{ color: inherit; }} }}

        .value {{ font-weight: 600; font-family: 'JetBrains Mono', monospace; }}
        
        /* Swarm Monitor */
        #swarm-container {{ display: flex; flex-direction: column; gap: 8px; }}
        .activity-item {{
            background: rgba(255,255,255,0.02); border: 1px solid var(--border);
            border-radius: 6px; padding: 10px; display: flex; align-items: center; gap: 10px;
        }}
        .pulse {{ width: 8px; height: 8px; background: var(--success); border-radius: 50%; }}
        .working {{ animation: pulse-anim 2s infinite; }}
        @keyframes pulse-anim {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}

        table {{ width: 100%; font-size: 12px; border-collapse: collapse; }}
        th {{ text-align: left; color: var(--text-muted); padding: 6px; border-bottom: 1px solid var(--border); }}
        td {{ padding: 8px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); }}

        .footer {{ margin-top: 30px; text-align: center; font-size: 11px; color: var(--text-muted); opacity: 0.7; }}
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <div class="icon"></div>
            <h1>NOVA <span style="color:var(--text-muted)">Command Center</span></h1>
        </div>
        <div id="uptime" style="font-size:12px; color:var(--primary)">Uptime: {snapshot.get('uptime', {}).get('uptime_human')}</div>
    </header>

    <div class="main-layout">
        <div class="left-col">
            <div class="grid-stats">
                <div class="card">
                    <h2>⚙️ Infraestructura</h2>
                    <div class="stat-row"><span class="label">Threads Activos</span><span class="value" id="val-total-workers">{OLLAMA_NUM_THREAD}</span></div>
                 <div class="stat-row"><span class="label">Tareas en Ejecución</span><span class="value" id="val-busy" style="color:var(--primary)">{snapshot.get('workers', {}).get('busy', 0)}</span></div>
                    <div class="stat-row"><span class="label">En Cola</span><span class="value" id="val-queue">{snapshot.get('workers', {}).get('queue_size', 0)}</span></div>
                </div>

                <div class="card">
                    <h2>🧠 Neural Bridge</h2>
                    <div class="stat-row"><span class="label">Estado Ollama</span><span id="val-ollama-status" style="font-weight:bold; color:var(--success)">{snapshot.get('ollama', {}).get('status', 'offline')}</span></div>
                    <div class="stat-row"><span class="label">Latencia Base</span><span class="value" id="val-ollama-lat">{snapshot.get('ollama', {}).get('latency_ms', 0)} ms</span></div>
                    <div class="stat-row"><span class="label">Cache Hit Rate</span><span class="value" id="val-cache-hit">{snapshot.get('llm', {}).get('cache_hit_rate', 0)*100:.1f}%</span></div>
                </div>

                <div class="card">
                    <h2>📊 Ontología</h2>
                    <div class="stat-row"><span class="label">Entidades</span><span class="value" id="val-knowledge">{snapshot.get('knowledge', {}).get('total_articles', 0):,}</span></div>
                    <div class="stat-row"><span class="label">Confianza Media</span><span class="value" id="val-conf" style="color:var(--success)">{snapshot.get('knowledge', {}).get('avg_confidence_score', 0)*100:.1f}%</span></div>
                </div>
            </div>

            <div class="card" style="margin-top: 20px">
                <h2>📡 Modelos Activos</h2>
                <table id="models-table">
                    <thead><tr><th>Modelo</th><th>Latencia</th><th>Llamadas</th></tr></thead>
                    <tbody id="models-body">{models_rows}</tbody>
                </table>
            </div>
        </div>

        <div class="right-col">
            <div class="card">
                <h2>🔥 Swarm Activity</h2>
                <div id="swarm-container">
                    <div style='color:var(--text-muted);text-align:center;padding:10px'>Cargando actividad...</div>
                </div>
            </div>

            <div class="card" style="margin-top: 20px">
                <h2>🔋 Recursos iGPU</h2>
                <div class="stat-row"><span class="label">Modo</span><span class="value" style="color:var(--success)">Ultra-Light</span></div>
                <div class="stat-row"><span class="label">Refresh</span><span class="value">Async (Every 15s)</span></div>
            </div>
        </div>
    </div>

    <div class="footer">
        Generado: <span id="val-gen-at">{snapshot.get('generated_at')}</span> · Version: v12.0.0 · <a href="/api/metrics" style="color:var(--primary); text-decoration:none">JSON API ↗</a>
    </div>

    <script>
        async function updateMetrics() {{
            try {{
                const res = await fetch("/api/metrics");
                const data = await res.json();
                
                // Actualizar valores simples
                document.getElementById('uptime').innerText = "Uptime: " + data.uptime.uptime_human;
                document.getElementById('val-busy').innerText = data.workers.busy;
                document.getElementById('val-queue').innerText = data.workers.queue_size;
                document.getElementById('val-ollama-status').innerText = data.ollama.status;
                document.getElementById('val-ollama-lat').innerText = data.ollama.latency_ms + " ms";
                document.getElementById('val-cache-hit').innerText = (data.llm.cache_hit_rate * 100).toFixed(1) + "%";
                document.getElementById('val-knowledge').innerText = data.knowledge.total_articles.toLocaleString();
                document.getElementById('val-conf').innerText = (data.knowledge.avg_confidence_score * 100).toFixed(1) + "%";
                document.getElementById('val-gen-at').innerText = data.generated_at;

                // Actualizar Swarm Activity
                const swarm = document.getElementById('swarm-container');
                const activity = data.knowledge.tasks.live_activity || [];
                if (activity.length === 0) {{
                    swarm.innerHTML = "<div style='color:#8b949e;text-align:center;padding:10px'>Esperando tareas... 💤</div>";
                }} else {{
                    swarm.innerHTML = activity.map(job => `
                        <div class="activity-item">
                            <div class="pulse working"></div>
                            <div style="display:flex; flex-direction:column; gap:2px">
                                <strong style="font-size:12px">${{job.topic.substring(0,35)}}...</strong>
                                <span style="font-size:10px; color:#8b949e">Fase: ${{job.stage}}</span>
                            </div>
                        </div>
                    `).join('');
                }}

                // Actualizar Tabla de Modelos
                const modelsBody = document.getElementById('models-body');
                const models = data.llm.models || {{}};
                const modelKeys = Object.keys(models);
                if (modelKeys.length === 0) {{
                     modelsBody.innerHTML = "<tr><td colspan='3'>No hay modelos activos</td></tr>";
                }} else {{
                    modelsBody.innerHTML = modelKeys.map(k => `
                        <tr>
                            <td><code>${{k}}</code></td>
                            <td>${{models[k].avg_latency_ms}} ms</td>
                            <td>${{models[k].calls_total}}</td>
                        </tr>
                    `).join('');
                }}

            }} catch (e) {{ console.error("Update failed", e); }}
        }}

        // Iniciar bucle asíncrono
        setInterval(updateMetrics, 15000);
        updateMetrics(); // Primera carga inmediata
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)
