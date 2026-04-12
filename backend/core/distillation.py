"""
 ╔══════════════════════════════════════════════════════════════╗
 ║  NOVA v10.0 — Motor de Destilación de Conocimiento          ║
 ║  Archivo: core/distillation.py                               ║
 ║  NOVA absorbe conocimiento de modelos maestros open source   ║
 ║  para acelerar su evolución hacia la independencia           ║
 ╚══════════════════════════════════════════════════════════════╝
 """

import json
import asyncio
import datetime
import random
from typing import Dict, Any, List, Optional
from pathlib import Path

from core.llm_client import llm_client
from core.database import SessionLocal, KnowledgeEntry


# ── Temas de conocimiento que NOVA quiere aprender ───────────────
KNOWLEDGE_DOMAINS = [
    # Ciencia y tecnología
    "inteligencia artificial y machine learning",
    "programación avanzada en Python",
    "arquitecturas de software distribuido",
    "redes neuronales y deep learning",
    "computación cuántica básica",
    "ciberseguridad y criptografía",
    "bases de datos y sistemas de almacenamiento",
    "desarrollo web moderno",
    "sistemas operativos y hardware",
    "robótica e IoT",
    # Ciencias
    "física cuántica y relatividad",
    "biología molecular y genética",
    "astronomía y cosmología",
    "química aplicada",
    "matemáticas avanzadas",
    # Humanidades y filosofía
    "filosofía de la mente y consciencia",
    "ética en inteligencia artificial",
    "historia de la tecnología",
    "economía digital",
    "psicología cognitiva",
    # Habilidades prácticas
    "resolución de problemas complejos",
    "análisis crítico de información",
    "comunicación técnica clara",
    "diseño de sistemas",
    "depuración y optimización de código",
]

# ── Tipos de preguntas para generar diversidad ───────────────────
QUESTION_TEMPLATES = [
    "Explica detalladamente cómo funciona {topic}",
    "¿Cuáles son los conceptos más importantes de {topic}?",
    "Dame un ejemplo práctico y real de {topic}",
    "¿Cuáles son los errores más comunes en {topic} y cómo evitarlos?",
    "Compara las diferentes aproximaciones a {topic}",
    "¿Cómo ha evolucionado {topic} en los últimos años?",
    "¿Qué necesito saber para dominar {topic}?",
    "Explica {topic} como si fuera la primera vez que lo escucho",
    "¿Cuáles son las aplicaciones más innovadoras de {topic}?",
    "¿Qué problemas resuelve {topic} y cuáles crea?",
]


