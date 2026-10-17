"""A9 · Consenso Ciudadano — índice de credibilidad por fuentes independientes.

Idea (poco vista en la operación de agua en Panamá): un mismo corte puede
producir 50 mensajes, pero no todos son "50 fuentes". Este agente combina:

  - fuentes independientes (hashes distintos),
  - evidencia multimedia (fotos, audios, vídeos),
  - variedad del relato (textos distintos = personas distintas; textos idénticos
    = posible campaña o reenvío),

y produce un ÍNDICE DE CONSENSO (0-1). Sirve para priorizar mejor y para avisar
al operador cuándo algo huele a campaña coordinada.

Complementa la línea base que se equivoca al contar "quejas".
"""
from __future__ import annotations

import re
import time

from config import CONSENSUS_MIN_SOURCES
from services.traces import log_step

AGENT = "A9_Consenso"


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-záéíóúñ0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _level(index: float) -> str:
    if index >= 0.7:
        return "alto"
    if index >= 0.4:
        return "medio"
    return "bajo"


def consensus_for(sector_id: str, reports: list[dict]) -> dict:
    rs = [r for r in reports if r.get("sector_id") == sector_id and r.get("status") != "rechazado"]
    if not rs:
        return {"sector_id": sector_id, "sources": 0, "with_media": 0, "variety": 0.0,
                "index": 0.0, "level": "bajo", "campaign_suspected": False}

    sources = {r.get("source_hash") for r in rs if r.get("source_hash")}
    with_media = sum(1 for r in rs if (r.get("meta") or {}).get("media"))
    texts = [_norm(r.get("raw_text", "")) for r in rs]
    texts = [t for t in texts if t]
    variety = (len(set(texts)) / len(texts)) if texts else 0.0

    src_term = min(1.0, len(sources) / max(1, CONSENSUS_MIN_SOURCES))
    media_term = min(1.0, with_media / 2.0)
    index = round(0.45 * src_term + 0.30 * media_term + 0.25 * variety, 3)

    campaign = len(sources) >= 4 and variety < 0.3 and with_media == 0
    if campaign:
        index = round(index * 0.5, 3)

    return {
        "sector_id": sector_id,
        "sources": len(sources),
        "reports": len(rs),
        "with_media": with_media,
        "variety": round(variety, 3),
        "index": index,
        "level": _level(index),
        "campaign_suspected": campaign,
    }


def index_report(report, existing: list[dict], run_id: str) -> dict:
    """Calcula el consenso del sector del reporte (incluyéndolo) y lo guarda en meta."""
    started = time.perf_counter()
    rows = list(existing)
    if not any(r.get("id") == report.id for r in rows):
        rows.append({
            "id": report.id, "sector_id": report.sector_id, "source_hash": report.source_hash,
            "raw_text": report.raw_text, "status": report.status, "meta": report.meta,
        })
    result = consensus_for(report.sector_id, rows) if report.sector_id else {
        "sector_id": None, "sources": 0, "index": 0.0, "level": "sin_sector",
        "with_media": 0, "variety": 0.0, "campaign_suspected": False,
    }
    report.meta["consensus"] = result
    log_step(run_id, AGENT, "consenso", {"sector_id": report.sector_id},
             {"index": result["index"], "level": result["level"],
              "sources": result.get("sources"), "campaign": result.get("campaign_suspected")},
             tools=["fuentes_independientes", "evidencia_multimedia"],
             latency_ms=(time.perf_counter() - started) * 1000, decision=f"consenso {result['level']}")
    return result
