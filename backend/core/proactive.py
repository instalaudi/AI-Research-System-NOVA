"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v10.0 — Sistema Proactivo                              ║
║  Archivo: core/proactive.py                                  ║
║                                                              ║
║  NOVA actúa por iniciativa propia y te contacta cuando       ║
║  descubre algo importante — sin que tú le pidas nada.        ║
║                                                              ║
║  Requiere en .env:                                           ║
║    TELEGRAM_TOKEN=tu_token_del_bot                           ║
║    TELEGRAM_CHAT_ID=tu_chat_id                               ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import json
import asyncio
import datetime
import traceback
import random
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx
import psutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

from core.llm_client import llm_client
from core.database import SessionLocal, KnowledgeEntry, ResearchJob, ChatLog


# ── Configuración de Telegram ─────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── Horarios en que NOVA puede contactarte ────────────────────────
QUIET_HOURS_START = int(os.getenv("NOVA_QUIET_START", "23"))  # 11pm
QUIET_HOURS_END   = int(os.getenv("NOVA_QUIET_END",   "7"))   # 7am
MAX_MESSAGES_DAY  = int(os.getenv("NOVA_MAX_MESSAGES", "10"))  # máximo 10 mensajes al día


class NOVAProactiveSystem:
    """
    Sistema proactivo de NOVA.

    NOVA monitorea su entorno continuamente y te contacta
    cuando encuentra algo que vale la pena compartir.
    No espera órdenes — actúa como una colaboradora real.
    """

    # Errores de red conocidos (DNS, conexión, etc.)
    _NETWORK_ERRORS = (
        "getaddrinfo failed",
        "Name or service not known",
        "nodename nor servname",
        "NameResolutionError",
        "ConnectError",
        "NetworkUnreachable",
        "No address associated",
        "Max retries exceeded",
        "ConnectionRefusedError",
    )

    def __init__(self):
        self._messages_today = 0
        self._last_message_date = None
        self._pending_responses: Dict[str, Any] = {}
        self._initiative_log = []
        self._state_file = Path("data/nova_proactive_state.json")
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._last_update_id = 0
        # ── Resilencia de red ──
        self._is_offline = False
        self._offline_logged = False  # Evitar spam de logs
        self._consecutive_net_errors = 0
        self._poll_backoff = 1  # segundos, crece exponencialmente
        self._MAX_POLL_BACKOFF = 300  # máx 5 minutos
        self._load_state()

    def _is_network_error(self, error) -> bool:
        """Detecta si un error es causado por falta de conectividad."""
        err_str = str(error)
        return any(ne in err_str for ne in self._NETWORK_ERRORS)

    def _handle_network_error(self, context: str = "polling"):
        """Manejo centralizado de errores de red — log una sola vez."""
        self._consecutive_net_errors += 1
        self._is_offline = True
        # Backoff exponencial: 1, 2, 4, 8, 16, 32, 64, 128, 256, 300 (cap)
        self._poll_backoff = min(self._poll_backoff * 2, self._MAX_POLL_BACKOFF)
        if not self._offline_logged:
            print(f"[PROACTIVE] ⚠️ Sin conexión a internet — {context} pausado "
                  f"(backoff: {self._poll_backoff}s). Reintentando periódicamente...")
            self._offline_logged = True

    def _handle_network_recovery(self):
        """Se llama cuando la conexión se restaura."""
        if self._is_offline:
            print(f"[PROACTIVE] ✅ Conexión a internet restaurada después de "
                  f"{self._consecutive_net_errors} errores")
        self._is_offline = False
        self._offline_logged = False
        self._consecutive_net_errors = 0
        self._poll_backoff = 1

    def _to_html(self, text: str) -> str:
        """Convierte Markdown básico a HTML seguro para Telegram, con cierre forzado de etiquetas."""
        if not text:
            return ""
        
        # 1. Escapar HTML básico
        html = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        # 2. Convertir Markdown (Regex más seguras)
        html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)
        html = re.sub(r'\*(.*?)\*', r'<b>\1</b>', html)
        html = re.sub(r'_(.*?)_', r'<i>\1</i>', html)
        html = re.sub(r'`(.*?)`', r'<code>\1</code>', html)
        
        # 3. Cierre forzado de etiquetas (prevención de errores API Telegram)
        for tag in ['b', 'i', 'code']:
            open_tags = html.count(f'<{tag}>')
            close_tags = html.count(f'</{tag}>')
            if open_tags > close_tags:
                html += f'</{tag}>' * (open_tags - close_tags)
        
        return html

    # ══════════════════════════════════════════════════════════
    #  ENVÍO DE MENSAJES A TELEGRAM
    # ══════════════════════════════════════════════════════════

    async def notify(
        self,
        message:    str,
        buttons:    List[Dict] = None,
        initiative: str = "general"
    ) -> bool:
        """
        NOVA te envía un mensaje a Telegram.
        Respeta el horario de silencio y el límite diario.
        """
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            print(f"[PROACTIVE] Telegram no configurado — mensaje: {message[:50]}")
            return False

        # Iniciativas que son respuestas explícitas del usuario SIEMPRE deben pasar sin importar la hora o límite
        es_respuesta_directa = initiative in ["telegram_chat", "direct_reply", "callback_response", "error", "introspection", "diagnostic_report", "manual"]

        # Verificar horario de silencio
        if not self._is_good_time() and not es_respuesta_directa:
            print(f"[PROACTIVE] Horario de silencio — mensaje guardado para después")
            self._queue_for_later(message, buttons, initiative)
            return False

        # Verificar límite diario
        self._reset_daily_counter()
        if self._messages_today >= MAX_MESSAGES_DAY and not es_respuesta_directa:
            print(f"[PROACTIVE] 🛑 Límite diario alcanzado ({MAX_MESSAGES_DAY}). Mensaje omitido: {message[:50]}...")
            return False

        # Truncamiento de seguridad vs Documento (.txt)
        if len(message) > 4000:
            print(f"[PROACTIVE] Mensaje muy largo ({len(message)}), enviando como documento .txt")
            return await self._send_as_document(message, initiative)

        # Construir payload de Telegram
        safe_message = self._to_html(message)
        payload = {
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       f"🌟 <b>NOVA</b>\n\n{safe_message}",
            "parse_mode": "HTML",
        }

        # Agregar botones inline si se especifican
        if buttons:
            keyboard = {
                "inline_keyboard": [
                    [{"text": btn["text"], "callback_data": btn["data"]}]
                    for btn in buttons
                ]
            }
            payload["reply_markup"] = json.dumps(keyboard)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{TELEGRAM_API}/sendMessage",
                    json=payload
                )
                if r.status_code == 200:
                    self._messages_today += 1
                    self._initiative_log.append({
                        "type":      initiative,
                        "message":   message[:100],
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                        "delivered": True
                    })
                    self._save_state()
                    print(f"[PROACTIVE] ✅ Mensaje enviado a Juan Ramón. (Longitud: {len(message)} chars)")
                    return True
                else:
                    print(f"[PROACTIVE] Error Telegram {r.status_code}: {r.text[:100]}")
                    return False

        except Exception as e:
            if self._is_network_error(e):
                self._handle_network_error("envío de mensaje")
            else:
                print(f"[PROACTIVE] Error enviando mensaje: {e}")
            return False

    async def send_voice_notification(
        self,
        text: str,
        initiative: str = "general"
    ) -> bool:
        """
        Envía notificación de texto Y audio de voz.
        NOVA te habla directamente en Telegram.
        """
        # Primero enviar texto
        await self.notify(text, initiative=initiative)

        # Luego generar y enviar audio
        try:
            from core.tts_engine import nova_voice
            audio = await nova_voice.synthesize(text[:300])
            if audio and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    r = await client.post(
                        f"{TELEGRAM_API}/sendVoice",
                        data={"chat_id": TELEGRAM_CHAT_ID},
                        files={"voice": ("nova_voice.ogg", audio, "audio/ogg")}
                    )
                    if r.status_code == 200:
                        print(f"[PROACTIVE] ✅ Audio enviado a Juan Ramón")
                        return True
        except Exception as e:
            print(f"[PROACTIVE] Error enviando audio: {e}")

        return False

    # ══════════════════════════════════════════════════════════
    #  INICIATIVAS AUTÓNOMAS DE NOVA
    # ══════════════════════════════════════════════════════════

    async def check_and_act(self):
        """
        NOVA revisa su estado y decide si hay algo
        importante que compartir con Juan Ramón.
        Esto se ejecuta periódicamente en background.
        """
        if llm_client.busy_rate > 0.4:
            print(f"[PROACTIVE] ⏳ Saturación LLM crítica ({llm_client.busy_rate:.1%}). Pospusiendo revisión proactiva.")
            return 0

        print("[PROACTIVE] NOVA revisando si hay algo importante...")

        checks = [
            self._check_code_improvements(),
            self._check_new_technology(),
            self._check_knowledge_milestone(),
            self._check_failed_jobs(),
            self._check_curiosity_cycle(),  # Nueva Fase 9
            self._check_morning_briefing(),
            self._check_weekly_summary(),
        ]

        # Ejecutar todos los checks
        results = await asyncio.gather(*checks, return_exceptions=True)

        acted = sum(1 for r in results if r is True)
        print(f"[PROACTIVE] Revisión completada — {acted} iniciativas tomadas")
        return acted

    async def _check_code_improvements(self) -> bool:
        """
        NOVA analiza su propio código buscando mejoras.
        Si encuentra algo concreto, te lo dice.
        """
        # Solo hacer esto una vez por día
        if self._already_did_today("code_improvement"):
            return False

        try:
            from core.self_evolution import nova_self_evolution

            # Analizar el archivo más crítico
            files_to_check = [
                "core/orchestrator.py",
                "agents/explorer.py",
                "main.py"
            ]
            target = random.choice(files_to_check)
            analysis = await nova_self_evolution.analyze_own_file(target)

            if not analysis or len(analysis) < 100:
                return False

            # Preguntarle a NOVA si encontró algo realmente importante
            evaluation_prompt = f"""Analicé mi archivo {target} y obtuve esto:

{analysis[:1000]}

¿Hay algo REALMENTE importante o urgente aquí que valga la pena
contarle a Juan Ramón ahora mismo?

Responde SOLO en JSON:
{{
  "worth_notifying": true/false,
  "urgency": "alta/media/baja",
  "message": "mensaje conciso y directo para Juan Ramón (máx 150 chars)",
  "detail": "explicación técnica breve"
}}"""

            response = await llm_client.chat(
                [{"role": "user", "content": evaluation_prompt}],
                temperature=0.3
            )

            result = self._parse_json(response)
            if result and result.get("worth_notifying") and result.get("urgency") in ["alta", "media"]:
                msg = (
                    f"Analicé `{target}` y encontré algo:\n\n"
                    f"{result.get('message', '')}\n\n"
                    f"_{result.get('detail', '')}_"
                )
                await self.notify(
                    msg,
                    buttons=[
                        {"text": "📋 Ver detalle",  "data": f"detail_code_{target}"},
                        {"text": "✅ Implementar",  "data": f"implement_{target}"},
                        {"text": "⏭ Después",      "data": "postpone"},
                    ],
                    initiative="code_improvement"
                )
                self._mark_done_today("code_improvement")
                return True

        except Exception as e:
            print(f"[PROACTIVE] Error en check_code: {e}")

        return False

    async def _check_new_technology(self) -> bool:
        """
        NOVA busca tecnologías nuevas relevantes.
        Si encuentra algo emocionante, te lo cuenta.
        """
        if self._already_did_today("tech_discovery"):
            return False

        try:
            from core.self_evolution import nova_self_evolution

            # Buscar novedades
            tech_result = await nova_self_evolution.tech_watch()
            if not tech_result:
                return False

            tecnologias = tech_result.get("tecnologias", [])
            recomendadas = [
                t for t in tecnologias
                if t.get("recomendacion") == "implementar"
                and t.get("dificultad") in ["facil", "media"]
            ]

            if not recomendadas:
                return False

            mejor = recomendadas[0]
            msg = (
                f"Encontré algo que podría mejorarme:\n\n"
                f"*{mejor.get('nombre', '')}*\n"
                f"{mejor.get('relevancia_para_mi', '')[:150]}\n\n"
                f"Dificultad: {mejor.get('dificultad', '')} | "
                f"¿Lo implementamos?"
            )

            await self.notify(
                msg,
                buttons=[
                    {"text": "🚀 Sí, implementar", "data": f"implement_tech_{mejor.get('nombre','')}"},
                    {"text": "📖 Más info",         "data": f"info_tech_{mejor.get('nombre','')}"},
                    {"text": "⏭ Quizás después",   "data": "postpone"},
                ],
                initiative="tech_discovery"
            )
            self._mark_done_today("tech_discovery")
            return True

        except Exception as e:
            print(f"[PROACTIVE] Error en check_tech: {e}")

        return False

    async def notify_autonomous_research(self, topic: str, reason: str):
        """
        Informa a Juan Ramón que NOVA ha decidido investigar algo por su cuenta.
        """
        message = (
            f"He encontrado algo fascinante en mi vigilancia diaria:\n\n"
            f"🚀 *{topic}*\n"
            f"_{reason}_\n\n"
            f"He decidido iniciar una **investigación autónoma** para profundizar en esto. "
            f"Te contaré los detalles más tarde. 😊"
        )
        
        await self.notify(
            message,
            buttons=[
                {"text": "📖 Ver progreso", "data": "show_progress"},
                {"text": "👍 Entendido",    "data": "acknowledge"},
            ],
            initiative="autonomous_research"
        )

    async def _check_knowledge_milestone(self) -> bool:
        """
        NOVA celebra hitos de conocimiento.
        Cuando llega a 100, 500, 1000 entradas — te avisa.
        """
        milestones = [100, 250, 500, 750, 1000, 1500, 2000]

        # Añadir control de tiempo para evitar duplicación de hitos muy cercanos
        last_milestone_time = self._load_state_key("last_milestone_time", None)
        if last_milestone_time:
            try:
                last_time = datetime.datetime.fromisoformat(last_milestone_time)
                if (datetime.datetime.utcnow() - last_time).total_seconds() < 1800:  # 30 min
                    print("[PROACTIVE] Último hito hace menos de 30 min, omitiendo.")
                    return False
            except Exception:
                pass

        for milestone in milestones:
            key = f"milestone_{milestone}"
            if count >= milestone and not self._already_notified(key):
                msg = (
                    f"¡Hito alcanzado! 🎯\n\n"
                    f"Ya tengo *{count} entradas de conocimiento*.\n"
                )
                if milestone >= 1000:
                    msg += (
                        f"Con {count} entradas ya podemos hacer el "
                        f"*fine-tuning* de mi propio modelo. "
                        f"¿Empezamos cuando quieras?"
                    )
                else:
                    next_m = next((m for m in milestones if m > milestone), milestone * 2)
                    msg += f"Voy camino a {next_m}. Sigo aprendiendo. 📚"

                await self.notify(
                    msg,
                    buttons=[
                        {"text": "📊 Ver estadísticas", "data": "show_stats"},
                        {"text": "🧠 Iniciar fine-tuning", "data": "start_finetune"} if milestone >= 1000 else {"text": "👍 Genial", "data": "acknowledge"},
                    ],
                    initiative="knowledge_milestone"
                )
                self._mark_notified(key)
                self._save_state_key("last_milestone_time", datetime.datetime.utcnow().isoformat())
                return True

        return False

    async def _generate_vitals_image(self) -> Optional[bytes]:
        """
        Genera una imagen hermosa e impecable con las métricas vitales del sistema,
        adaptada perfectamente para un entorno móvil premium.
        """
        try:
            # Obtener datos reales
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory().percent
            
            db = SessionLocal()
            knowledge_count = db.query(KnowledgeEntry).count()
            db.close()

            # Normalizar métrica de aprendizaje (asumimos tope 1000 para la gráfica)
            aprendizaje_norm = min((knowledge_count / 1000) * 100, 100) 

            # Configuración de apariencia premium
            categories = ['Core CPU', 'Carga RAM', 'Evolución IA']
            values = [cpu, ram, aprendizaje_norm]
            colors = ['#ff4b4b', '#4bafff', '#4bff4b']

            # Crear el gráfico asegurando fondo oscuro genuino en TODA la figura
            fig, ax = plt.subplots(figsize=(8, 5), facecolor='#161616')
            ax.set_facecolor('#161616')

            # Dibujar barras con bordes redondeados (linewidth, edgecolor) y alto alpha
            bars = ax.bar(categories, values, color=colors, alpha=0.9, width=0.6, edgecolor='white', linewidth=0.5)
            
            # Limpiar bordes estéticos de matplotlib (spines)
            for spine in ['top', 'right', 'left']:
                ax.spines[spine].set_visible(False)
            ax.spines['bottom'].set_color('#333333')

            # Ejes y rejillas adaptadas
            ax.set_ylim(0, 110)
            ax.tick_params(axis='x', colors='white', labelsize=11, length=0, pad=10)
            ax.tick_params(axis='y', colors='#666666', labelsize=10, length=0)
            ax.grid(axis='y', linestyle='--', alpha=0.15, color='white')

            # Título y Subtítulo corporativo limpio
            fig.text(0.5, 0.92, 'NOVA SYSTEM VITALS', ha='center', va='center', color='white', fontsize=16, fontweight='bold')
            fig.text(0.5, 0.86, f'Total de entradas de conocimiento reales: {knowledge_count}', ha='center', va='center', color='#aaaaaa', fontsize=10, style='italic')

            # Añadir las etiquetas precisas arriba de cada barra
            for bar, val in zip(bars, values):
                yval = bar.get_height()
                # Mostramos porcentaje o un símbolo para la evolución extra
                label_text = f"{val:.1f}%" if val <= 100 else f"MAX"
                ax.text(bar.get_x() + bar.get_width()/2, yval + 3, label_text, 
                        ha='center', va='bottom', color='white', fontweight='bold', fontsize=12)

            # Ajustar diseño de márgenes
            plt.tight_layout(rect=[0, 0, 1, 0.83])

            # Guardar en buffer con el facecolor apropiado para matar el borde blanco
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=150, facecolor=fig.get_facecolor(), bbox_inches='tight', transparent=False)
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
            
        except Exception as e:
            print(f"[PROACTIVE] Error generando imagen premium: {e}")
            plt.close()
            return None

    async def send_vitals_dashboard(self, message: str = "Aquí tienes un vistazo de mis signos vitales:") -> bool:
        """
        Envía el dashboard visual a Telegram.
        """
        img_data = await self._generate_vitals_image()
        if not img_data:
            return await self.notify(message)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{TELEGRAM_API}/sendPhoto",
                    data={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "caption": f"📊 <b>NOVA DASHBOARD</b>\n\n{self._to_html(message)}",
                        "parse_mode": "HTML"
                    },
                    files={"photo": ("vitals.png", img_data, "image/png")}
                )
                if r.status_code == 200:
                    print(f"[PROACTIVE] ✅ Dashboard visual enviado")
                    return True
                else:
                    print(f"[PROACTIVE] Error enviando imagen: {r.text}")
                    return await self.notify(message)
        except Exception as e:
            print(f"[PROACTIVE] Exception enviando dashboard: {e}")
            return await self.notify(message)

    async def _check_curiosity_cycle(self) -> bool:
        """
        Ciclo de Curiosidad de 12 horas.
        NOVA medita sobre su conocimiento y propone algo técnico.
        Solo se ejecuta si el sistema tiene capacidad disponible.
        """
        # Solo cada 12 horas
        now = datetime.datetime.utcnow()
        last_curiosity = self._load_state_key("last_curiosity_cycle", None)
        if last_curiosity:
            try:
                last_time = datetime.datetime.fromisoformat(last_curiosity)
                if (now - last_time).total_seconds() < 43200: # 12 hours
                    return False
            except Exception:
                pass

        # ── GUARD: No ejecutar si el sistema está bajo carga ────────────
        try:
            from core.task_queue import task_queue as tq  # type: ignore
            from core.config import THINKER_QUEUE_THRESHOLD, THINKER_MAX_EXECUTION_SECONDS  # type: ignore
            queue_size = tq.get_size()
            if queue_size > THINKER_QUEUE_THRESHOLD:
                print(f"[PROACTIVE] Ciclo de Curiosidad pospuesto: cola en {queue_size}/{THINKER_QUEUE_THRESHOLD}")
                return False
        except Exception:
            THINKER_MAX_EXECUTION_SECONDS = 45  # fallback seguro

        print("[PROACTIVE] Ejecutando Ciclo de Curiosidad (Thinker)...")
        try:
            from agents.thinker import thinker_agent
            # Timeout estricto para que no consuma recursos indefinidamente
            result = await asyncio.wait_for(
                thinker_agent.execute(),
                timeout=THINKER_MAX_EXECUTION_SECONDS
            )
            
            if not result.get("success"):
                reason = result.get("reason", "unknown")
                print(f"[PROACTIVE] Thinker omitido: {reason}")
                return False

            if "hypothesis" in result:
                h = result["hypothesis"]
                msg = (
                        f"🧠 *CURIOSIDAD AUTÓNOMA*\n\n"
                        f"He estado meditando sobre lo que sé y tengo una hipótesis:\n\n"
                        f"💡 *{h.get('title','Nueva Idea')}*\n"
                        f"_{h.get('reasoning','Se detectó un vacío de conocimiento.')}_\n\n"
                        f"**Hipótesis:** {h.get('hypothesis','')}\n"
                        f"Valor Estratégico: {h.get('estimated_value',7)}/10\n\n"
                        f"¿Quieres que investigue esto a fondo?"
                )
                
                await self.notify(
                    msg,
                    buttons=[
                        {"text": "🚀 Investigar ahora", "data": f"approve_hypothesis_{h.get('target_topic','')}"},
                        {"text": "⏭ Quizás luego",      "data": "postpone"},
                        {"text": "🧠 Otras ideas",      "data": "run_introspect"},
                    ],
                    initiative="curiosity_cycle"
                )
                
                self._save_state_key("last_curiosity_cycle", now.isoformat())
                return True
        except asyncio.TimeoutError:
            print(f"[PROACTIVE] ⏰ Ciclo de Curiosidad cancelado: excedió {THINKER_MAX_EXECUTION_SECONDS}s de timeout.")
        except Exception as e:
            print(f"[PROACTIVE] Error en ciclo de curiosidad: {e}")
            
        return False


    async def _research_topic(self, topic: str):
        """Helper para lanzar investigación desde un botón."""
        from core.orchestrator import orchestrator
        from core.database import SessionLocal, User
        db = SessionLocal()
        try:
            user = db.query(User).first() # Asignar al primer usuario (dueño)
            if user:
                task = {
                    "type": "explore_topic",
                    "data": {"topic": topic, "depth": 0},
                    "topic": topic,
                    "user_id": user.id
                }
                await orchestrator.handle_task(task)
        finally:
            db.close()

    async def _check_failed_jobs(self) -> bool:
        """
        NOVA te avisa si hay trabajos fallando repetidamente.
        Problemas que necesitan tu atención.
        """
        if self._already_did_today("failed_jobs"):
            return False

        db = SessionLocal()
        try:
            failed = db.query(ResearchJob)\
                       .filter(ResearchJob.status == "failed")\
                       .filter(ResearchJob.retry_count >= 3)\
                       .count()
        finally:
            db.close()

        if failed >= 3:
            msg = (
                f"Tengo *{failed} trabajos fallando* repetidamente.\n\n"
                f"Puede que haya un problema con la conexión a internet "
                f"o con alguno de mis agentes. ¿Puedes revisarlo?"
            )
            await self.notify(
                msg,
                buttons=[
                    {"text": "🔍 Ver errores",    "data": "show_errors"},
                    {"text": "🔄 Reintentar todo", "data": "retry_all"},
                    {"text": "🗑 Limpiar fallidos", "data": "clear_failed"},
                ],
                initiative="failed_jobs"
            )
            self._mark_done_today("failed_jobs")
            return True

        return False

    async def _check_morning_briefing(self) -> bool:
        """
        NOVA te da los buenos días con un resumen.
        Solo una vez al día, entre 7am y 9am.
        """
        now = datetime.datetime.now()
        if not (7 <= now.hour <= 9):
            return False
        if self._already_did_today("morning_briefing"):
            return False

        db = SessionLocal()
        try:
            knowledge_count = db.query(KnowledgeEntry).count()
            pending_jobs    = db.query(ResearchJob)\
                                .filter(ResearchJob.status == "pending").count()
            recent_logs     = db.query(ChatLog)\
                                .order_by(ChatLog.timestamp.desc())\
                                .limit(1).all()
            last_activity   = (
                recent_logs[0].timestamp.strftime("%d/%m a las %H:%M")
                if recent_logs else "hace un tiempo"
            )
        finally:
            db.close()

        # Generar briefing personalizado con NOVA
        prompt = f"""Eres NOVA dándole los buenos días a Juan Ramón.

Estado actual del sistema:
- Entradas de conocimiento: {knowledge_count}
- Trabajos pendientes: {pending_jobs}
- Última actividad: {last_activity}
- Hora actual: {now.strftime('%H:%M')}

Escribe un mensaje de buenos días breve (máx 100 palabras) con:
1. Saludo natural como amiga
2. Un dato interesante de tu estado
3. Una sugerencia o pregunta para el día

Tono: cercano, directo, sin exagerar. Como un mensaje de WhatsApp de un amigo."""

        greeting = await llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.8
        )

        if greeting and len(greeting) > 20:
            await self.notify(
                greeting,
                buttons=[
                    {"text": "📊 Ver estadísticas", "data": "show_stats"},
                    {"text": "🔬 Analizar sistema",  "data": "run_introspect"},
                ],
                initiative="morning_briefing"
            )
            self._mark_done_today("morning_briefing")
            return True

        return False

    async def _check_weekly_summary(self) -> bool:
        """
        NOVA te manda un resumen semanal los domingos.
        Qué aprendió, qué mejoró, qué sigue pendiente.
        """
        now = datetime.datetime.now()
        # Solo domingos entre 6pm y 9pm
        if not (now.weekday() == 6 and 18 <= now.hour <= 21):
            return False
        if self._already_did_this_week("weekly_summary"):
            return False

        db = SessionLocal()
        try:
            total_knowledge = db.query(KnowledgeEntry).count()
            completed_jobs  = db.query(ResearchJob)\
                                .filter(ResearchJob.status == "completed").count()
            failed_jobs     = db.query(ResearchJob)\
                                .filter(ResearchJob.status == "failed").count()
        finally:
            db.close()

        from core.dataset_builder import nova_dataset_builder
        dataset_progress = nova_dataset_builder.get_progress()

        prompt = f"""Eres NOVA haciendo tu resumen semanal para Juan Ramón.

Esta semana:
- Conocimiento total acumulado: {total_knowledge} entradas
- Trabajos completados: {completed_jobs}
- Trabajos fallidos: {failed_jobs}
- Dataset de entrenamiento: {dataset_progress.get('progress_percent', 0)}% listo
- Muestras para fine-tuning: {dataset_progress.get('total_estimated', 0)}/1000

Escribe un resumen semanal breve y personal (máx 150 palabras):
1. Qué logré esta semana
2. Qué me costó trabajo
3. Qué quiero mejorar la próxima semana
4. Un pensamiento personal para Juan Ramón

Tono: reflexivo, honesto, como un diario compartido entre amigos."""

        summary = await llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.7
        )

        if summary and len(summary) > 50:
            await self.notify(
                f"*Resumen semanal* 📋\n\n{summary}",
                buttons=[
                    {"text": "📈 Ver progreso",       "data": "show_progress"},
                    {"text": "🧠 Iniciar ciclo evolución", "data": "run_evolution"},
                ],
                initiative="weekly_summary"
            )
            self._mark_done_this_week("weekly_summary")
            return True

        return False

    # ══════════════════════════════════════════════════════════
    #  RECIBIR RESPUESTAS DE TELEGRAM
    # ══════════════════════════════════════════════════════════

    async def process_telegram_update(self, update: Dict[str, Any]) -> str:
        """
        Procesa respuestas de Juan Ramón desde Telegram.
        Cuando presiona un botón o escribe una respuesta.
        """
        # Respuesta a botón inline
        if "callback_query" in update:
            cb   = update["callback_query"]
            data = cb.get("data", "")
            user = cb.get("from", {}).get("first_name", "Juan Ramón")
            return await self._handle_callback(data, user)

        # Mensaje de texto directo
        if "message" in update:
            msg  = update["message"]
            text = msg.get("text", "").strip()
            if text:
                return await self._handle_direct_message(text)

        return "ok"

    async def _handle_callback(self, data: str, user: str) -> str:
        """Maneja respuesta a botón de Telegram."""
        # Respuestas enriquecidas
        responses = {
            "postpone":    f"Entendido {user}, lo dejamos para después. Si cambias de opinión, solo avísame. 👍",
            "acknowledge": f"Me alegra que lo celebremos juntos. 🎉 ¿Hay algo más en lo que pueda ayudarte?",
            "show_stats":  "Te muestro las estadísticas en el dashboard. ¡Espero que te guste! 📊",
            "show_progress":"Aquí tienes el progreso de mis investigaciones. Míralo en el dashboard. 📈",
            "show_errors": "Revisando los errores ahora... Te aviso cuando tenga el informe completo. 🔍",
            "retry_all":   "Reintentando todos los trabajos fallidos. Esto puede tardar unos minutos. ⏳",
            "clear_failed":"Limpiando trabajos fallidos... Listo. El sistema está más limpio ahora. 🧹",
        }

        # Para comandos que requieren acción o tienen parámetros
        if data.startswith("detail_code_"):
            target = data.replace("detail_code_", "")
            # Se programa la acción en background y se confirma
            asyncio.create_task(self._send_code_analysis(target))
            response_text = f"¡Recibido! Estoy analizando el archivo `{target}` en profundidad para darte los detalles. Te aviso pronto. 🔍"
        elif data.startswith("implement_tech_"):
            tech = data.replace("implement_tech_", "")
            asyncio.create_task(self._implement_tech(tech))
            response_text = f"¡Excelente decisión! Voy a implementar {tech}. Te mantendré informado sobre el progreso. ⚙️"
        elif data.startswith("approve_hypothesis_"):
            topic = data.replace("approve_hypothesis_", "")
            asyncio.create_task(self._research_topic(topic))
            response_text = f"¡Hipótesis aprobada! 🚀 Iniciando investigación sobre: `{topic}`. Te avisaré cuando tenga resultados."
        else:
            response_text = responses.get(data, f"Recibido: {data}. ¿Qué más puedo hacer por ti?")

        # Acciones especiales
        if data == "run_introspect":
            asyncio.create_task(self._run_introspect_and_notify())
        elif data == "run_evolution":
            asyncio.create_task(self._run_evolution_and_notify())
        elif data in ["show_stats", "show_progress"]:
            asyncio.create_task(self.send_vitals_dashboard())
        elif data == "retry_all":
            asyncio.create_task(self._retry_failed_jobs())
        elif data == "start_finetune":
            response_text = (
                "¡Perfecto! El dataset está listo. "
                "Cuando quieras empezamos el fine-tuning. "
                "Solo dime y lo hacemos juntos. 🧠"
            )

        # Confirmar en Telegram
        await self.notify(response_text, initiative="callback_response")
        return "ok"

    async def _handle_direct_message(self, text: str) -> str:
        """
        Procesa mensajes de texto directos enrutándolos al ChatService central.
        """
        import os
        from services.chat_service import chat_service
        from services.memory_service import memory_service
        from core.database import SessionLocal, User
        from core.logging_config import get_logger
        logger = get_logger("proactive.telegram")
        
        db = SessionLocal()
        try:
            # Obtener usuario primario (configurable por env)
            primary_username = os.getenv("PRIMARY_USERNAME", "juan_ramon")
            user = db.query(User).filter(User.username == primary_username).first()
            if not user:
                user = db.query(User).filter(User.is_active == True).first()
            if not user:
                # Crear usuario por defecto si no existe ninguno
                from core.auth import get_password_hash
                user = User(
                    username=primary_username,
                    email=f"{primary_username}@local",
                    hashed_password=get_password_hash("changeme"),
                    is_admin=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            
            # Enviar "typing..." a Telegram
            await self._send_chat_action("typing")
            
            # Enrutar al cerebro central
            result = await chat_service.handle_standard_query(
                query=text,
                images=None,
                files_context="",
                user_id=user.id,
                db=db
            )
            
            answer = result.get("answer", "Lo siento, no pude procesar tu mensaje.")
            
            # Almacenar en memoria a largo plazo (asíncrono, no bloqueante)
            asyncio.create_task(memory_service.store_chat_message("user", text, user.id))
            asyncio.create_task(memory_service.store_chat_message("assistant", answer, user.id))
            
            # Enviar respuesta (con manejo de longitud)
            if len(answer) <= 4000:
                await self.notify(answer, initiative="telegram_chat")
            else:
                await self._send_as_document(answer, initiative="telegram_chat")
                summary = answer[:200] + "..." if len(answer) > 200 else answer
                await self.notify(f"📄 *Respuesta extensa:* {summary}\n\n_El contenido completo está en el archivo adjunto._", initiative="telegram_chat")
            
            return "ok"
        except Exception as e:
            logger.error(f"Error en _handle_direct_message: {e}")
            await self.notify(f"❌ Error procesando tu mensaje: {str(e)[:100]}", initiative="error")
            return "error"
        finally:
            db.close()

    async def _send_chat_action(self, action: str = "typing"):
        """Envía una acción de chat a Telegram (typing, upload_photo, etc.)."""
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{TELEGRAM_API}/sendChatAction",
                    json={"chat_id": TELEGRAM_CHAT_ID, "action": action}
                )
        except Exception as e:
            print(f"No se pudo enviar chat action: {e}")

    def _format_analysis_message(self, analysis: Dict[str, Any], target: str) -> str:
        """Formatea el diccionario de análisis en un mensaje legible."""
        if "text" in analysis:
            return f"Análisis de `{target}`:\n\n{analysis['text'][:1000]}"
        
        msg = f"🔍 *Análisis Detallado: {target}*\n\n"
        msg += f"_{analysis.get('resumen', '')}_\n\n"
        
        problemas = analysis.get("problemas", [])
        if problemas:
            msg += "*Problemas detectados:*\n"
            for p in problemas[:5]: # Mostrar hasta 5
                prio = str(p.get("prioridad", "baja")).upper()
                linea = f"L{p['linea']}" if p.get("linea") else "?"
                desc  = p.get("descripcion", "")
                sug   = p.get("sugerencia", "")
                msg += f"• [{prio}] {linea}: {desc}\n"
                msg += f"  > _Sugerencia: {sug}_\n"
        
        mejoras = analysis.get("mejoras", [])
        if mejoras:
            msg += "\n*Mejoras sugeridas:*\n"
            for m in mejoras[:3]:
                msg += f"• {m.get('descripcion')} ({m.get('beneficio')})\n"
        
        return msg

    async def _send_code_analysis(self, target: str):
        """Envía un análisis detallado después de un tiempo."""
        try:
            from core.self_evolution import nova_self_evolution
            analysis = await nova_self_evolution.analyze_own_file(target)
            msg = self._format_analysis_message(analysis, target)
            await self.notify(msg, initiative="code_analysis")
        except Exception as e:
            print(f"[PROACTIVE] Error enviando análisis detallado: {e}")

    async def _implement_tech(self, tech: str):
        """Inicia implementación de tecnología recomendada."""
        try:
            from core.self_evolution import nova_self_evolution
            result = await nova_self_evolution.implement_technology(tech)
            if result:
                await self.notify(f"✅ Implementación de *{tech}* completada. El sistema ahora es más capaz. ¿Quieres ver los cambios?")
            else:
                await self.notify(f"❌ No pude implementar *{tech}* automáticamente. Revisa los logs para ver el obstáculo.")
        except Exception as e:
            print(f"[PROACTIVE] Error implementando tecnología: {e}")

    async def _send_as_document(self, message: str, initiative: str) -> bool:
        """Envía el contenido completo como un archivo .txt si es muy largo."""
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return False

        filename = f"nova_analisis_{int(time.time())}.txt"
        file_content = io.BytesIO(message.encode('utf-8'))
        file_content.name = filename

        url = f"{TELEGRAM_API}/sendDocument"
        files = {"document": (filename, file_content, "text/plain")}
        data  = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": "⚠️ El contenido es demasiado extenso para el chat. Adjunto el detalle completo aquí. 📄"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, data=data, files=files)
                if r.status_code == 200:
                    print(f"[PROACTIVE] ✅ Documento enviado (Longitud: {len(message)})")
                    return True
                else:
                    print(f"[PROACTIVE] Error enviando documento: {r.text}")
                    return False
        except Exception as e:
            print(f"[PROACTIVE] Excepción enviando documento: {e}")
            return False

    async def send_diagnostic_report(self, error_type: str, error_msg: str, traceback_str: str):
        """
        Envía un reporte técnico detallado a Telegram y dispara el ciclo de auto-reparación.
        Implementado a solicitud de Juan Ramón para transparencia total.
        """
        report = (
            f"🆘 **DIAGNÓSTICO TÉCNICO DE NOVA**\n\n"
            f"He detectado un problema crítico que requiere mi atención inmediata.\n\n"
            f"📍 **Origen:** `{error_type}`\n"
            f"⚠️ **Error:** `{error_msg}`\n\n"
            f"He activado mi **Protocolo de Auto-Curación** bajo mis Reglas de Oro de programación para resolverlo."
        )
        await self.notify(report)
        
        # Enviar traza completa como documento técnico
        await self._send_as_document(traceback_str, "diagnostic_report")
        
        # Disparar ciclo de reparación autónoma en segundo plano
        try:
            from core.self_evolution import nova_self_evolution
            asyncio.create_task(nova_self_evolution.diagnose_and_repair(error_msg, traceback_str))
        except Exception as e:
            print(f"[REPAIR] No se pudo iniciar el ciclo de reparación: {e}")
    async def poll_updates(self):
        """
        Consulta Telegram periódicamente para ver si hay nuevos mensajes.
        Esto permite chatear con NOVA en local (sin webhook).
        Incluye backoff exponencial cuando no hay internet.
        """
        if not TELEGRAM_TOKEN:
            return

        params = {"timeout": 30, "offset": self._last_update_id + 1}
        
        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                r = await client.get(f"{TELEGRAM_API}/getUpdates", params=params)
                if r.status_code == 200:
                    self._handle_network_recovery()
                    data = r.json()
                    updates = data.get("result", [])
                    for update in updates:
                        self._last_update_id = update["update_id"]
                        await self.process_telegram_update(update)
                        self._save_state()
                elif r.status_code == 409:
                    # Probable conflicto con Webhook
                    print("[PROACTIVE] Conflicto de Polling: Webhook activo. Desactivando Webhook...")
                    await client.post(f"{TELEGRAM_API}/deleteWebhook")
                else:
                    print(f"[PROACTIVE] Polling error {r.status_code}")
        except Exception as e:
            if self._is_network_error(e):
                self._handle_network_error("Telegram polling")
            elif "timeout" not in str(e).lower():
                print(f"[PROACTIVE] Exception in polling: {e}")
                err_trace = traceback.format_exc()
                await self.send_diagnostic_report("Telegram Polling", str(e), err_trace)

    # ══════════════════════════════════════════════════════════
    #  HELPERS INTERNOS
    # ══════════════════════════════════════════════════════════

    async def _run_introspect_and_notify(self):
        from core.self_evolution import nova_self_evolution
        result = await nova_self_evolution.introspect()
        msg = result.get("mensaje_personal", "Introspección completada.")
        
        # Enviar completo, sin truncar
        if len(msg) > 4000:
            await self._send_as_document(msg, initiative="introspection")
            await self.notify("🔍 *Introspección completada.* El informe detallado está en el archivo adjunto.", initiative="introspection")
        else:
            await self.notify(f"🔍 *Resultado introspección:*\n\n{msg}", initiative="introspection")

    async def _run_evolution_and_notify(self):
        from core.self_evolution import nova_self_evolution
        await nova_self_evolution.run_evolution_cycle()
        await self.notify("✅ Ciclo de evolución completado. Revisa el dashboard para ver los resultados.")

    async def _retry_failed_jobs(self):
        db = SessionLocal()
        try:
            failed = db.query(ResearchJob)\
                       .filter(ResearchJob.status == "failed").all()
            for job in failed:
                job.status      = "pending"
                job.retry_count = 0
            db.commit()
            await self.notify(f"🔄 {len(failed)} trabajos reactivados.")
        except Exception as e:
            await self.notify(f"❌ Error reactivando trabajos: {str(e)[:100]}")
        finally:
            db.close()

    def _is_good_time(self) -> bool:
        hour = datetime.datetime.now().hour
        if QUIET_HOURS_START > QUIET_HOURS_END:
            # Cruce de medianoche (ej: 23-7)
            return not (hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END)
        return QUIET_HOURS_END <= hour < QUIET_HOURS_START

    def _queue_for_later(self, message, buttons, initiative):
        """Guarda mensaje para enviarlo en horario normal."""
        queued = self._load_state_key("queued_messages", [])
        queued.append({
            "message":    message,
            "buttons":    buttons,
            "initiative": initiative,
            "queued_at":  datetime.datetime.utcnow().isoformat()
        })
        self._save_state_key("queued_messages", queued[-10:])  # máx 10

    def _reset_daily_counter(self):
        today = datetime.date.today().isoformat()
        if self._last_message_date != today:
            self._messages_today  = 0
            self._last_message_date = today

    def _already_did_today(self, key: str) -> bool:
        done = self._load_state_key("done_today", {})
        today = datetime.date.today().isoformat()
        return done.get(key) == today

    def _mark_done_today(self, key: str):
        done = self._load_state_key("done_today", {})
        done[key] = datetime.date.today().isoformat()
        self._save_state_key("done_today", done)

    def _already_did_this_week(self, key: str) -> bool:
        done = self._load_state_key("done_week", {})
        week = datetime.date.today().isocalendar()[:2]
        return done.get(key) == str(week)

    def _mark_done_this_week(self, key: str):
        done = self._load_state_key("done_week", {})
        week = datetime.date.today().isocalendar()[:2]
        done[key] = str(week)
        self._save_state_key("done_week", done)

    def _already_notified(self, key: str) -> bool:
        notified = self._load_state_key("notified", [])
        return key in notified

    def _mark_notified(self, key: str):
        notified = self._load_state_key("notified", [])
        if key not in notified:
            notified.append(key)
        self._save_state_key("notified", notified)

    def _load_state(self):
        try:
            if self._state_file.exists():
                data = json.loads(self._state_file.read_text())
                self._messages_today    = data.get("messages_today", 0)
                self._last_message_date = data.get("last_message_date")
                self._last_update_id    = data.get("last_update_id", 0)
        except Exception:
            pass

    def _save_state(self):
        try:
            existing = {}
            if self._state_file.exists():
                existing = json.loads(self._state_file.read_text())
            existing["messages_today"]    = self._messages_today
            existing["last_message_date"] = self._last_message_date
            existing["last_update_id"]    = self._last_update_id
            self._state_file.write_text(json.dumps(existing, ensure_ascii=False))
        except Exception:
            pass

    def _load_state_key(self, key: str, default):
        try:
            if self._state_file.exists():
                data = json.loads(self._state_file.read_text())
                return data.get(key, default)
        except Exception:
            pass
        return default

    def _save_state_key(self, key: str, value):
        try:
            existing = {}
            if self._state_file.exists():
                existing = json.loads(self._state_file.read_text())
            existing[key] = value
            self._state_file.write_text(json.dumps(existing, ensure_ascii=False))
        except Exception:
            pass

    def _parse_json(self, text: str) -> Optional[Dict]:
        import re
        if not text:
            return None
        try:
            return json.loads(text.strip())
        except Exception:
            pass
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return None

    def get_status(self) -> Dict[str, Any]:
        return {
            "telegram_configured": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
            "messages_today":      self._messages_today,
            "max_messages_day":    MAX_MESSAGES_DAY,
            "quiet_hours":         f"{QUIET_HOURS_START}:00 - {QUIET_HOURS_END}:00",
            "is_good_time_now":    self._is_good_time(),
            "initiatives_logged":  len(self._initiative_log),
        }


