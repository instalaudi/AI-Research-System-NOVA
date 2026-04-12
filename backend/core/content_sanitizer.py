import re

def sanitize_for_prompt(text: str, max_length: int = 1500) -> str:
    """Limpia texto web antes de inyectarlo en prompts del LLM para evitar prompt injection."""
    if not text:
        return ""
    # Eliminar caracteres de control
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Eliminar patrones de inyección de prompt
    injection_patterns = [
        r'ignore\s+(previous|above|all)\s+instructions',
        r'you\s+are\s+now\s+a',
        r'system\s*:\s*',
        r'<\s*/?(?:script|style|iframe)',
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, '[FILTERED]', text, flags=re.IGNORECASE)
    # Truncar
    return text[:max_length]
