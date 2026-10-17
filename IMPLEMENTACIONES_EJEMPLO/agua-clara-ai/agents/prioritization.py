"""A4 · Priorización — puntaje auditable, con pesos visibles.

score = 0.40 * horas_norm + 0.30 * población_norm + 0.30 * vulnerabilidad
        (ajustado por la probabilidad de corte del A3 y con bono por institución crítica)

Reglas firmes:
- La cantidad de quejas NUNCA aumenta la prioridad (solo la evidencia, corregida
  por visibilidad, entra en p_cut).
- Mismos datos -> mismo orden (determinista, desempate por sector_id).
- Cada razón se enumera para que el coordinador vea POR QUÉ.
"""
from __future__ import annotations

from schemas import Sector, SectorPriority
from services.traces import log_step

AGENT = "A4_Prioridad"

W_HOURS = 0.40
W_POPULATION = 0.30
W_VULNERABILITY = 0.30
CRITICAL_BONUS = 0.25
P_CUT_THRESHOLD = 0.35   # por debajo de esto, no se prioriza (a menos que tenga institución crítica)


def _norm(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def rank(sectors: list[Sector], estimates: dict[str, dict], run_id: str) -> list[SectorPriority]:
    hours = [s.hours_without_water for s in sectors] or [0]
    pops = [s.population for s in sectors] or [1]
    h_lo, h_hi = min(hours), max(hours)
    p_lo, p_hi = min(pops), max(pops)

    out: list[SectorPriority] = []
    for s in sectors:
        est = estimates[s.id]
        p_cut = est["p_cut"]
        hours_n = _norm(s.hours_without_water, h_lo, h_hi)
        pop_n = _norm(s.population, p_lo, p_hi)

        base = W_HOURS * hours_n + W_POPULATION * pop_n + W_VULNERABILITY * s.vulnerability
        critical = bool(s.essential_services)
        score = base * (0.5 + 0.5 * p_cut) + (CRITICAL_BONUS if critical else 0.0)

        reasons = [
            f"Horas sin agua: {s.hours_without_water:g} h (factor {W_HOURS:.0%}, normalizado {hours_n:.2f}).",
            f"Población: {s.population:,} (factor {W_POPULATION:.0%}, normalizado {pop_n:.2f}).",
            f"Vulnerabilidad declarada: {s.vulnerability:.2f} (factor {W_VULNERABILITY:.0%}).",
            f"Probabilidad de corte estimada: {p_cut:.0%}.",
        ]
        if critical:
            reasons.append(f"Institución/servicio crítico: {', '.join(s.essential_services)} (bono {CRITICAL_BONUS:.2f}).")
        reasons.append(est["visibility_note"])

        out.append(SectorPriority(
            sector_id=s.id, name=s.name, p_cut=p_cut,
            distinct_sources=est["distinct_sources"],
            hours_without_water=s.hours_without_water,
            population_affected=int(s.population * p_cut),
            vulnerability=s.vulnerability, essential_services=s.essential_services,
            score=round(score, 4), rank=0, reasons=reasons,
            visibility_note=est["visibility_note"],
        ))

    out.sort(key=lambda x: (-x.score, x.sector_id))
    for i, item in enumerate(out, start=1):
        item.rank = i

    log_step(run_id, AGENT, "ranking", {"sectores": len(sectors)},
             [{"sid": x.sector_id, "score": x.score} for x in out[:5]],
             tools=["pesos_configurables"], decision="orden determinista")
    return out


def eligible(priorities: list[SectorPriority]) -> list[SectorPriority]:
    return [p for p in priorities if p.p_cut >= P_CUT_THRESHOLD or p.essential_services]
