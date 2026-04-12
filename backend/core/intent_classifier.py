"""
Clasificador de intenciones determinístico de NOVA.
Usa keywords/regex para el 90% de los casos.
Solo recurre al LLM cuando la query es ambigua.
"""
import re

# ── FAST PATH: Clasificación por keywords (O(n) con n = keywords) ──

_GREETINGS = {
    "hola", "hi", "hello", "hey", "buenos días", "buenas tardes",
    "buenas noches", "cómo estás", "como estas", "que tal", "qué tal",
    "saludos", "qué onda", "que onda", "buenas", "buen día",
}

_CHAT_PATTERNS = [
    r"^(gracias|thanks|ok|vale|genial|perfecto|cool|entendido|dale|listo|claro|okey|de acuerdo)[\s!.]*$",
    r"^(ja|jaja|jajaja|lol|xd|😂|😄|🤣)",
    r"^(adiós|bye|chao|nos vemos|hasta luego|hasta mañana)",
    r"^(sí|no|si|nope|nah|sep|nel)[\s!.]*$",
]

_PROJECT_BUILD_TRIGGERS = [
    r"adelante", r"constr[uú]yelo?", r"build", r"empaqu[eé]talo", 
    r"procede", r"hazlo", r"apruebo", r"contin[uú]a", r"empieza", r"arm[ea]"
]

_SYSTEM_TRIGGERS = [
    r"estado.*sistema", r"análisis.*sistema", r"como.*sistema",
    r"arquitectura", r"modelo", r"agentes", r"status", r"backend",
    r"qué.*modelo", r"cuántos.*documentos",
    r"diagnóstico", r"infraestructura", r"stack", r"versión",
    r"\bcpu\b", r"\bram\b", r"health", r"workers", r"cola.*tareas", r"queue",
    r"logs", r"métricas", r"metrics", r"latencia", r"performance", r"rendimiento",
    r"salud", r"hardware", r"memoria", r"auditoría", r"reporte.*técnico"
]

_RESEARCH_TRIGGERS = [
    r"investiga\b", r"busca\b.*(?:art[ií]culos|papers|información)",
    r"profundiza\b", r"estudia\b", r"explora\b.*(?:tema|tópico)",
    r"quiero.*aprender.*sobre", r"necesito.*informaci[oó]n.*profunda",
    r"hazme.*investigaci[oó]n", r"despliega.*agentes",
    r"inicia.*investigaci[oó]n",
]

_COMPUTATION_TRIGGERS = [
    r"calcula\b", r"computa\b", r"ejecuta\b.*(?:código|code|script)",
    r"escribe.*(?:script|programa|código|function)",
    r"resuelve.*(?:ecuaci[oó]n|problema|matem[aá]tic)",
    r"programa\b.*(?:en|con)\b",
]

_BOOK_TRIGGERS = [
    r"(?:en\s+el\s+)?libro\b", r"(?:del?\s+)?cap[ií]tulo\b",
    r"(?:la\s+)?lectura\b", r"(?:el\s+)?autor\b.*(?:dice|menciona|escrib)",
    r"según\s+(?:el|la)\s+(?:libro|texto|obra)",
]


async def classify_intent(query: str) -> str:
    """
    Clasifica la intención del usuario de forma determinística.
    Solo recurre al LLM cuando la query es ambigua (< 5% de los casos).
    """
    q_lower = query.strip().lower()
    q_clean = re.sub(r'[¿?¡!.,;:\'"()]', '', q_lower).strip()

    # ── NIVEL 1: Fuzzy Greeting & Substring Match (O(n)) ──
    # Si la query empieza con un saludo o es muy corta y contiene uno
    if any(q_clean.startswith(g) for g in _GREETINGS) or \
       (len(q_clean.split()) <= 4 and any(g in q_clean for g in _GREETINGS)):
        return "CONVERSATION"

    # ── NIVEL 2: Regex patterns (determinístico) ──
    for pattern in _CHAT_PATTERNS:
        if re.match(pattern, q_clean, re.IGNORECASE):
            return "CONVERSATION"

    for pattern in _RESEARCH_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "RESEARCH"

    for pattern in _COMPUTATION_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "COMPUTATION"

    for pattern in _BOOK_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "BOOK_QUERY"

    # ── NIVEL 2.5: Proyecto Start ──
    for pattern in _PROJECT_BUILD_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "PROJECT_BUILD"

    # ── NIVEL 3: Regex matching para SYSTEM ──
    for pattern in _SYSTEM_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "SYSTEM"

    # ── NIVEL 4: Heurísticas de longitud y estructura ──
    word_count = len(q_clean.split())

    # Queries muy cortas sin keywords de research → probablemente chat (Hola Nova, etc)
    if word_count <= 4 and not any(c == '?' for c in query):
        return "CONVERSATION"

    # Queries que son preguntas informativas → KNOWLEDGE
    if any(q_lower.startswith(p) for p in [
        "qué es", "que es", "qué son", "que son", "cómo funciona",
        "como funciona", "cuál es", "cual es", "por qué", "por que",
        "explica", "describe", "dime sobre", "háblame de", "hablame de",
        "qué sabes", "que sabes", "resume", "resumen",
    ]):
        return "KNOWLEDGE"

    # ── NIVEL 5: LLM fallback (solo queries genuinamente ambiguas) ──
    return await _llm_classify_fallback(query)


async def _llm_classify_fallback(query: str) -> str:
    """Fallback al LLM solo para queries ambiguas. ~5% de los casos."""
    try:
        from core.llm_client import llm_client  # type: ignore
        prompt = (
            "Clasifica esta consulta en UNA sola categoría: "
            "KNOWLEDGE, RESEARCH, CONVERSATION, COMPUTATION, BOOK_QUERY, SYSTEM, PROJECT_BUILD.\n"
            f"Consulta: {query}\n"
            "Responde SOLO la palabra clave en mayúsculas."
        )
        response = await llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            priority=0  # Vital: El clasificador es parte del flujo de chat, no debe abortarse
        )
        intent = response.strip().upper()
        # v10.9.1: Mapeo estricto para evitar alucinaciones
        valid_intents = ["PROJECT_BUILD", "KNOWLEDGE", "RESEARCH", "CONVERSATION", "COMPUTATION", "BOOK_QUERY", "SYSTEM"]
        for valid in valid_intents:
            if valid in intent:
                return valid
    except Exception as e:
        print(f"[IntentClassifier] LLM fallback error: {e}")

    return "KNOWLEDGE"  # Default seguro
