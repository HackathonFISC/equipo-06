"""Guardrails y controles transversales.

- Detección de campañas coordinadas (ráfagas casi idénticas desde teléfonos nuevos).
- Detección de emergencias médicas para derivar al 911.
- Límite de reportes por fuente en una ventana.
"""
from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher

MEDICAL_PATTERNS = [
    r"desmay", r"herid", r"ambulanc", r"emergencia m[eé]dica", r"insulina", r"diabetes",
    r"dialisis", r"di[aá]lisis", r"falta de medicamento", r"beb[eé] enfermo", r"no respira",
]

CAMPAIGN_MIN_SOURCES = 4
CAMPAIGN_MIN_RATIO = 0.90
RATE_LIMIT_PER_SOURCE = 15


def is_medical_emergency(text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in MEDICAL_PATTERNS)


def rate_limited(source_hash: str | None, existing: list[dict]) -> bool:
    if not source_hash:
        return False
    count = sum(1 for r in existing if r.get("source_hash") == source_hash)
    return count >= RATE_LIMIT_PER_SOURCE


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-záéíóúñ0-9\s]", " ", (text or "").lower())).strip()


def detect_campaigns(reports: list[dict], min_sources: int = CAMPAIGN_MIN_SOURCES) -> list[dict]:
    """Agrupa reportes casi idénticos de fuentes distintas: posible campaña."""
    active = [r for r in reports if r.get("status") not in ("rechazado",) and r.get("sector_id")]
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in active:
        key = f"{r.get('sector_id')}|{r.get('incident_type')}"
        groups[key].append(r)

    flags = []
    for key, rows in groups.items():
        sources = {r.get("source_hash") or r["id"] for r in rows}
        if len(sources) < min_sources:
            continue
        base = _normalize(rows[0]["raw_text"])
        similar = sum(1 for r in rows if SequenceMatcher(None, base, _normalize(r["raw_text"])).ratio() >= CAMPAIGN_MIN_RATIO)
        if similar >= min_sources:
            flags.append({"group": key, "reports": len(rows), "sources": len(sources),
                          "note": "Ráfaga casi idéntica desde fuentes distintas: posible campaña coordinada."})
    return flags
