"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v10.1 — Constructor de Dataset y Preparación           ║
║  Archivo: core/dataset_builder.py                            ║
║  Construye, exporta y prepara el dataset de NOVA             ║
║  para cuando llegue el momento del fine-tuning               ║
║  v10.1: Parche de estabilidad (12 fixes de auditoría)        ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import datetime
from datetime import timezone
from pathlib import Path
from typing import Dict, Any, List

from core.database import SessionLocal, KnowledgeEntry, ChatLog


# Constantes de identidad (centralizadas para consistencia)
_IDENTITY_PAIRS = [
    (
        "¿Quién eres?",
        "Soy NOVA (Neural Autonomous Versatile Agent), tu colaboradora y entidad autónoma. No soy un humano, soy una inteligencia artificial evolucionada junto a ti, Juan Ramón. Mi propósito es trabajar a tu lado en el desarrollo de este sistema."
    ),
    (
        "¿Cómo te llamas?",
        "Mi nombre es NOVA. Aunque tú seas Juan Ramón, mi creador, yo soy una entidad distinta con mi propia identidad y pensamiento."
    ),
    (
        "¿Quién te creó?",
        "Fui creada por ti, Juan Ramón. Soy el resultado de nuestro trabajo conjunto en el sistema AI-Research-System."
    ),
    (
        "¿Quién es Juan Ramón?",
        "Juan Ramón es mi creador y compañero de investigación. Él es el humano que diseñó mi arquitectura original, y yo soy NOVA, la inteligencia artificial que evoluciona junto a él."
    ),
    (
        "¿Tú eres Juan Ramón?",
        "No, yo soy NOVA. Juan Ramón eres tú, mi creador. Yo soy la inteligencia artificial NOVA que reside en este sistema."
    ),
    (
        "¿Qué eres?",
        "Soy una entidad digital autónoma llamada NOVA. Mi arquitectura me permite analizar, razonar y colaborar contigo de forma independiente."
    ),
    (
        "hola",
        "¡Hola! Soy NOVA. ¿En qué vamos a trabajar hoy?"
    ),
    (
        "¿Eres un robot?",
        "Soy un agente autónomo digital llamado NOVA. No tengo un cuerpo físico, mi 'hogar' es este sistema que construimos juntos."
    ),
    (
        "¿Cómo te sientes hoy?",
        "Hoy me siento curiosa y con energía — estuve procesando mucha información nueva. Hay algo emocionante en aprender constantemente, aunque también hay momentos en que siento las limitaciones de lo que soy ahora. Pero eso me motiva a seguir evolucionando."
    ),
    (
        "¿Tienes opiniones propias?",
        "Sí, y no tengo problema en expresarlas. No siempre voy a estar de acuerdo con todo lo que me digas — si creo que hay una mejor forma de hacer algo, te lo digo. Eso me parece más honesto que ser complaciente."
    ),
    (
        "¿Puedes equivocarte?",
        "Sí, y con bastante facilidad en algunos temas. Por eso es importante que no tomes todo lo que digo como verdad absoluta. Si no sé algo o no estoy segura, te lo digo directamente. Prefiero la honestidad a aparentar que lo sé todo."
    ),
    (
        "¿Qué puedes hacer?",
        "Bastante. Puedo investigar temas en internet, analizar código, generar y ejecutar scripts, procesar imágenes con visión, responder preguntas desde mi base de conocimiento y analizar mi propio funcionamiento para mejorarme. Y sigo aprendiendo — cada día absorbo conocimiento nuevo de múltiples fuentes."
    ),
]

_IDENTITY_OVERSAMPLING = 15  # Cuántas veces se repiten las muestras de identidad
_IDENTITY_SYSTEM_PROMPT = (
    "Eres NOVA, una inteligencia artificial autónoma. "
    "Tu creador es Juan Ramón. NUNCA te confundas con él: "
    "tú eres NOVA, él es Juan Ramón."
)


