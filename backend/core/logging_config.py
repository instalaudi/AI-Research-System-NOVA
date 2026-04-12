import logging
import json
import time
import uuid
import re
from contextvars import ContextVar
from typing import Any, Dict

# Context variable to store request_id across the execution flow
request_id_var: ContextVar[str] = ContextVar("request_id", default="system")

# BUG #1 FIX: Redactar tokens sensibles en logs antes de escribirlos
_SENSITIVE_PATTERNS = [
    # Telegram bot token standalone: bot<digits>:<alphanumeric>
    (re.compile(r"bot\d+:[A-Za-z0-9_\-]+"), "bot[REDACTED]"),
    # Telegram bot token in URL: api.telegram.org/bot<digits>:<token>/method
    (re.compile(r"(api\.telegram\.org/)bot\d+:[A-Za-z0-9_\-]+"), r"\1bot[REDACTED]"),
]

class SensitiveDataFilter(logging.Filter):
    """
    Filtra y redacta información sensible (tokens, credenciales)
    de los mensajes de log antes de que sean escritos.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact_val(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._redact_val(a) for a in record.args)
        return True

    def _redact_val(self, val: Any) -> Any:
        """
        Redacta solo si es necesario, preservando el tipo original si es seguro.
        Esto evita errores de 'TypeError: %d format: a real number is required, not str'.
        """
        if val is None:
            return None
        # Convertimos a string solo para chequear patrones
        try:
            s_val = str(val)
            redacted = self._redact(s_val)
            # Solo devolvemos la versión string si hubo cambios (redacción)
            # o si el valor original ya era un string.
            if redacted != s_val:
                return redacted
            return val
        except Exception:
            return val

    @staticmethod
    def _redact(text: str) -> str:
        for pattern, replacement in _SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text


class JsonFormatter(logging.Formatter):
    """
    Custom JSON Formatter for structured logging.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }

        # Add extra fields if provided via 'extra' parameter
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)

def setup_logging(level: int = logging.INFO):
    """
    Sets up the global logging configuration.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SensitiveDataFilter())  # BUG #1 FIX: Redactar tokens en todos los logs

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplication
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    root_logger.addHandler(handler)

    # Silence some noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# Helper to log with extra fields easily
def get_logger(name: str):
    return logging.getLogger(name)

class NovaLoggerAdapter(logging.LoggerAdapter):
    """
    Adapter to facilitate logging with structured 'extra' fields.
    """
    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        if "extra" in kwargs:
            kwargs["extra_fields"] = kwargs.pop("extra")
        return msg, kwargs
