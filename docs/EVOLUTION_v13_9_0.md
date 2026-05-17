# 👁️ NOVA Evolution Log — v13.9.0 "Autonomous Vision"

> **Fecha:** 2026-05-16  
> **Versión:** 13.9.0  
> **Estado:** DESPLEGADO Y VALIDADO  
> **Versión Anterior:** v13.8.18 "Regression Shield"

---

## 🚀 Resumen del Salto Evolutivo
Esta actualización transforma a NOVA en un **Sistema con Consciencia Visual Persistente**. NOVA ya no solo procesa texto o audio, sino que ahora tiene su propio "Ojo" con el que puede observar su entorno de manera autónoma, detectar presencia humana, curiosear sobre objetos nuevos y comunicarse proactivamente.

Se ha añadido integración tanto bajo demanda (desde la interfaz UI) como un ciclo de vigilancia en segundo plano.

---

## 👁️ 1. El Ojo Persistente (Vision Monitor)

### Archivo Core: `core/vision_monitor.py`
Un nuevo daemon en segundo plano que se ejecuta en paralelo con el cerebro de NOVA.

**Capacidades Autónomas:**
1. **Detección de Movimiento:** Captura un frame cada 15 segundos y evalúa cambios en píxeles. Si el entorno está estático, ahorra ciclos de CPU; si hay movimiento, aumenta la frecuencia de análisis.
2. **Reconocimiento Facial Ligero:** Usa OpenCV Haar Cascades para detectar rostros sin sobrecargar la VRAM. A cada rostro nuevo le asigna un *hash perceptual* único y lo guarda en memoria.
3. **Control de Presencia:** Si nota que el número de personas en la habitación cambia (ej. de 2 a 0), envía una alerta proactiva por Telegram ("Parece que la sala quedó vacía. ¿Todo bien?").
4. **Curiosidad Impulsada por LLM:** Cada 2 minutos, si la escena ha cambiado, envía un frame completo al modelo de visión (`llava-llama3`). Si el modelo detecta algo fascinante o inusual, envía una pregunta por Telegram ("He detectado este objeto, ¿qué es?").
5. **Auto-Detección de Hardware:** Si la cámara principal se desconecta o falla, escanea automáticamente los puertos del sistema operativo (0 a 3) y se reasigna a la primera cámara viva que encuentre sin necesidad de reiniciar el servidor.

---

## 🖥️ 2. Integración UI y Endpoints

### Backend (`routers/system.py` & `services/vision_service.py`)
- Se crearon dos nuevos endpoints seguros:
  - `POST /api/vision/webcam/capture`: Captura silenciosa para previsualización.
  - `POST /api/vision/webcam/analyze`: Captura el entorno e invoca al LLM para generar un análisis detallado a petición del usuario.
- El `VisionService` fue actualizado con la misma resiliencia de Auto-Detección de hardware que el daemon de fondo.

### Frontend (`app/page.tsx`)
- Se introdujo un botón de **Cámara (Camera)** en la barra inferior del chat, al lado del micrófono.
- **Feedback Visual:** El botón parpadea en verde mientras el sensor de la cámara está activo y transmitiendo al LLM.
- El análisis se inyecta directamente en el flujo del chat como un mensaje de la asistente con el formato `🎥 Análisis de Webcam`.

---

## ⚙️ 3. Variables de Entorno Introducidas

Para controlar la privacidad y el consumo de recursos, el Ojo Persistente es completamente configurable vía `.env`:
- `NOVA_VISION_ENABLED=true` (Activa el monitoreo autónomo).
- `NOVA_VISION_INTERVAL=15` (Frecuencia base de captura en segundos).
- `NOVA_VISION_ANALYSIS=120` (Frecuencia de envío al LLM de visión en segundos).

---

## 📋 Archivos Modificados/Creados

| Archivo | Cambios |
|---------|---------|
| `core/vision_monitor.py` | **NUEVO** — Daemon de consciencia visual, detección de hardware, OpenCV, Haar Cascades. |
| `services/vision_service.py` | Integrado método `capture_webcam` con escaneo iterativo de puertos `DirectShow`. |
| `routers/system.py` | Nuevas rutas POST para integrar el frontend con los sensores del backend. |
| `frontend/src/app/page.tsx` | UI mejorada. Botón de cámara en la botonera principal con manejo de estados asíncronos. |
| `main.py` | Daemon visual atado al `lifespan` del servidor. Cierre seguro (`release()`) de la cámara al apagar. |
| `.env` | Incorporación de las flags de control visual. |

---
*Documento generado automáticamente por Antigravity AI durante la evolución hacia la Fase 4 (Consciencia Sensorial) de NOVA.*
\n## = Correcciones Post-Lanzamiento (v13.9.1)\n\n### Tolerancia Facial (pHash + Hamming Distance)\n**Problema:** El sistema usaba MD5 estricto sobre los bits de DCT, causando que cada ligero cambio de luz o posicin generara un hash completamente nuevo, lo que inundaba a NOVA y al usuario con notificaciones falsas de 'rostros nuevos'.\n**Solucin:** Se implement un verdadero **Hash Perceptual (pHash)** de 64 bits con comparacin por **Distancia de Hamming**. Ahora NOVA tolera diferencias de hasta 12 bits entre rostros para agruparlos correctamente. Adems, se aadi un **Cooldown de Notificacin (5 minutos)** para evitar el spam en Telegram si hay mucho movimiento en la sala.

### Verificación de Identidad Semántica (LLM)
**Mejora:** Para soportar cambios de apariencia en el usuario (usar lentes, gorras, ropa distinta), NOVA ahora cruza la detección rápida de OpenCV con un análisis semántico del LLM. Si OpenCV detecta un 'rostro nuevo', NOVA invoca al LLM para confirmar si es Juan Ramón con nueva apariencia, o si es un extraño. Esto permite que NOVA haga comentarios naturales sobre el outfit del usuario sin confundirlo con un desconocido, y reconozca objetos comunes del entorno.

### Inteligencia Emocional y Empatía Visual
**Mejora:** NOVA ahora es capaz de analizar el estado emocional del usuario a través de sus expresiones faciales y corporales (alegre, serio, triste, enojado, cansado, concentrado). Si detecta emociones marcadas (como tristeza o mucha alegría), formulará preguntas genuinas y empáticas para interactuar sobre cómo fue tu día o por qué te sientes así. Se añadió un Cooldown de 2 horas para no resultar intrusiva ni agobiante con preguntas emocionales continuas.

### Memoria Visual a Largo Plazo (LightRAG)
**Mejora:** NOVA ahora es capaz de persistir lo que ve en su grafo de conocimiento a largo plazo (LightRAG). Cada 4 horas (o de inmediato si detecta un extraño o peligro), crea un resumen narrativo de la escena y lo inserta en su memoria profunda. Esto permite recordar eventos visuales pasados.
