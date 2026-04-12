STOP_WORDS_ES = {"para", "como", "sobre", "entre", "donde", "cuando", "quien",
                  "esta", "este", "pero", "con", "por", "que", "los", "las",
                  "del", "una", "uno", "más", "sin", "todo", "qué", "de", "la", "el", "en", "es", "al"}

PRESERVE_SHORT = {"IA", "UI", "AI", "ML", "NLP", "DNA", "API", "GPU", "CPU", "RAM"}

def extract_keywords(text: str, min_length: int = 3) -> list[str]:
    """Extrae keywords significativas de texto, unificado para todo el sistema."""
    words = text.split()
    return [
        w.lower() for w in words
        if (len(w) >= min_length or w.upper() in PRESERVE_SHORT)
        and w.lower() not in STOP_WORDS_ES
    ]

def escape_like(text: str) -> str:
    """Escapa caracteres especiales de LIKE/ILIKE de SQL."""
    return text.replace('%', '\\%').replace('_', '\\_')
