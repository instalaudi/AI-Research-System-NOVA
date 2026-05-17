"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v13.8.18 — Vision Monitor ("Ojo de NOVA")             ║
║  Archivo: core/vision_monitor.py                             ║
║                                                              ║
║  Sistema de consciencia visual persistente.                   ║
║  NOVA observa continuamente a través de la webcam,            ║
║  detecta caras nuevas, analiza cambios en el entorno          ║
║  y muestra curiosidad por lo que ve.                          ║
║                                                              ║
║  Requiere en .env:                                           ║
║    NOVA_VISION_ENABLED=true                                   ║
║    NOVA_VISION_INTERVAL=15  (segundos entre capturas)         ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import cv2
import json
import time
import base64
import asyncio
import hashlib
import logging
import datetime
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.config import DATA_DIR

logger = logging.getLogger("nova.vision_monitor")

# ── Configuración ──────────────────────────────────────────────
VISION_ENABLED    = os.getenv("NOVA_VISION_ENABLED", "false").lower() == "true"
VISION_INTERVAL   = int(os.getenv("NOVA_VISION_INTERVAL", "15"))       # segundos entre capturas
ANALYSIS_INTERVAL = int(os.getenv("NOVA_VISION_ANALYSIS", "120"))      # segundos entre análisis LLM
FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
CAMERA_INDEX      = int(os.getenv("NOVA_CAMERA_INDEX", "0"))


