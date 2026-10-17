"""A2 · Geolocalización y deduplicación.

- Relaciona la ubicación textual con el catálogo local de sectores (búsqueda difusa).
- Si el mejor candidato no supera al segundo por un margen claro, devuelve varios
  candidatos y marca el reporte como "pendiente_confirmacion" (no adivina).
- Agrupa reportes del mismo incidente (mismo sector, tiempo cercano, texto parecido)
  para que cien mensajes idénticos cuenten como UNA fuente.
"""
from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

from services import catalog, memory
from schemas import Report
from services.traces import log_step

AGENT = "A2_Geo_Dedup"

FUZZY_ACCEPT = 0.62        # aceptar el mejor candidato
AMBIGUITY_MARGIN = 0.12    # si el segundo está muy cerca, pedir confirmación
DEDUP_TEXT_RATIO = 0.80    # similitud de texto para considerar duplicado
DEDUP_WINDOW_MIN = 180     # ventana temporal (minutos)


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-záéíóúñ0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extra_sources(sector_id: str) -> list[str]:
    """Referencias locales (gacetero) + alias aprendidos de correcciones humanas."""
    sources: list[str] = []
    for lm in catalog.landmarks():
        if lm.get("sector_id") == sector_id:
            sources.append(lm.get("name", ""))
            sources.extend(lm.get("aliases", []))
    sources.extend(sorted(memory.aliases_for(sector_id)))
    return [s for s in sources if s]


def resolve_location(report: Report, run_id: str) -> Report:
    text = _normalize(report.sector_hint or report.raw_text)
    scores = []
    for sector in catalog.sectors():
        best = 0.0
        for candidate in [sector.name, sector.corregimiento, *sector.aliases, *_extra_sources(sector.id)]:
            c = _normalize(candidate)
            if not c:
                continue
            if c in text:
                best = max(best, 1.0)
            else:
                best = max(best, SequenceMatcher(None, c, text).ratio(),
                           SequenceMatcher(None, c, text).find_longest_match(0, len(c), 0, len(text)).size / max(len(c), 1))
        scores.append((sector.id, sector.name, round(best, 3)))
    scores.sort(key=lambda x: x[2], reverse=True)
    top = scores[0] if scores else None
    second = scores[1] if len(scores) > 1 else ("", "", 0.0)

    candidates = [s for s in scores[:3] if s[2] > 0.2]
    if top and top[2] >= FUZZY_ACCEPT and (top[2] - second[2]) >= AMBIGUITY_MARGIN:
        report.sector_id = top[0]
        report.status = "recibido" if report.status != "rechazado" else report.status
        decision = f"asignado a {top[1]}"
    elif candidates:
        report.status = "pendiente_confirmacion" if report.status != "rechazado" else report.status
        decision = "ambiguo: requiere confirmación"
    else:
        report.status = "pendiente_confirmacion" if report.status != "rechazado" else report.status
        decision = "sin coincidencia en catálogo"

    # Deja los candidatos en meta (A2b los usa para preguntar de vuelta).
    report.meta["geo_candidates"] = [
        {"sector_id": c[0], "sector_name": c[1], "score": c[2]} for c in candidates
    ]

    log_step(run_id, AGENT, "geolocalizacion", {"hint": report.sector_hint},
             {"candidatos": candidates, "sector_id": report.sector_id},
             tools=["fuzzy_match", "gacetero_local", "memoria_alias"], decision=decision)
    return report


def _minutes_between(a: str, b: str) -> float:
    from datetime import datetime
    try:
        t1 = datetime.fromisoformat(a)
        t2 = datetime.fromisoformat(b)
        return abs((t1 - t2).total_seconds()) / 60.0
    except Exception:
        return 9999.0


def find_duplicate(report: Report, existing: list[dict]) -> str | None:
    """Devuelve el id del reporte del que este es duplicado, si lo hay."""
    if report.status == "rechazado":
        return None
    for other in existing:
        if other["id"] == report.id or other.get("status") == "rechazado":
            continue
        if report.sector_id and other.get("sector_id") and report.sector_id != other["sector_id"]:
            continue
        if _minutes_between(report.created_at, other["created_at"]) > DEDUP_WINDOW_MIN:
            continue
        ratio = SequenceMatcher(None, _normalize(report.raw_text), _normalize(other["raw_text"])).ratio()
        same_sector_same_type = (
            report.sector_id is not None
            and other.get("sector_id") == report.sector_id
            and other.get("incident_type") == report.incident_type.value
        )
        if ratio >= DEDUP_TEXT_RATIO or (same_sector_same_type and ratio >= 0.5):
            return other["id"]
    return None


def deduplicate(report: Report, existing: list[dict], run_id: str) -> Report:
    dup_of = find_duplicate(report, existing)
    if dup_of:
        report.dup_of = dup_of
        report.status = "duplicado"
    else:
        # Misma fuente que insiste no cuenta como fuente nueva (se maneja al contar fuentes).
        pass
    log_step(run_id, AGENT, "deduplicacion", {"report_id": report.id},
             {"dup_of": dup_of}, tools=["text_similarity"],
             decision="duplicado" if dup_of else "nuevo incidente")
    return report
