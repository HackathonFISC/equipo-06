"""A3 · Estimador de estado — ¿qué probabilidad hay de que cada sector esté sin agua?

Idea central (y aporte diferenciador): cero reportes NO significa que no haya corte.
Combinamos:
- una probabilidad previa por sector (historial de cortes), y
- la evidencia de los reportes, pesada por la confiabilidad de cada fuente y
  CORREGIDA por la propensión a reportar del sector.

Así, un sector que casi nunca reporta (poca visibilidad) no queda invisible:
mantiene su previa y cada reporte suyo pesa relativamente más.
Todo es determinista y explicable; el LLM no participa.
"""
from __future__ import annotations

import math
from collections import defaultdict

from schemas import Sector
from services.traces import log_step

AGENT = "A3_Estimador"

SOURCE_BASE_WEIGHT = 1.0
PROPENSITY_FLOOR = 0.15   # evita dividir por cero en sectores casi silenciosos
K = 0.9                   # cuánto mueve la evidencia a la probabilidad


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def estimate(sectors: list[Sector], reports: list[dict], run_id: str) -> dict[str, dict]:
    """Devuelve {sector_id: {p_cut, distinct_sources, evidence, visibility_note}}."""
    by_sector: dict[str, list[dict]] = defaultdict(list)
    for r in reports:
        if r.get("status") in ("rechazado", "pendiente_confirmacion"):
            continue
        if r.get("sector_id"):
            by_sector[r["sector_id"]].append(r)

    result: dict[str, dict] = {}
    for sector in sectors:
        rows = by_sector.get(sector.id, [])
        # Deduplicar la EVIDENCIA por fuente: cien mensajes del mismo número
        # cuentan como una sola fuente, pero cien números distintos suman.
        by_source: dict[str, float] = {}
        for r in rows:
            key = r.get("source_hash") or r["id"]
            by_source[key] = max(by_source.get(key, 0.0), float(r.get("confidence") or 0.5))
        distinct_sources = len(by_source)

        propensity = max(sector.report_propensity, PROPENSITY_FLOOR)
        evidence = sum(weight / propensity for weight in by_source.values())
        evidence_strength = K * math.log(1 + evidence)

        if distinct_sources == 0:
            p_cut = sector.prior_cut
            note = (f"Sin reportes, pero la previa del sector es {sector.prior_cut:.0%}: "
                    f"no lo tratamos como 'sin problema'.")
        else:
            p_cut = _sigmoid(_logit(sector.prior_cut) + evidence_strength)
            if sector.report_propensity < 0.35:
                note = (f"Sector de baja visibilidad (propensión {sector.report_propensity:.0%}); "
                        f"se corrigió para que pocos reportes no lo oculten.")
            else:
                note = f"{distinct_sources} fuente(s) distinta(s) respaldan el corte."

        result[sector.id] = {
            "p_cut": round(p_cut, 3),
            "distinct_sources": distinct_sources,
            "evidence": round(evidence, 3),
            "visibility_note": note,
        }

    log_step(run_id, AGENT, "estimacion", {"sectores": len(sectors), "reportes": len(reports)},
             {sid: v["p_cut"] for sid, v in result.items()}, tools=["modelo_bayesiano_determinista"],
             decision="posterior por sector")
    return result


def sampling_targets(sectors: list[Sector], estimates: dict[str, dict], top_n: int = 2) -> list[dict]:
    """Muestreo activo: preguntar por los sectores con más incertidumbre."""
    ranked = []
    for s in sectors:
        est = estimates.get(s.id, {})
        if est.get("distinct_sources", 0) > 0:
            continue
        uncertainty = 1 - abs(est.get("p_cut", 0.0) - 0.5) * 2  # máxima cerca de 0.5
        ranked.append({"sector_id": s.id, "name": s.name,
                       "p_cut": est.get("p_cut", 0.0), "uncertainty": round(uncertainty, 3)})
    ranked.sort(key=lambda x: x["uncertainty"], reverse=True)
    return ranked[:top_n]