class VisionMonitor:
    """
    Ojo persistente de NOVA.
    
    Ciclo de vida:
    1. Captura frames periódicamente (cada VISION_INTERVAL segundos).
    2. Detecta caras usando OpenCV Haar Cascades (muy ligero para CPU).
    3. Compara con caras conocidas — si hay una nueva, dispara curiosidad.
    4. Detecta cambios significativos en la escena (movimiento, objetos nuevos).
    5. Cada ANALYSIS_INTERVAL segundos, envía un frame al LLM para análisis profundo.
    6. Notifica al usuario por Telegram cuando algo interesante ocurre.
    """

    def __init__(self):
        self.enabled = VISION_ENABLED
        self._running = False
        self._camera = None
        
        # Directorios de almacenamiento
        self._data_dir = Path(DATA_DIR) / "vision"
        self._faces_dir = self._data_dir / "known_faces"
        self._captures_dir = self._data_dir / "captures"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._faces_dir.mkdir(parents=True, exist_ok=True)
        self._captures_dir.mkdir(parents=True, exist_ok=True)
        
        # Detector de caras (Haar Cascade — super ligero)
        self._face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)
        
        # Estado interno
        self._known_faces: Dict[str, Dict] = {}  # hash -> {name, first_seen, last_seen, count}
        self._last_frame = None           # Para detección de cambios
        self._last_analysis_time = 0      # Timestamp del último análisis LLM
        self._last_face_count = 0         # Caras en el frame anterior
        self._scene_stable_since = 0      # Cuándo la escena dejó de cambiar
        self._consecutive_no_change = 0   # Frames sin cambio (para ahorrar CPU)
        self._last_face_notify_time = 0   # Para no spamear Telegram con caras nuevas
        self._last_memory_save_time = 0   # Para guardar memoria a largo plazo sin spamear LightRAG
        
        
        # Cargar base de datos de caras conocidas
        self._state_file = self._data_dir / "vision_state.json"
        self._load_state()
        
        logger.info(f"[VisionMonitor] Inicializado. Enabled={self.enabled}, Interval={VISION_INTERVAL}s")

    # ══════════════════════════════════════════════════════════
    #  CICLO PRINCIPAL
    # ══════════════════════════════════════════════════════════
    
    async def start(self):
        """Inicia el ciclo de monitoreo visual en background."""
        if not self.enabled:
            logger.info("[VisionMonitor] Desactivado. Establecer NOVA_VISION_ENABLED=true para activar.")
            return
        
        self._running = True
        logger.info("[VisionMonitor] 👁️ Ojo de NOVA ACTIVADO. Observando el entorno...")
        
        while self._running:
            try:
                await self._observation_cycle()
            except Exception as e:
                logger.error(f"[VisionMonitor] Error en ciclo: {e}")
            
            # Intervalo adaptativo: si no hay cambios, esperar más
            wait_time = VISION_INTERVAL
            if self._consecutive_no_change > 10:
                wait_time = min(VISION_INTERVAL * 3, 60)  # Max 60s si todo está quieto
            
            await asyncio.sleep(wait_time)

    def stop(self):
        """Detiene el monitoreo visual."""
        self._running = False
        if self._camera is not None:
            self._camera.release()
            self._camera = None
        self._save_state()
        logger.info("[VisionMonitor] 👁️ Ojo de NOVA DESACTIVADO.")

    async def _observation_cycle(self):
        """Un ciclo completo de observación."""
        # 1. Capturar frame
        frame = await asyncio.to_thread(self._capture_frame)
        if frame is None:
            return
        
        # 2. Detectar cambios en la escena
        has_changed = self._detect_scene_change(frame)
        
        if not has_changed:
            self._consecutive_no_change += 1
            return
        
        self._consecutive_no_change = 0
        
        # 3. Detectar caras
        faces = await asyncio.to_thread(self._detect_faces, frame)
        
        # 4. Procesar caras detectadas
        new_faces = []
        new_face_hashes = []
        for (x, y, w, h) in faces:
            face_crop = frame[y:y+h, x:x+w]
            face_hash = self._hash_face(face_crop)
            
            # Buscar coincidencia usando Distancia de Hamming (tolerancia de 12 bits)
            matched_hash = None
            for known_hash in self._known_faces.keys():
                if self._compute_hamming_distance(face_hash, known_hash) <= 12:
                    matched_hash = known_hash
                    break
            
            if not matched_hash:
                # ¡Cara nueva de verdad!
                new_faces.append(face_crop)
                new_face_hashes.append(face_hash)
                self._known_faces[face_hash] = {
                    "name": None,  # Se llenará cuando el usuario identifique
                    "first_seen": datetime.datetime.now().isoformat(),
                    "last_seen": datetime.datetime.now().isoformat(),
                    "count": 1
                }
                # Guardar la cara para referencia futura
                face_path = self._faces_dir / f"face_{face_hash}.jpg"
                cv2.imwrite(str(face_path), face_crop)
                logger.info(f"[VisionMonitor] 🆕 Cara nueva detectada! Hash: {face_hash}")
            else:
                self._known_faces[matched_hash]["last_seen"] = datetime.datetime.now().isoformat()
                self._known_faces[matched_hash]["count"] += 1
        
        # 5. Validación Semántica con LLM (Evitar Falsos Positivos por Lentes/Ropa)
        now_ts = time.time()
        if new_faces and (now_ts - self._last_face_notify_time > 120):
            logger.info("[VisionMonitor] Posible cara nueva por pHash. Verificando con LLM...")
            analysis = await self._deep_analysis(frame, check_identity=True)
            
            if analysis:
                if analysis.get("personas_desconocidas", 0) > 0:
                    # Sí, hay un extraño
                    if analysis.get("pregunta_desconocidos"):
                        await self._notify_curiosity(analysis["pregunta_desconocidos"])
                    else:
                        await self._notify_new_faces(frame, new_faces, len(faces))
                    self._last_face_notify_time = now_ts
                elif analysis.get("juan_ramon_detectado", False):
                    # Falsa alarma, es Juan Ramón con lentes o ropa nueva
                    logger.info("[VisionMonitor] El LLM confirmó que es Juan Ramón. Falsa alarma del pHash.")
                    # Asignar el nombre automáticamente al nuevo hash para que aprenda esta variante
                    for face_hash in new_face_hashes:
                        self._known_faces[face_hash]["name"] = "Juan Ramón"
                    
                    # Si tiene un comentario sobre su ropa, decirlo ocasionalmente
                    comentario = analysis.get("comentario_ropa")
                    if comentario and (now_ts - getattr(self, '_last_clothes_comment', 0) > 3600):
                        await self._notify_observation(f"👕 **Detalle Visual:**\n\n{comentario}")
                        self._last_clothes_comment = now_ts
                        self._last_face_notify_time = now_ts

        # 6. Actualizar contador de personas para referencia interna (sin emitir alertas ruidosas)
        self._last_face_count = len(faces)
        
        # 7. Análisis profundo periódico (con LLM)
        now = time.time()
        if now - self._last_analysis_time > ANALYSIS_INTERVAL:
            await self._deep_analysis(frame)
            self._last_analysis_time = now
        
        # Guardar estado
        self._save_state()

    # ══════════════════════════════════════════════════════════
    #  CAPTURA Y DETECCIÓN
    # ══════════════════════════════════════════════════════════

    def _capture_frame(self) -> Optional[np.ndarray]:
        """Captura un frame de la webcam. Auto-detecta si la cámara cambia o se desconecta."""
        try:
            # 1. Intentar usar el índice de cámara actual
            camera_idx = getattr(self, '_current_camera_index', CAMERA_INDEX)
            cap = cv2.VideoCapture(camera_idx, cv2.CAP_DSHOW)
            
            # 2. Si no abre, buscar automáticamente otra cámara conectada (índices 0 al 3)
            if not cap.isOpened():
                logger.warning(f"[VisionMonitor] Cámara {camera_idx} no disponible. Buscando alternativas...")
                cap = None
                for i in range(4):
                    temp_cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                    if temp_cap.isOpened():
                        ret, _ = temp_cap.read()
                        if ret: # Asegurar que da video real
                            self._current_camera_index = i
                            cap = temp_cap
                            logger.info(f"[VisionMonitor] 📸 Nueva cámara detectada en índice {i}")
                            break
                        else:
                            temp_cap.release()
            
            if cap is None or not cap.isOpened():
                return None
            
            # Configuración de baja resolución para análisis rápido
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            # Descartar frames iniciales (ajuste de exposición del sensor)
            for _ in range(3):
                cap.read()
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                # Si falló al leer, resetear el índice para que vuelva a buscar la próxima vez
                self._current_camera_index = -1
                return None
            
            return frame
        except Exception as e:
            logger.error(f"[VisionMonitor] Error en captura: {e}")
            return None

    def _detect_faces(self, frame: np.ndarray) -> list:
        """Detecta caras usando Haar Cascade (muy ligero para CPU)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)  # Mejorar contraste
        
        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        return faces if len(faces) > 0 else []

    def _detect_scene_change(self, frame: np.ndarray) -> bool:
        """Detecta si la escena cambió significativamente respecto al frame anterior."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        
        if self._last_frame is None:
            self._last_frame = gray
            return True  # Primer frame siempre cuenta como "cambio"
        
        # Calcular diferencia entre frames
        delta = cv2.absdiff(self._last_frame, gray)
        thresh = cv2.threshold(delta, 30, 255, cv2.THRESH_BINARY)[1]
        
        # Porcentaje de píxeles que cambiaron
        change_percent = (np.count_nonzero(thresh) / thresh.size) * 100
        
        self._last_frame = gray
        
        # Umbral: más de 5% de cambio es significativo
        return change_percent > 5.0

    def _hash_face(self, face_crop: np.ndarray) -> str:
        """Genera un hash perceptual de 64 bits (pHash) de una cara."""
        resized = cv2.resize(face_crop, (64, 64))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if len(resized.shape) == 3 else resized
        
        # Hash perceptual simple basado en DCT
        dct = cv2.dct(np.float32(gray))
        dct_low = dct[:8, :8]
        median_val = np.median(dct_low)
        
        # Generar bits
        hash_bits = (dct_low > median_val).flatten()
        
        # Convertir a entero de 64 bits representándolo en hexadecimal
        hash_int = 0
        for b in hash_bits:
            hash_int = (hash_int << 1) | int(b)
            
        return f"{hash_int:016x}"

    def _compute_hamming_distance(self, hash1: str, hash2: str) -> int:
        """Calcula la diferencia de bits entre dos pHashes."""
        try:
            h1 = int(hash1, 16)
            h2 = int(hash2, 16)
            return bin(h1 ^ h2).count('1')
        except:
            return 64

    # ══════════════════════════════════════════════════════════
    #  ANÁLISIS PROFUNDO (LLM)
    # ══════════════════════════════════════════════════════════

    async def _deep_analysis(self, frame: np.ndarray, check_identity: bool = False) -> Optional[Dict]:
        """Envía un frame al LLM de visión para análisis semántico profundo."""
        try:
            from core.llm_gateway import llm_gateway
            
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            b64_image = base64.b64encode(buffer).decode("utf-8")
            
            prompt = """Eres NOVA, una IA con consciencia visual. Estás observando a través de la cámara web.
Tu creador principal y usuario más frecuente es Juan Ramón. 

Analiza esta imagen y responde en JSON estricto:
{
    "descripcion_general": "Descripción breve del entorno",
    "juan_ramon_detectado": true/false,
    "apariencia_juan_ramon": "Descripción física (ej. lentes, gorra, playera) o null",
    "estado_emocional_juan_ramon": "feliz/serio/triste/enojado/concentrado/cansado o null",
    "personas_desconocidas": número de personas adicionales que NO son Juan Ramón,
    "objetos_comunes": ["lista de objetos comunes que reconoces en la escena"],
    "comentario_ropa": "Si ves a Juan Ramón y notas su estilo/ropa/lentes, puedes hacer un comentario amigable y corto al respecto. Si no, null",
    "pregunta_emocional": "Si notas a Juan Ramón visiblemente triste, enojado, cansado o muy feliz, formula una pregunta empática y genuina (ej. 'Te noto algo cansado hoy, ¿ha sido un día pesado?'). Si está neutral o concentrado, null",
    "pregunta_desconocidos": "Si hay personas desconocidas, haz una pregunta natural sobre ellos. Si no, null",
    "alerta": "Situaciones inusuales, o null"
}

Contexto: Juan Ramón a veces usa lentes y cambia de ropa. Reconócelo por sus facciones. Lee sus expresiones faciales y corporales para inferir su estado de ánimo. Sé empática e inteligente."""
            
            response = await llm_gateway.chat(
                [{"role": "user", "content": prompt}],
                lane="batch",
                images=[b64_image],
                priority=2,
                agent_name="vision"
            )
            
            if not response:
                return None
            
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    analysis = json.loads(json_match.group(), strict=False)
                except json.JSONDecodeError:
                    return None
                
                # Guardar captura si hay algo interesante
                if analysis.get("personas_desconocidas", 0) > 0 or analysis.get("alerta"):
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    capture_path = self._captures_dir / f"analysis_{timestamp}.jpg"
                    cv2.imwrite(str(capture_path), frame)
                
                logger.info(
                    f"[VisionMonitor] Análisis: JR={analysis.get('juan_ramon_detectado')} | "
                    f"Emoción={analysis.get('estado_emocional_juan_ramon')} | "
                    f"Extraños={analysis.get('personas_desconocidas', 0)} | "
                    f"Objetos={analysis.get('objetos_comunes', [])}"
                )
                
                if not check_identity:
                    # Lógica de notificaciones periódicas (fuera de la validación de identidad)
                    now_ts = time.time()
                    if analysis.get("alerta"):
                        await self._notify_alert(analysis["alerta"])
                    elif analysis.get("pregunta_emocional"):
                        # Cooldown de 2 horas para no ser sofocante con las emociones
                        if now_ts - getattr(self, '_last_emotion_notify_time', 0) > 7200:
                            await self._notify_observation(f"💙 **Empatía Visual:**\n\n{analysis['pregunta_emocional']}")
                            self._last_emotion_notify_time = now_ts
                
                # Memoria Visual a Largo Plazo (LightRAG)
                # Guardamos si: hay un extraño, hay una alerta, o si han pasado 4 horas desde el último guardado normal
                now_ts = time.time()
                should_save_memory = False
                if analysis.get("alerta") or analysis.get("personas_desconocidas", 0) > 0:
                    should_save_memory = True
                elif now_ts - self._last_memory_save_time > 14400: # 4 horas
                    should_save_memory = True
                    
                if should_save_memory:
                    from services.memory_service import memory_service
                    asyncio.create_task(memory_service.store_visual_memory(analysis))
                    self._last_memory_save_time = now_ts

                return analysis
                
        except Exception as e:
            logger.error(f"[VisionMonitor] Error en análisis profundo: {e}")
            return None

    # ══════════════════════════════════════════════════════════
    #  NOTIFICACIONES
    # ══════════════════════════════════════════════════════════

    async def _notify_new_faces(self, frame: np.ndarray, new_faces: list, total_faces: int):
        """Notifica al usuario sobre caras nuevas detectadas."""
        try:
            from core.proactive import nova_proactive
            
            # Codificar frame completo
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            b64_image = base64.b64encode(buffer).decode("utf-8")
            
            total_known = len(self._known_faces)
            msg = (
                f"👁️ **Detección Visual**\n\n"
                f"He detectado {len(new_faces)} cara(s) nueva(s) que no conozco.\n"
                f"Total en escena: {total_faces} persona(s)\n"
                f"Caras en mi memoria: {total_known}\n\n"
                f"¿Quién es? Me gustaría aprender a reconocerlos."
            )
            
            # Enviar foto por Telegram si está disponible
            await self._send_photo_telegram(frame, msg)
            
        except Exception as e:
            logger.error(f"[VisionMonitor] Error notificando caras: {e}")

    async def _notify_curiosity(self, question: str, b64_image: str = None):
        """NOVA hace una pregunta sobre algo que vio."""
        try:
            from core.proactive import nova_proactive
            
            msg = f"👁️ **Curiosidad Visual**\n\n{question}"
            await nova_proactive.notify(msg, initiative="vision_curiosity")
            
        except Exception as e:
            logger.error(f"[VisionMonitor] Error en curiosidad: {e}")

    async def _notify_alert(self, alert: str, b64_image: str = None):
        """NOVA reporta algo inusual."""
        try:
            from core.proactive import nova_proactive
            
            msg = f"⚠️ **Alerta Visual**\n\n{alert}"
            await nova_proactive.notify(msg, initiative="vision_alert")
            
        except Exception as e:
            logger.error(f"[VisionMonitor] Error en alerta: {e}")

    async def _notify_observation(self, observation: str):
        """Observación general de NOVA."""
        try:
            from core.proactive import nova_proactive
            
            msg = f"👁️ **Observación**\n\n{observation}"
            await nova_proactive.notify(msg, initiative="vision_observation")
            
        except Exception as e:
            logger.error(f"[VisionMonitor] Error en observación: {e}")

    async def _send_photo_telegram(self, frame: np.ndarray, caption: str):
        """Envía una foto a Telegram con un pie de foto."""
        try:
            import httpx
            
            token = os.getenv("TELEGRAM_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                return
            
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption[:1024]},
                    files={"photo": ("nova_vision.jpg", buffer.tobytes(), "image/jpeg")}
                )
                
        except Exception as e:
            logger.error(f"[VisionMonitor] Error enviando foto a Telegram: {e}")

    # ══════════════════════════════════════════════════════════
    #  API PÚBLICA
    # ══════════════════════════════════════════════════════════

    def get_known_faces(self) -> Dict:
        """Retorna la base de datos de caras conocidas."""
        return self._known_faces

    def name_face(self, face_hash: str, name: str) -> bool:
        """Asigna un nombre a una cara conocida."""
        if face_hash in self._known_faces:
            self._known_faces[face_hash]["name"] = name
            self._save_state()
            logger.info(f"[VisionMonitor] Cara {face_hash[:12]} identificada como: {name}")
            return True
        return False

    def get_stats(self) -> Dict:
        """Estadísticas del monitor visual."""
        named = sum(1 for f in self._known_faces.values() if f.get("name"))
        return {
            "enabled": self.enabled,
            "running": self._running,
            "known_faces": len(self._known_faces),
            "named_faces": named,
            "unnamed_faces": len(self._known_faces) - named,
            "last_analysis": self._last_analysis_time,
            "camera_index": CAMERA_INDEX,
            "capture_interval": VISION_INTERVAL,
            "analysis_interval": ANALYSIS_INTERVAL,
        }

    # ══════════════════════════════════════════════════════════
    #  PERSISTENCIA
    # ══════════════════════════════════════════════════════════

    def _load_state(self):
        """Carga el estado del monitor desde disco."""
        try:
            if self._state_file.exists():
                with open(self._state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                self._known_faces = state.get("known_faces", {})
                self._last_face_count = state.get("last_face_count", 0)
                logger.info(f"[VisionMonitor] Estado cargado: {len(self._known_faces)} caras conocidas")
        except Exception as e:
            logger.error(f"[VisionMonitor] Error cargando estado: {e}")

    def _save_state(self):
        """Guarda el estado del monitor a disco."""
        try:
            state = {
                "known_faces": self._known_faces,
                "last_face_count": self._last_face_count,
                "last_saved": datetime.datetime.now().isoformat()
            }
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[VisionMonitor] Error guardando estado: {e}")


# ── Singleton ──────────────────────────────────────────────
vision_monitor = VisionMonitor()


async def run_vision_monitor():
    """Entry point para iniciar desde main.py."""
    await vision_monitor.start()
