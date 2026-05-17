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
    r"construye\s+el\s+proyecto", r"genera\s+código", r"desarrolla\s+aplicación", 
    r"crea\s+programa", r"build\s+project", r"empaqu[eé]talo\s+todo",
    r"procede\b", r"adelante\b", r"hazlo\s+ya", r"inicia\s+el\s+flujo",
    r"crea\s+la\s+calculadora", r"genera\s+el\s+archivo"
]

_SYSTEM_TRIGGERS = [
    r"estado.*sistema", r"análisis.*sistema", r"como.*sistema",
    r"arquitectura", r"modelo", r"agentes", r"status", r"backend",
    r"qué.*modelo", r"cuántos.*documentos",
    r"diagnóstico", r"infraestructura", r"stack", r"versión",
    r"\bcpu\b", r"\bram\b", r"health", r"workers", r"cola.*tareas", r"queue",
    r"logs", r"métricas", r"metrics", r"latencia", r"performance", r"rendimiento",
    r"salud", r"hardware", r"memoria", r"auditoría", r"reporte.*técnico",
    r"cómo.*vas", r"qué.*haces", r"progreso", r"investigaciones", r"avances"
]

_RESEARCH_TRIGGERS = [
    r"investiga\b", r"busca\b.*(?:art[ií]culos|papers|información)",
    r"profundiza\b", r"estudia\b", r"explora\b.*(?:tema|tópico)",
    r"analiza\b", r"analisa\b", r"interpreta\b", r"describe\b.*imagen",
    r"quiero.*aprender.*sobre", r"necesito.*informaci[oó]n.*profunda",
    r"hazme.*investigaci[oó]n", r"despliega.*agentes",
    r"inicia.*investigaci[oó]n", r"qué.*relación.*hay", r"quien\s+es\b",
    r"qué.*vínculo\b", r"conecta\b.*con\b"
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
# v13.6.3: Disparadores de acción de investigación (Prioridad sobre SYSTEM)
_RESEARCH_ACTION_TRIGGERS = [
    r"busca\s+(nuevas\s+)?tecnolog[ií]as",
    r"investiga\s+(nuevas\s+)?tecnolog[ií]as",
    r"encuentra\s+mejoras",
    r"busca\s+la\s+manera\s+de\s+auto\s*mejorarte",
    r"c[oó]mo\s+mejorar\s+el\s+rendimiento"
]



_MEMORY_TRIGGERS = [
    r"recuerda\b", r"memoriza\b", r"aprende\b", r"guarda\s+esta\s+info", 
    r"anota\b", r"toma\s+nota", r"registra\b", r"gr[aá]bate\b", r"no\s+olvides"
]

_GWS_TRIGGERS = [
    r"agenda", r"calendario", r"calendar", r"correo", r"mail", r"gmail", 
    r"drive", r"archivo.*nube", r"reuni[oó]n", r"cita", r"triage", r"pendientes.*hoy"
]

_VISION_TRIGGERS = [
    r"mira\s+(?:la\s+)?pantalla", r"qu[eé]\s+ves", r"captura", r"haz\s+clic", 
    r"busca\s+en\s+pantalla", r"grounding", r"presiona", r"escribe"
]

# v12.1.6: Resumen de Aprendizaje (KNOWLEDGE)
_KNOWLEDGE_SUMMARY_TRIGGERS = [
    r"(?:qué|que)\s+(?:has\s+aprendido|conocimiento\s+tienes|sabes\s+hasta\s+ahora)",
    r"resume\s+(?:lo\s+que\s+has\s+aprendido|tu\s+aprendizaje|lo\s+aprendido)",
    r"(?:cu[eé]ntame|dime)\s+(?:lo\s+)?(?:que|qu[eé])\s+(?:has\s+aprendido|sabes)",
    r"haz\s+(?:un|una)\s+resumen\s+de\s+(?:lo\s+aprendido|tu\s+conocimiento)",
]

_STATUS_TRIGGERS = [
    r"qu[ée]\s+has\s+aprendido", r"resume\s+lo\s+que\s+has\s+aprendido",
    r"qu[ée]\s+sabes\s+de\s+esta\s+sesi[oó]n", r"qu[ée]\s+recuerdas",
    r"resumen\s+de\s+lo\s+aprendido", r"dime\s+qu[ée]\s+has\s+hecho"
]


async def classify_intent(query: str) -> str:
    """
    Clasifica la intención del usuario de forma determinística.
    Solo recurre al LLM cuando la query es ambigua (< 5% de los casos).
    """
    q_lower = query.strip().lower()
    # v11.9.17: Limpieza de prefijos neutrales para mejorar precisión
    q_clean = re.sub(r"^(oye\s+)?nova\s*[,:]?\s*", "", q_lower)
    q_clean = re.sub(r"^(escucha\s+)?nova\s*[,:]?\s*", "", q_clean)
    q_clean = re.sub(r'[¿?¡!.,;:\'"()]', '', q_clean).strip()

    # ── NIVEL 0: Memoria / Aprendizaje (MÁXIMA PRIORIDAD) ──
    # Evitamos que un saludo bloquee el guardado de información importante
    for pattern in _MEMORY_TRIGGERS:
        if re.search(pattern, q_clean, re.IGNORECASE):
            return "KNOWLEDGE"

    # ── NIVEL 0.4: Resumen de Aprendizaje (KNOWLEDGE) ──
    for pattern in _KNOWLEDGE_SUMMARY_TRIGGERS:
        if re.search(pattern, q_clean, re.IGNORECASE):
            return "KNOWLEDGE"

    # ── NIVEL 0.5: Status / Memoria de Sesión (Consultar Grafo/RAG) ──
    for pattern in _STATUS_TRIGGERS:
        if re.search(pattern, q_clean, re.IGNORECASE):
            return "KNOWLEDGE"

    # ── NIVEL 0.7: GWS & VISION (Alta prioridad para herramientas) ──
    for pattern in _GWS_TRIGGERS:
        if re.search(pattern, q_clean, re.IGNORECASE):
            return "GWS"
    
    for pattern in _VISION_TRIGGERS:
        if re.search(pattern, q_clean, re.IGNORECASE):
            return "VISION"

    # ── NIVEL 1: Fuzzy Greeting & Substring Match (O(n)) ──
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

    # v13.6.3: Priorizar acciones de investigación sobre SYSTEM
    if any(re.search(pat, q_clean, re.I) for pat in _RESEARCH_ACTION_TRIGGERS):
        return "RESEARCH"


    for pattern in _COMPUTATION_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "COMPUTATION"

    for pattern in _BOOK_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "BOOK_QUERY"

    # ── NIVEL 2.5: Proyecto Start ──
    # GUARD: Solo disparar PROJECT_BUILD si el mensaje es una instrucción directa,
    # NO una conversación casual que menciona palabras técnicas.
    # Mensajes largos narrativos (>12 palabras) sin verbos imperativos directos
    # son casi siempre conversación, no órdenes de construcción.
    word_count = len(q_clean.split())
    for pattern in _PROJECT_BUILD_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            # Verificar que no sea conversación disfrazada
            if word_count > 12:
                # Mensajes largos necesitan un verbo imperativo directo al inicio
                imperative_start = re.match(
                    r'^(crea|genera|construye|desarrolla|build|make|hazme|programa|empaqu[eé]ta)',
                    q_clean, re.IGNORECASE
                )
                if not imperative_start:
                    break  # No es una orden, salir del loop y seguir clasificando
            return "PROJECT_BUILD"

    # ── NIVEL 3: Regex matching para SYSTEM ──
    for pattern in _SYSTEM_TRIGGERS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "SYSTEM"


    # Queries muy cortas sin keywords de acción/research → probablemente chat (Hola Nova, etc)
    action_keywords = ["procede", "adelante", "hazlo", "crea", "genera", "investiga", "busca", "dime", "cuenta", "explica", "escucho", "hablame"]
    if word_count <= 4 and not any(c == '?' for c in query) and not any(kw in q_clean for kw in action_keywords):
        return "CONVERSATION"

    # Queries que son preguntas informativas → KNOWLEDGE
    if any(q_clean.startswith(p) for p in [
        "qué es", "que es", "qué son", "que son", "cómo funciona",
        "como funciona", "cuál es", "cual es", "por qué", "por que",
        "explica", "describe", "dime sobre", "háblame de", "hablame de",
        "qué sabes", "que sabes", "que era", "qué era", "cuál era", "cual era",
        "qué sugieres", "que sugieres", "qué recomiendas", "que recomiendas", "qué recursos"
    ]):
        return "KNOWLEDGE"

    # ── NIVEL 5: LLM fallback (solo queries genuinamente ambiguas) ──
    return await _llm_classify_fallback(query)


async def _llm_classify_fallback(query: str) -> str:
    """
    v13.7.1: Fallback al LLM con Razonamiento (CoT).
    Obliga al modelo a analizar la consulta antes de clasificarla.
    """
    try:
        from core.llm_gateway import llm_gateway  # type: ignore
        prompt = (
            "Actúa como el Clasificador de Intenciones de NOVA.\n"
            "Analiza la siguiente consulta y clasifícala en una categoría permitida.\n\n"
            "CATEGORÍAS:\n"
            "- KNOWLEDGE: Preguntas técnicas, dudas sobre conceptos o información fáctica.\n"
            "- RESEARCH: Peticiones que requieren búsqueda externa, navegación o exploración profunda.\n"
            "- CONVERSATION: Charlas casuales, saludos, bromas o feedback personal.\n"
            "- SYSTEM: Consultas sobre el estado de NOVA (CPU, RAM, logs, versiones).\n"
            "- COMPUTATION: Cálculos matemáticos o generación de scripts simples.\n"
            "- BOOK_QUERY: Dudas específicas sobre textos o autores.\n\n"
            f"Consulta del usuario: \"{query}\"\n\n"
            "Responde en el siguiente formato:\n"
            "RAZONAMIENTO: <breve análisis de 1 frase>\n"
            "INTENCIÓN: <CATEGORÍA_EN_MAYÚSCULAS>"
        )
        response = await llm_gateway.chat(
            [{"role": "user", "content": prompt}],
            lane="realtime",
            temperature=0.0,
            priority=0
        )
        
        # Extraer la intención usando regex para mayor seguridad
        intent_match = re.search(r"INTENCIN:\s*(KNOWLEDGE|RESEARCH|CONVERSATION|COMPUTATION|BOOK_QUERY|SYSTEM)", response.upper())
        if intent_match:
            return intent_match.group(1)
            
    except Exception as e:
        print(f"[IntentClassifier] LLM fallback error: {e}")

    return "KNOWLEDGE"  # Default seguro