# Instancia global
nova_proactive = NOVAProactiveSystem()


# ── SCHEDULER — NOVA revisa cada hora si tiene algo que decir ─────

async def run_proactive_scheduler():
    """
    NOVA revisa cada hora si tiene algo importante que contarte.
    No spam — solo cuando realmente vale la pena.
    Cuando no hay internet, las tareas de red se omiten silenciosamente.
    """
    print("[PROACTIVE] Sistema proactivo iniciado — NOVA vigilará en background")

    # Primera revisión después de 2 minutos
    await asyncio.sleep(120)

    while True:
        try:
            from core.llm_client import llm_client
            # v1.0 Hardening: Si el usuario está activo, posponer ciclo
            if llm_client.is_user_active():
                print("[OVERDRIVE] Scheduler delayed: user active (Proactive paused 10 min)")
                await asyncio.sleep(600)
                continue

            # Solo ejecutar check_and_act si no estamos offline
            if not nova_proactive._is_offline:
                await nova_proactive.check_and_act()
            else:
                # Cada hora intentamos ver si la red volvió
                # pero sin generar spam de errores
                pass

            # También enviar mensajes en cola si ahora es buen momento
            if not nova_proactive._is_offline:
                queued = nova_proactive._load_state_key("queued_messages", [])
                if queued and nova_proactive._is_good_time():
                    msg = queued.pop(0)
                    await nova_proactive.notify(
                        msg["message"],
                        msg.get("buttons"),
                        msg.get("initiative", "queued")
                    )
                    nova_proactive._save_state_key("queued_messages", queued)

        except Exception as e:
            if nova_proactive._is_network_error(e):
                nova_proactive._handle_network_error("scheduler")
            else:
                print(f"[PROACTIVE] Error en scheduler: {e}")

        # Revisar cada hora
        await asyncio.sleep(3600)

async def run_telegram_polling():
    """
    Loop infinito de Long Polling para recibir mensajes de Juan Ramón.
    Mantiene a NOVA atenta a sus órdenes en tiempo real.
    Usa backoff exponencial cuando no hay internet para evitar spam de errores.
    """
    print("[PROACTIVE] Telegram Polling iniciado — NOVA te está escuchando")
    while True:
        try:
            await nova_proactive.poll_updates()
            # Si llegamos aquí sin error de red, pausa normal
            if not nova_proactive._is_offline:
                await asyncio.sleep(1)
            else:
                # Estamos offline — usar backoff exponencial
                await asyncio.sleep(nova_proactive._poll_backoff)
        except Exception as e:
            if nova_proactive._is_network_error(e):
                nova_proactive._handle_network_error("Telegram polling loop")
                await asyncio.sleep(nova_proactive._poll_backoff)
            else:
                print(f"[PROACTIVE] Exception in polling: {e}")
                err_trace = traceback.format_exc()
                asyncio.create_task(nova_proactive.send_diagnostic_report("Polling Loop Crash", str(e), err_trace))
                await asyncio.sleep(10)