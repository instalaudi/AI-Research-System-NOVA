# 🎨 NOVA Premium Design System (DESIGN.md)

Este es el **manifiesto de diseño obligatorio** para cualquier interfaz de usuario (web/móvil) generada por NOVA.  
El incumplimiento de estas reglas será considerado un **FALLO** por el Agente Auditor.

---

## 1. PRINCIPIOS VISUALES (Estética Modernista)

- **Glassmorphism & profundidad**:  
  Usa `backdrop-filter: blur()`, bordes translúcidos (ej. `border: 1px solid rgba(255,255,255,0.1)`), sombras suaves (`box-shadow`) y tarjetas flotantes.

- **Paletas de color HSL**:  
  Prohibido usar colores primarios básicos (`red`, `blue`, `green`) como colores **principales** de la interfaz.  
  ✅ **Excepción**: Se permiten para señalar **estados semánticos** (error, éxito, advertencia) con moderación.  
  Ejemplo: `color: #d32f2f` para errores, `color: #2e7d32` para mensajes de éxito.

- **Tipografía moderna con fallback**:  
  Usa fuentes Sans‑Serif importadas de Google Fonts (Inter, Roboto, Poppins, Outfit).  
  **Siempre incluye una cadena de fallback segura**:  
  `font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;`  
  (Nunca uses `Times New Roman`).

- **Espaciado generoso**:  
  Aplica `padding` y `margin` amplios. Evita interfaces congestionadas.

---

## 2. INTERACTIVIDAD Y MICRO‑ANIMACIONES

- **Hover effects**:  
  Todo elemento interactivo debe tener estado `:hover` con `transition: all 0.3s ease`.

- **Feedback visual**:  
  Usa animaciones suaves en carga, clic o aparición (`@keyframes fade-in`, `slide-up`).

---

## 3. ARQUITECTURA UI

- **Semántica HTML**: `<header>`, `<main>`, `<section>`, `<footer>`, `<aside>`.
- **Responsive design**:  
  Obligatorio usar Flexbox o CSS Grid. La interfaz debe funcionar en móvil y escritorio.
- **Accesibilidad básica**:  
  Contraste mínimo 4.5:1, texto legible, `cursor: pointer` en elementos interactivos.

---

## 4. PROHIBICIONES ESTRICTAS ❌

| Lo que **no** está permitido |
|------------------------------|
| Fondos planos blancos o grises aburridos |
| Botones cuadrados sin `cursor: pointer` |
| Texto ilegible o contraste pobre |
| Placeholders ("// tu código aquí") o imágenes rotas |
| Estilos inline (todo CSS en `<style>` o archivos externos) |
| Falta de compatibilidad con Safari (`-webkit-backdrop-filter` obligatorio si usas `backdrop-filter`) |

---

## ✅ Criterios de aprobación (para el Agente Auditor)

Una interfaz será **aprobada** si cumple **todos** los puntos:

- [ ] Usa glassmorphism o diseño moderno equivalente.
- [ ] Paleta de colores elegante (no primarios básicos como dominantes).
- [ ] Tipografía moderna con fallback.
- [ ] Espaciado generoso y responsive.
- [ ] Micro‑animaciones presentes.
- [ ] Código limpio, sin placeholders.
- [ ] Compatible con navegadores modernos (Chrome, Firefox, Safari).

> **Crítica**: Si el diseño parece hecho por una agencia de diseño de élite, aprueba. Si es mediocre o básico, **rechaza**.

---
> [!NOTE]
> **Auto‑optimización** (sistema interno): Esta guía se actualiza con nuevos patrones de accesibilidad y tendencias de diseño.
