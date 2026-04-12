import asyncio
import re

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
    q_lower = query.strip().lower()
    q_clean = re.sub(r'[¿?¡!.,;:\'"()]', '', q_lower).strip()

    if any(q_clean.startswith(g) for g in _GREETINGS) or \
       (len(q_clean.split()) <= 4 and any(g in q_clean for g in _GREETINGS)):
        return "CONVERSATION (L1)"

    for pattern in _CHAT_PATTERNS:
        if re.match(pattern, q_clean, re.IGNORECASE):
            return "CONVERSATION (L2)"

    for pattern in _RESEARCH_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "RESEARCH (L2)"

    for pattern in _COMPUTATION_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "COMPUTATION (L2)"

    for pattern in _BOOK_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "BOOK_QUERY (L2)"

    for pattern in _SYSTEM_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "SYSTEM (L3)"

    word_count = len(q_clean.split())

    if word_count <= 4 and not any(c == '?' for c in query):
        return "CONVERSATION (L4)"

    if any(q_lower.startswith(p) for p in [
        "qué es", "que es", "qué son", "que son", "cómo funciona",
        "como funciona", "cuál es", "cual es", "por qué", "por que",
        "explica", "describe", "dime sobre", "háblame de", "hablame de",
        "qué sabes", "que sabes", "resume", "resumen",
    ]):
        return "KNOWLEDGE (L4)"

    return "FALLBACK (L5)"

async def main():
    res = await classify_intent("Dame un análisis detallado del estado actual del sistema")
    print(f"Result: {res}")

if __name__ == "__main__":
    asyncio.run(main())
