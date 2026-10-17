"""A1b · Normalizador de escritura y jerga panameña.

Muchos reportes llegan con errores de tipeo, abreviaturas y jerga local. Este
agente los normaliza ANTES de extraer campos, y deja constancia transparente de
cada cambio (auditable). Aprende de las correcciones humanas vía services.memory.

- Corrige palabras/frases conocidas (memoria + corpus).
- Detecta jerga ("no hay ni gota" = sin_agua) y la expone como pista.
- Mide la "calidad" del texto: si es muy ruidoso, lo marca para pedir aclaración.
"""
from __future__ import annotations

import re
import time

from services import memory
from services.traces import log_step

AGENT = "A1b_Normalizador"

# Vocabulario de referencia (para estimar ruido). Incluye términos del dominio,
# conectores y los nombres de los sectores.
COMMON_WORDS = {
    "sin", "agua", "no", "hay", "tenemos", "llega", "horas", "hora", "dia", "dias",
    "personas", "familia", "familias", "somos", "para", "por", "en", "el", "la",
    "los", "las", "un", "una", "unos", "unas", "y", "o", "que", "de", "del",
    "con", "cerca", "donde", "estamos", "llevamos", "desde", "hasta", "barriada",
    "barrio", "calle", "casa", "casa", "escuela", "hospital", "clinica", "centro",
    "salud", "fuga", "tuberia", "presion", "poca", "poquita", "gota", "tanque",
    "camion", "cisterna", "ayuda", "urgente", "favor", "por", "vista", "alegre",
    "nuevo", "emperador", "cerro", "silvestre", "burunga", "veracruz", "santa",
    "clara", "colon", "guadalupe", "arado", "puerto", "caimito", "arraijan",
    "chorrera",
}


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-záéíóúñ0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _apply_corrections(text: str) -> tuple[str, list[dict]]:
    corr = memory.corrections()
    out = text
    applied: list[dict] = []
    # Frases largas primero para no romper expresiones compuestas.
    for wrong, right in sorted(corr.items(), key=lambda kv: -len(kv[0])):
        if not wrong:
            continue
        pattern = r"(?<![a-záéíóúñ0-9])" + re.escape(wrong) + r"(?![a-záéíóúñ0-9])"
        new = re.sub(pattern, right, out, flags=re.IGNORECASE)
        if new != out:
            applied.append({"from": wrong, "to": right})
            out = new
    out = re.sub(r"\s+", " ", out).strip()
    return out, applied


def _detect_slang(text: str) -> list[dict]:
    low = _norm(text)
    hits = []
    for term, intent in memory.slang().items():
        if term and term in low:
            hits.append({"term": term, "intent": intent})
    return hits


def _quality(text: str) -> tuple[float, list[str]]:
    """0..1 (1 = texto claro). Lista de tokens desconocidos sospechosos."""
    tokens = [t for t in _norm(text).split() if t]
    if not tokens:
        return 0.0, []
    unknown = [t for t in tokens if t not in COMMON_WORDS and len(t) > 2
               and not any(ch.isdigit() for ch in t)]
    unknown = [t for t in unknown if t not in memory.corrections()
               and not any(t.startswith(c) for c in ())]
    ratio = len(unknown) / len(tokens)
    return round(max(0.0, 1.0 - ratio), 3), unknown[:8]


def normalize(text: str, run_id: str | None = None) -> dict:
    run_id = run_id or "run_ad_hoc"
    started = time.perf_counter()
    corrected, applied = _apply_corrections(text or "")
    slang_hits = _detect_slang(corrected)
    quality, unknown = _quality(corrected)
    suspicious = quality < 0.45

    log_step(run_id, AGENT, "normalizar", {"len": len(text or "")},
             {"correcciones": len(applied), "jerga": [s["intent"] for s in slang_hits],
              "calidad": quality, "sospechoso": suspicious},
             tools=["memoria.correcciones", "memoria.jerga"], latency_ms=(time.perf_counter() - started) * 1000,
             decision="texto normalizado")
    return {
        "text": corrected,
        "corrections": applied,
        "slang": slang_hits,
        "quality": quality,
        "unknown_tokens": unknown,
        "suspicious": suspicious,
    }