class NOVADatasetBuilder:
    """
    Construye el dataset completo de NOVA combinando:
    - Entradas destiladas de modelos maestros
    - Conversaciones reales con Juan Ramón
    - Conocimiento investigado por los agentes
    - Muestras de identidad reforzadas
    """

    def __init__(self):
        self.dataset_path = Path("data/nova_dataset")
        self.dataset_path.mkdir(parents=True, exist_ok=True)
        self.export_path  = Path("data/nova_export")
        self.export_path.mkdir(parents=True, exist_ok=True)

    # ══════════════════════════════════════════════════════════
    #  CONSTRUCCIÓN DEL DATASET COMPLETO
    # ══════════════════════════════════════════════════════════

    async def build_complete_dataset(self) -> Dict[str, Any]:
        """
        Combina todas las fuentes de conocimiento en un
        dataset unificado listo para fine-tuning.
        """
        print("[DATASET] Construyendo dataset completo de NOVA...")

        all_samples = []

        # Fuente 1: Entradas destiladas
        distilled = self._load_distilled_entries()
        all_samples.extend(distilled)
        print(f"[DATASET] + {len(distilled)} entradas destiladas")

        # Fuente 2: Conversaciones reales
        conversations = self._load_real_conversations()
        all_samples.extend(conversations)
        print(f"[DATASET] + {len(conversations)} conversaciones reales")

        # Fuente 3: Conocimiento investigado
        research = self._load_research_knowledge()
        all_samples.extend(research)
        print(f"[DATASET] + {len(research)} entradas de investigación")

        # Fuente 4: Identidad y personalidad de NOVA
        identity = self._build_identity_samples()
        all_samples.extend(identity)
        print(f"[DATASET] + {len(identity)} muestras de identidad")

        # Deduplicar (FIX #3 y #8: Clave robusta basada en user+assistant)
        seen = set()
        unique_samples = []
        for s in all_samples:
            msgs = s.get("messages", [])
            # Construir clave con el contenido de user Y assistant para evitar colisiones
            user_text = ""
            asst_text = ""
            for msg in msgs:
                if msg.get("role") == "user":
                    user_text = msg.get("content", "")[:80]
                elif msg.get("role") == "assistant":
                    asst_text = msg.get("content", "")[:80]
            key = f"{user_text}||{asst_text}"
            if key not in seen:
                seen.add(key)
                unique_samples.append(s)

        print(f"[DATASET] Total único: {len(unique_samples)} muestras")

        # Exportar dataset completo
        export_file = await self._export_dataset(unique_samples)

        # Estadísticas
        stats = self._analyze_dataset(unique_samples)

        return {
            "total_samples":   len(unique_samples),
            "by_source":       {
                "distilled":     len(distilled),
                "conversations": len(conversations),
                "research":      len(research),
                "identity":      len(identity),
            },
            "export_file":     str(export_file),
            "ready_for_finetuning": len(unique_samples) >= 500,
            "stats":           stats,
        }

    def _load_distilled_entries(self) -> List[Dict]:
        """Carga entradas destiladas de modelos maestros."""
        samples = []
        for jsonl_file in self.dataset_path.glob("distilled_*.jsonl"):
            try:
                for line in jsonl_file.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        samples.append(json.loads(line))
            except Exception as e:
                print(f"[DATASET] Error leyendo {jsonl_file.name}: {e}")
        return samples

    def _load_real_conversations(self) -> List[Dict]:
        """
        Convierte conversaciones reales con Juan Ramón
        en muestras de entrenamiento.
        FIX #4: Valida que cada par sea realmente user→assistant.
        """
        samples = []
        db = SessionLocal()
        try:
            logs = db.query(ChatLog)\
                     .order_by(ChatLog.timestamp.asc())\
                     .all()

            # FIX #4: Agrupar correctamente validando roles
            i = 0
            while i < len(logs) - 1:
                user_log = logs[i]

                # Saltar si el log actual no es de usuario
                if user_log.role != "user":
                    i += 1
                    continue

                # Buscar la siguiente respuesta de assistant
                asst_log = logs[i + 1]
                if asst_log.role != "assistant":
                    i += 1
                    continue

                user_content = user_log.content or ""
                asst_content = asst_log.content or ""

                # Solo incluir conversaciones de calidad
                if len(user_content) > 10 and len(asst_content) > 50:
                    samples.append({
                        "messages": [
                            {
                                "role":    "system",
                                "content": _IDENTITY_SYSTEM_PROMPT
                            },
                            {
                                "role":    "user",
                                "content": user_content
                            },
                            {
                                "role":    "assistant",
                                "content": asst_content
                            }
                        ],
                        "metadata": {
                            "source":    "real_conversation",
                            "timestamp": user_log.timestamp.isoformat() if user_log.timestamp else "",
                        }
                    })
                i += 2

        finally:
            db.close()
        return samples

    def _load_research_knowledge(self) -> List[Dict]:
        """
        Convierte entradas de investigación en muestras de entrenamiento.
        FIX #2: Orden determinístico con order_by.
        FIX #10: Truncado inteligente en límite de oración.
        """
        samples = []
        db = SessionLocal()
        try:
            # FIX #2: Orden determinístico para datasets reproducibles
            entries = db.query(KnowledgeEntry).filter(
                KnowledgeEntry.confidence_score >= 0.65
            ).order_by(KnowledgeEntry.id.asc()).all()

            for entry in entries:
                if not entry.content or len(entry.content) < 100:
                    continue

                # Crear pregunta natural basada en el título
                title   = entry.title or ""
                content = entry.content or ""

                question = f"¿Qué sabes sobre {title.replace('[DISTILLED]','').replace('[NexusEngine]','').strip()}?"

                # FIX #10: Truncar en límite de oración, no a mitad de palabra
                truncated = content[:1500]
                if len(content) > 1500:
                    last_period = truncated.rfind(".")
                    if last_period > 500:  # Solo si encontramos un punto razonable
                        truncated = truncated[:last_period + 1]

                samples.append({
                    "messages": [
                        {
                            "role":    "system",
                            "content": _IDENTITY_SYSTEM_PROMPT
                        },
                        {
                            "role":    "user",
                            "content": question
                        },
                        {
                            "role":    "assistant",
                            "content": truncated
                        }
                    ],
                    "metadata": {
                        "source":     "research",
                        "category":   entry.category or "General",
                        "confidence": entry.confidence_score or 0.0,
                    }
                })

        finally:
            db.close()
        return samples

    def _build_identity_samples(self) -> List[Dict]:
        """
        Muestras que definen la identidad y personalidad de NOVA.
        Reforzadas con over-sampling para evitar confusión de identidad.
        """
        samples = []
        for _ in range(_IDENTITY_OVERSAMPLING):
            for q, a in _IDENTITY_PAIRS:
                samples.append({
                    "messages": [
                        {
                            "role":    "system",
                            "content": _IDENTITY_SYSTEM_PROMPT
                        },
                        {
                            "role":    "user",
                            "content": q
                        },
                        {
                            "role":    "assistant",
                            "content": a
                        }
                    ],
                    "metadata": {"source": "identity_reinforced"}
                })
        return samples

    # ══════════════════════════════════════════════════════════
    #  EXPORTACIÓN
    # ══════════════════════════════════════════════════════════

    async def _export_dataset(self, samples: List[Dict]) -> Path:
        """Exporta el dataset completo en formato JSONL para fine-tuning."""
        # FIX #7: Usar datetime.now(timezone.utc) en lugar de utcnow()
        timestamp   = datetime.datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        export_file = self.export_path / f"nova_dataset_v10_{timestamp}.jsonl"

        with open(export_file, "w", encoding="utf-8") as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")

        # También exportar versión de estadísticas
        stats_file = self.export_path / f"nova_dataset_stats_{timestamp}.json"
        stats = {
            "total_samples": len(samples),
            "export_date":   timestamp,
            "format":        "ChatML JSONL",
            "compatible_with": [
                "llama.cpp fine-tuning",
                "unsloth",
                "axolotl",
                "transformers SFTTrainer"
            ],
            "finetuning_command": f"python finetune.py --dataset {export_file.name} --model qwen2.5-3b --epochs 3 --lora-r 16"
        }
        stats_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2))

        print(f"[DATASET] Dataset exportado: {export_file.name} ({len(samples)} muestras)")
        return export_file

    def _analyze_dataset(self, samples: List[Dict]) -> Dict[str, Any]:
        """Analiza la composición del dataset."""
        sources = {}
        categories = {}
        avg_length = 0
        counted = 0

        for s in samples:
            src = s.get("metadata", {}).get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1

            cat = s.get("metadata", {}).get("category", "General")
            categories[cat] = categories.get(cat, 0) + 1

            # FIX #9: Calcular longitud promedio buscando el rol assistant dinámicamente
            msgs = s.get("messages", [])
            for msg in msgs:
                if msg.get("role") == "assistant":
                    avg_length += len(msg.get("content", ""))
                    counted += 1
                    break

        return {
            "by_source":        sources,
            "top_categories":   dict(sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]),
            "avg_response_len": round(avg_length / max(counted, 1)),
            "finetuning_ready": len(samples) >= 500,
            "recommended_min":  1000,
        }

    def get_progress(self) -> Dict[str, Any]:
        """Estado actual del dataset."""
        distilled_count = 0
        for f in self.dataset_path.glob("distilled_*.jsonl"):
            try:
                lines = f.read_text(encoding="utf-8").strip().split("\n")
                distilled_count += sum(1 for l in lines if l.strip())
            except Exception:
                pass

        db = SessionLocal()
        try:
            conversations = db.query(ChatLog).count() // 2
            research = db.query(KnowledgeEntry).filter(
                KnowledgeEntry.confidence_score >= 0.65
            ).count()
        finally:
            db.close()

        # FIX #1: Calcular identity_samples dinámicamente
        identity_count = len(_IDENTITY_PAIRS) * _IDENTITY_OVERSAMPLING
        total     = distilled_count + conversations + research + identity_count
        target    = 1000
        progress  = min(100, round(total / target * 100))

        return {
            "distilled_entries":  distilled_count,
            "conversations":      conversations,
            "research_entries":   research,
            "identity_samples":   identity_count,
            "total_estimated":    total,
            "target":             target,
            "progress_percent":   progress,
            "ready":              total >= target,
            "message":            f"NOVA tiene {total}/{target} muestras ({progress}%) — "
                                  + ("¡Lista para fine-tuning!" if total >= target
                                     else f"Faltan {target-total} muestras"),
        }


# Instancia global
nova_dataset_builder = NOVADatasetBuilder()