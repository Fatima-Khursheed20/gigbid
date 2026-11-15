"""PII masking for logs, traces and the audit log (E4)."""

from __future__ import annotations

import logging
import re
from typing import Any

PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)*\.[a-zA-Z]{2,}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("PHONE", re.compile(r"(?<![\w-])(?:\+\d[\d\s().-]{7,}\d|\(?\d{3}\)?[\s.]\d{3}[\s.-]\d{4})(?![\w-])")),
    ("TOKEN", re.compile(r"\b(gs-[\w-]{3,}|gsk_[\w]{10,}|gho_[\w]{10,}|ghp_[\w]{10,}|sk-[\w-]{10,}|lsv2_[\w]{10,})\b")),
]


def mask(text: str) -> str:
    if not text:
        return text
    out = text
    for label, pat in PATTERNS:
        out = pat.sub(f"[{label}]", out)
    return out


def mask_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k.lower() in {"password", "token", "api_key", "authorization", "access_token",
                                                   "refresh_token", "secret"} else mask_obj(v)) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [mask_obj(v) for v in obj]
    return obj


class PIIFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask(record.msg)
        if record.args:
            record.args = tuple(mask(a) if isinstance(a, str) else a for a in record.args)
        return True


def setup_logging(level: int = logging.INFO) -> None:
    from .tracing import TraceIdFilter

    handler = logging.StreamHandler()
    handler.addFilter(PIIFilter())
    handler.addFilter(TraceIdFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [trace=%(trace_id)s] %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