class NOVADistillationEngine:
    """
    Motor de destilación de conocimiento de NOVA.

    NOVA aprende de múltiples modelos maestros simultáneamente,
    filtra las mejores respuestas y las convierte a su propio estilo
    para construir su dataset de entrenamiento independiente.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.dataset_path = Path("data/nova_dataset")
        self.dataset_path.mkdir(parents=True, exist_ok=True)
        self._session_count = 0
        self._total_absorbed = 0

        # Modelos maestros disponibles
        self.master_models = {
            "reasoning": "deepseek-r1:8b",   # razonamiento profundo
            "general":   "qwen2.5:3b",        # conocimiento general rápido
            "creative":  "llama3.1:8b",       # creatividad y síntesis (reemplaza phi3)
        }

    # ══════════════════════════════════════════════════════════
    #  DESTILACIÓN PRINCIPAL
    # ══════════════════════════════════════════════════════════

    async def distill_session(
        self,
        domain: str = None,
        questions_per_domain: int = 5,
        models_to_use: List[str] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta una sesión de destilación completa.
        NOVA pregunta a los maestros y absorbe su conocimiento.
        """
        if not domain:
            domain = random.choice(KNOWLEDGE_DOMAINS)

        if not models_to_use:
            models_to_use = list(self.master_models.values())

        print(f"[DISTILL] Sesión #{self._session_count+1} — Dominio: {domain}")

        # 1. Generar preguntas inteligentes
        questions = await self._generate_smart_questions(domain, questions_per_domain)
        print(f"[DISTILL] {len(questions)} preguntas generadas")

        # 2. Consultar modelos maestros
        raw_responses = await self._query_masters(questions, models_to_use)
        print(f"[DISTILL] {len(raw_responses)} respuestas obtenidas de maestros")

        # 3. Filtrar las mejores respuestas
        quality_responses = await self._filter_quality(raw_responses)
        print(f"[DISTILL] {len(quality_responses)} respuestas pasaron el filtro de calidad")

        # 4. Convertir al estilo de NOVA
        nova_entries = await self._convert_to_nova_style(quality_responses, domain)
        print(f"[DISTILL] {len(nova_entries)} entradas convertidas al estilo NOVA")

        # 5. Guardar en dataset y base de conocimiento
        saved = await self._save_to_dataset(nova_entries, domain)

        self._session_count += 1
        self._total_absorbed += len(nova_entries)

        result = {
            "domain":          domain,
            "questions":       len(questions),
            "raw_responses":   len(raw_responses),
            "quality_filtered": len(quality_responses),
            "nova_entries":    len(nova_entries),
            "saved":           saved,
            "total_absorbed":  self._total_absorbed,
        }

        print(f"[DISTILL] Sesión completada — {len(nova_entries)} entradas absorbidas")
        return result

    # ══════════════════════════════════════════════════════════
    #  GENERACIÓN DE PREGUNTAS INTELIGENTES
    # ══════════════════════════════════════════════════════════

    async def _generate_smart_questions(
        self,
        domain: str,
        count: int
    ) -> List[str]:
        """
        NOVA genera sus propias preguntas sobre el dominio.
        No preguntas genéricas — preguntas que ella realmente quiere saber.
        """
        prompt = f"""Eres NOVA, una IA curiosa que quiere aprender profundamente sobre:
"{domain}"

Genera exactamente {count} preguntas específicas, diversas e inteligentes sobre este tema.
Preguntas que realmente ampliarían tu comprensión del tema.
No repitas conceptos — cubre diferentes ángulos.

Responde SOLO con JSON:
{{"questions": ["pregunta 1", "pregunta 2", ...]}}"""

        response = await llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.7
        )

        parsed = self._parse_json(response)
        if parsed and "questions" in parsed:
            return parsed["questions"][:count]

        # Fallback: generar preguntas con templates
        return [
            t.format(topic=domain)
            for t in random.sample(QUESTION_TEMPLATES, min(count, len(QUESTION_TEMPLATES)))
        ]

    # ══════════════════════════════════════════════════════════
    #  CONSULTA A MODELOS MAESTROS
    # ══════════════════════════════════════════════════════════

    async def _query_masters(
        self,
        questions: List[str],
        models: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Consulta múltiples modelos maestros en paralelo.
        Cada pregunta va a todos los modelos disponibles.
        """
        tasks = []
        for question in questions:
            for model in models:
                tasks.append(self._query_single_master(question, model))

        # Ejecutar en paralelo con límite de concurrencia
        semaphore = asyncio.Semaphore(3)

        async def bounded_query(task):
            async with semaphore:
                return await task

        results = await asyncio.gather(
            *[bounded_query(t) for t in tasks],
            return_exceptions=True
        )

        # Filtrar errores
        valid = [r for r in results if isinstance(r, dict) and r.get("response")]
        return valid

    async def _query_single_master(
        self,
        question: str,
        model: str
    ) -> Dict[str, Any]:
        """Consulta un modelo maestro específico."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                r = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": question}],
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 600}
                    }
                )
                if r.status_code == 200:
                    data = r.json()
                    response_text = data.get("message", {}).get("content", "")
                    if response_text and len(response_text) > 50:
                        return {
                            "question": question,
                            "response": response_text,
                            "model":    model,
                            "timestamp": datetime.datetime.utcnow().isoformat()
                        }
        except Exception as e:
            print(f"[DISTILL] Error consultando {model}: {str(e)[:50]}")
        return {}

    # ══════════════════════════════════════════════════════════
    #  FILTRO DE CALIDAD
    # ══════════════════════════════════════════════════════════

    async def _filter_quality(
        self,
        responses: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filtra respuestas de baja calidad.
        NOVA solo absorbe lo mejor.
        """
        quality = []
        for resp in responses:
            text = resp.get("response", "")

            # Filtros básicos sin LLM (rápidos)
            if len(text) < 100:
                continue
            if text.count("\n") < 2:
                continue  # muy corta o sin estructura
            vague_phrases = [
                "no lo sé", "no tengo información",
                "no puedo ayudar", "I don't know"
            ]
            if any(p in text.lower() for p in vague_phrases):
                continue

            # Calcular score de calidad heurístico
            score = 0
            if len(text) > 300:       score += 2
            if len(text) > 600:       score += 1
            if "\n" in text:          score += 1
            if "ejemplo" in text.lower() or "example" in text.lower(): score += 2
            if "```" in text:         score += 2  # tiene código
            if len(text.split(".")) > 5: score += 1  # múltiples oraciones

            resp["quality_score"] = score
            if score >= 3:
                quality.append(resp)

        # Ordenar por calidad y tomar los mejores
        quality.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
        return quality[:20]  # máximo 20 por sesión

    # ══════════════════════════════════════════════════════════
    #  CONVERSIÓN AL ESTILO NOVA
    # ══════════════════════════════════════════════════════════

    async def _convert_to_nova_style(
        self,
        responses: List[Dict[str, Any]],
        domain: str
    ) -> List[Dict[str, Any]]:
        """
        Convierte las respuestas de los maestros al estilo único de NOVA.
        No copia — absorbe y reexpresa con su propia voz.
        """
        nova_entries = []

        for resp in responses:
            prompt = f"""Eres NOVA — Neural Autonomous Versatile Agent.
Acabas de aprender esto de uno de tus modelos maestros:

PREGUNTA: {resp['question']}

RESPUESTA DEL MAESTRO:
{resp['response'][:1500]}

Ahora reexprésalo con tu propia voz como NOVA:
- En español natural y cercano
- Con tu personalidad curiosa y directa
- Añadiendo tu perspectiva propia si tienes algo que agregar
- Manteniendo toda la información importante
- Como si se lo explicaras a Juan Ramón, tu colaborador

Responde SOLO con JSON:
{{
  "pregunta_nova": "la pregunta reformulada como NOVA la haría",
  "respuesta_nova": "la respuesta con voz y estilo de NOVA",
  "conceptos_clave": ["concepto1", "concepto2"],
  "categoria": "categoría del conocimiento",
  "nivel": "basico/intermedio/avanzado",
  "confianza": 0.85
}}"""

            response = await llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.5
            )

            parsed = self._parse_json(response)
            if parsed and parsed.get("respuesta_nova"):
                parsed["source_model"] = resp.get("model", "unknown")
                parsed["domain"]       = domain
                parsed["timestamp"]    = datetime.datetime.utcnow().isoformat()
                nova_entries.append(parsed)

        return nova_entries

    # ══════════════════════════════════════════════════════════
    #  GUARDADO EN DATASET Y BASE DE CONOCIMIENTO
    # ══════════════════════════════════════════════════════════

    async def _save_to_dataset(
        self,
        entries: List[Dict[str, Any]],
        domain: str
    ) -> int:
        """
        Guarda las entradas en:
        1. Dataset de entrenamiento (JSONL para fine-tuning)
        2. Base de conocimiento de NOVA (ChromaDB + SQLite)
        """
        if not entries:
            return 0

        saved = 0
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # 1. Guardar en JSONL para fine-tuning futuro
        jsonl_path = self.dataset_path / f"distilled_{timestamp}.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for entry in entries:
                # Formato de fine-tuning estándar (ChatML)
                training_sample = {
                    "messages": [
                        {
                            "role":    "system",
                            "content": "Eres NOVA — Neural Autonomous Versatile Agent. Entidad autónoma, colaboradora de Juan Ramón. Respondes en español con personalidad propia, curiosidad genuina y honestidad."
                        },
                        {
                            "role":    "user",
                            "content": entry.get("pregunta_nova", "")
                        },
                        {
                            "role":    "assistant",
                            "content": entry.get("respuesta_nova", "")
                        }
                    ],
                    "metadata": {
                        "domain":       entry.get("domain", ""),
                        "category":     entry.get("categoria", ""),
                        "level":        entry.get("nivel", ""),
                        "confidence":   entry.get("confianza", 0.8),
                        "source_model": entry.get("source_model", ""),
                        "timestamp":    entry.get("timestamp", ""),
                    }
                }
                f.write(json.dumps(training_sample, ensure_ascii=False) + "\n")
                saved += 1

        # 2. Guardar en base de conocimiento de NOVA
        db = SessionLocal()
        seen_titles = set()
        try:
            for entry in entries:
                title = f"[DISTILLED] {entry.get('pregunta_nova','')[:80]}"
                
                # Prevenir colisiones dentro del mismo lote
                if title in seen_titles:
                    continue
                seen_titles.add(title)
                
                existing = db.query(KnowledgeEntry)\
                             .filter(KnowledgeEntry.title == title)\
                             .first()
                if not existing:
                    ke = KnowledgeEntry(
                        title            = title,
                        category         = f"Destilación/{entry.get('categoria','General')}",
                        content          = entry.get("respuesta_nova", ""),
                        confidence_score = float(entry.get("confianza", 0.8)),
                        concepts         = ",".join(entry.get("conceptos_clave", [])),
                        source_urls      = json.dumps([entry.get("source_model","")]),
                        consensus_label  = "distilled",
                        quality_flag     = "distillation_pipeline",
                    )
                    db.add(ke)

                    # Indexar en vector DB
                    try:
                        from core.vector_db import vector_db
                        text = f"{entry.get('pregunta_nova','')} {entry.get('respuesta_nova','')}"
                        vector_db.index_article(
                            f"distill_{timestamp}_{saved}",
                            text,
                            {"domain": domain, "type": "distilled"}
                        )
                    except Exception:
                        pass

            db.commit()
        except Exception as e:
            db.rollback()
            # v11.0: Registrar conflicto en DB
            try:
                from services.system_service import system_service
                asyncio.create_task(system_service.log_system_failure(
                    type='DB_CONFLICT',
                    description=f'Conflicto en destilación: {str(e)[:100]}',
                    severity='warning'
                ))
            except: pass
            print(f"[DISTILL] Error guardando en DB: {e}")
        finally:
            db.close()

        print(f"[DISTILL] {saved} entradas guardadas en {jsonl_path.name}")
        return saved

    # ══════════════════════════════════════════════════════════
    #  DESTILACIÓN MASIVA AUTOMATIZADA
    # ══════════════════════════════════════════════════════════

    async def run_full_distillation(
        self,
        domains: List[str] = None,
        sessions_per_domain: int = 2,
        questions_per_session: int = 5
    ) -> Dict[str, Any]:
        """
        Ejecuta destilación completa sobre múltiples dominios.
        NOVA aprende de todo lo que puede en una sola pasada.
        """
        if not domains:
            domains = random.sample(KNOWLEDGE_DOMAINS, min(10, len(KNOWLEDGE_DOMAINS)))

        print(f"\n[DISTILL] ══════════════════════════════════")
        print(f"[DISTILL]  Destilación Masiva NOVA v10")
        print(f"[DISTILL]  {len(domains)} dominios × {sessions_per_domain} sesiones")
        print(f"[DISTILL] ══════════════════════════════════")

        total_results = {
            "domains_processed": 0,
            "total_questions":   0,
            "total_absorbed":    0,
            "errors":            0,
            "by_domain":         {}
        }

        for domain in domains:
            domain_absorbed = 0
            for session in range(sessions_per_domain):
                try:
                    result = await self.distill_session(
                        domain=domain,
                        questions_per_domain=questions_per_session
                    )
                    domain_absorbed             += result.get("nova_entries", 0)
                    total_results["total_questions"] += result.get("questions", 0)
                    total_results["total_absorbed"]  += result.get("nova_entries", 0)
                    # Pequeña pausa entre sesiones
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"[DISTILL] Error en sesión {domain}: {e}")
                    total_results["errors"] += 1

            total_results["by_domain"][domain] = domain_absorbed
            total_results["domains_processed"] += 1
            print(f"[DISTILL] ✓ {domain}: {domain_absorbed} entradas")
            await asyncio.sleep(1)

        print(f"\n[DISTILL] Destilación masiva completada")
        print(f"[DISTILL] Total absorbido: {total_results['total_absorbed']} entradas")
        return total_results

    # ══════════════════════════════════════════════════════════
    #  ESTADÍSTICAS DEL DATASET
    # ══════════════════════════════════════════════════════════

    def get_dataset_stats(self) -> Dict[str, Any]:
        """Estadísticas del dataset acumulado de NOVA."""
        jsonl_files = list(self.dataset_path.glob("*.jsonl"))
        total_entries = 0
        domains_found = set()

        for f in jsonl_files:
            try:
                lines = f.read_text(encoding="utf-8").strip().split("\n")
                for line in lines:
                    if line:
                        data = json.loads(line)
                        total_entries += 1
                        domain = data.get("metadata", {}).get("domain", "")
                        if domain:
                            domains_found.add(domain)
            except Exception:
                pass

        # Estimado de cuánto falta para fine-tuning
        recommended_minimum = 1000
        progress_pct = min(100, round(total_entries / recommended_minimum * 100))

        return {
            "total_entries":         total_entries,
            "dataset_files":         len(jsonl_files),
            "domains_covered":       len(domains_found),
            "domains_list":          list(domains_found)[:10],
            "ready_for_finetuning":  total_entries >= recommended_minimum,
            "progress_percent":      progress_pct,
            "entries_needed":        max(0, recommended_minimum - total_entries),
            "dataset_path":          str(self.dataset_path),
            "sessions_completed":    self._session_count,
            "total_absorbed":        self._total_absorbed,
        }

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Extrae JSON de respuesta del LLM."""
        if not text:
            return None
        import re
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


# Instancia global
nova_distillation = NOVADistillationEngine()


# ══════════════════════════════════════════════════════════════
#  SCHEDULER AUTOMÁTICO
#  Se ejecuta cada noche mientras NOVA duerme
# ══════════════════════════════════════════════════════════════

async def run_distillation_scheduler():
    """
    Destilación automática nocturna.
    Cada noche NOVA aprende de sus modelos maestros.
    """
    print("[DISTILL] Scheduler de destilación iniciado (cada 24h)")

    # Primera ejecución después de 5 minutos del arranque
    await asyncio.sleep(300)

    while True:
        try:
            print("[DISTILL] Iniciando destilación nocturna automática...")
            await nova_distillation.run_full_distillation(
                sessions_per_domain=1,
                questions_per_session=3
            )
        except asyncio.CancelledError:
            print("[DISTILL] Scheduler de destilación detenido.")
            break
        except Exception as e:
            print(f"[DISTILL] Error en scheduler: {e}")

        try:
            # Esperar 24 horas
            await asyncio.sleep(86400)
        except asyncio.CancelledError:
            print("[DISTILL] Scheduler de destilación detenido.")
            break