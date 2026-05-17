import os
import time
import base64
import logging
import json
import pyautogui
import mss
import cv2
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.llm_gateway import llm_gateway
from core.config import LLM_MODEL_NAME

logger = logging.getLogger("nova.vision")

# Configuración de PyAutoGUI para seguridad
pyautogui.FAILSAFE = True  # Mover el ratón a una esquina aborta la ejecución
pyautogui.PAUSE = 0.5      # Pausa entre comandos para evitar saturación

class VisionService:
    def __init__(self):
        self.sct = mss.mss()
        self.base_dir = Path(__file__).resolve().parent.parent
        self.screenshots_dir = self.base_dir / "data" / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def capture_screen(self, filename: str = "current_screen.png") -> Dict[str, Any]:
        """Captura la pantalla completa y retorna la ruta y los datos base64."""
        try:
            path = self.screenshots_dir / filename
            monitor = self.sct.monitors[1] if len(self.sct.monitors) > 1 else self.sct.monitors[0]
            screenshot = self.sct.grab(monitor)
            
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            cv2.imwrite(str(path), img)
            
            with open(path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            
            logger.info(f"Pantalla capturada en {path}")
            return {"path": str(path), "b64": encoded_string}
        except Exception as e:
            logger.error(f"Error capturando pantalla: {e}")
            return {"path": "", "b64": ""}

    def capture_webcam(self, camera_index: int = 0, filename: str = "webcam_capture.jpg") -> Dict[str, Any]:
        """
        v13.8.18: Captura un frame de la cámara web del usuario.
        Auto-detecta la primera cámara disponible si el índice inicial falla.
        """
        cap = None
        try:
            # Intentar usar el índice proporcionado (o el último conocido)
            target_index = getattr(self, '_current_camera_index', camera_index)
            
            # v13.9.5: Compatibilidad multiplataforma (CAP_DSHOW solo funciona en Windows)
            if os.name == 'nt':
                cap = cv2.VideoCapture(target_index, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(target_index)
            
            # Auto-búsqueda si no abre
            if not cap.isOpened():
                logger.warning(f"[VisionService] Cámara {target_index} no disponible. Buscando alternativas...")
                cap = None
                for i in range(4):
                    temp_cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                    if temp_cap.isOpened():
                        ret, _ = temp_cap.read()
                        if ret:
                            self._current_camera_index = i
                            cap = temp_cap
                            logger.info(f"[VisionService] 📸 Cámara encontrada en índice {i}")
                            break
                        else:
                            temp_cap.release()

            if cap is None or not cap.isOpened():
                logger.error("No se pudo abrir ninguna cámara web.")
                return {"success": False, "error": "Cámara no disponible", "b64": ""}

            # Configurar resolución máxima disponible para capturas manuales
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            
            # Descartar los primeros frames para que la cámara se ajuste
            for _ in range(5):
                cap.read()

            ret, frame = cap.read()
            if not ret or frame is None:
                self._current_camera_index = -1
                logger.error("No se pudo leer el frame de la cámara.")
                return {"success": False, "error": "Frame vacío", "b64": ""}

            # Guardar imagen
            path = self.screenshots_dir / filename
            cv2.imwrite(str(path), frame)

            # Codificar a base64 (JPEG para menor tamaño)
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            b64_image = base64.b64encode(buffer).decode("utf-8")

            logger.info(f"Webcam capturada: {frame.shape[1]}x{frame.shape[0]} → {path}")
            return {
                "success": True,
                "path": str(path),
                "b64": b64_image,
                "resolution": f"{frame.shape[1]}x{frame.shape[0]}"
            }
        except Exception as e:
            logger.error(f"Error capturando webcam: {e}")
            return {"success": False, "error": str(e), "b64": ""}
        finally:
            if cap is not None:
                cap.release()


    async def find_element_on_screen(self, description: str) -> Dict[str, Any]:
        """Usa el LLM para localizar un elemento específico en la pantalla."""
        res = self.capture_screen()
        b64_image = res["b64"]
        if not b64_image:
            return {"success": False, "error": "No se pudo capturar la pantalla."}

        # Prompt de Visual Grounding (Inspirado en Mark-XXXIX)
        prompt = f"""
        Analiza esta captura de pantalla de Windows.
        Tu objetivo es localizar el elemento descrito por el usuario: "{description}"
        
        INSTRUCCIONES:
        1. Identifica las coordenadas (x, y) del CENTRO del elemento.
        2. Las coordenadas deben estar en una escala de 0 a 1000 (donde 0,0 es arriba-izquierda y 1000,1000 es abajo-derecha).
        3. Indica el tipo de elemento (botón, campo de texto, icono, etc.).
        
        Responde ÚNICAMENTE en JSON con este formato:
        {{
            "found": true/false,
            "x": número,
            "y": número,
            "element_type": "string",
            "confidence": 0.0 a 1.0
        }}
        """

        try:
            # v13.0: Usamos el carril realtime para respuesta inmediata
            response = await llm_gateway.chat(
                [{"role": "user", "content": prompt}],
                lane="realtime",
                images=[b64_image],
                priority=0
            )
            
            # Limpiar y parsear JSON
            clean_res = response.strip().replace("```json", "").replace("```", "")
            data = json.loads(clean_res)
            
            if data.get("found"):
                # Convertir escala 0-1000 a píxeles reales del monitor
                screen_width, screen_height = pyautogui.size()
                real_x = int((data["x"] / 1000) * screen_width)
                real_y = int((data["y"] / 1000) * screen_height)
                data["real_x"] = real_x
                data["real_y"] = real_y
            
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Error analizando pantalla: {e}")
            return {"success": False, "error": str(e)}

    def click(self, x: int, y: int, clicks: int = 1):
        """Hace clic en una coordenada específica."""
        try:
            pyautogui.click(x, y, clicks=clicks)
            logger.info(f"Clic ejecutado en ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"Error haciendo clic: {e}")
            return False

    def type_text(self, text: str):
        """Escribe texto en el teclado."""
        try:
            pyautogui.write(text, interval=0.1)
            logger.info(f"Texto escrito: {text[:20]}...")
            return True
        except Exception as e:
            logger.error(f"Error escribiendo: {e}")
            return False

    def press_key(self, key: str):
        """Presiona una tecla especial (enter, esc, etc)."""
        try:
            pyautogui.press(key)
            return True
        except Exception as e:
            return False

    def calibrate(self) -> str:
        """Mueve el ratón por los puntos clave para verificar la calibración."""
        try:
            # Puntos cardinales del escritorio
            screen_width, screen_height = pyautogui.size()
            points = [
                (100, 100, "Arriba-Izquierda"),
                (screen_width - 100, 100, "Arriba-Derecha"),
                (screen_width - 100, screen_height - 100, "Abajo-Derecha"),
                (100, screen_height - 100, "Abajo-Izquierda"),
                (screen_width // 2, screen_height // 2, "Centro")
            ]
            
            for x, y, label in points:
                pyautogui.moveTo(x, y, duration=0.5)
                time.sleep(0.3)
            
            return "Rutina de calibración completada. ¿El puntero se movió correctamente a las esquinas y al centro?"
        except Exception as e:
            return f"Error en calibración: {e}"

    def snap_to_grid(self, x: int, y: int) -> Tuple[int, int]:
        """Ajusta una coordenada a la cuadrícula conocida del usuario (opcional)."""
        # Si está cerca de y=110, podemos asumir que es la fila de iconos
        if abs(y - 110) < 30:
            # Buscar la columna más cercana (cada 60px aprox)
            # Basado en Col 2 = 140, Col 3 = 200, etc.
            # offset = 140 - (2 * 60) = 20
            # x_ideal = (col_index * 60) + 20
            col_index = round((x - 20) / 60)
            snapped_x = (col_index * 60) + 20
            return snapped_x, 110
        return x, y

# Singleton
vision_service = VisionService()
