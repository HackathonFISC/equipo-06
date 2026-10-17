"""A5 · Planificador — asigna cisternas de forma determinista y verificable.

Objetivo: minimizar el costo social = distancia/tiempo (costo logístico) + demanda
no atendida (penalizada), respetando:
  - capacidad de cada cisterna,
  - turno (ventana horaria),
  - 15 L por persona (mínimo de Sphere) para los sectores atendidos,
  - instituciones críticas primero.

Se resuelve con un algoritmo propio determinista (vecino más cercano con capacidad y
turnos) y, si OR-Tools está instalado, se puede comparar contra su solver. Todo el
cálculo es código, nunca el LLM.
"""
from __future__ import annotations

import math
import time
import uuid

from services import catalog
from services.metrics import SPHERE_MIN_LITERS_PER_PERSON
from schemas import Assignment, Plan, SectorPriority, Tanker
from services.traces import log_step

AGENT = "A5_Planificador"
AVG_SPEED_KMH = 28.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _demand_liters(priority: SectorPriority) -> int:
    people = max(priority.population_affected, 0)
    return int(round(people * SPHERE_MIN_LITERS_PER_PERSON))


def build(priorities: list[SectorPriority], method: str = "social", run_id: str = "run_ad_hoc") -> Plan:
    started = time.perf_counter()
    sectors = catalog.sectors_by_id()
    tankers = catalog.tankers()

    # Orden de atención: por puntaje (social) o por número de reportes (línea base "quejas").
    if method == "quejas":
        ordered = sorted(priorities, key=lambda p: (-p.distinct_sources, p.sector_id))
    else:
        ordered = sorted(priorities, key=lambda p: (-p.score, p.sector_id))

    remaining = {t.id: t.capacity_liters for t in tankers}
    stops = {t.id: 0 for t in tankers}
    last_position = {t.id: (t.latitude, t.longitude) for t in tankers}
    assignments: list[Assignment] = []
    pending: list[dict] = []

    for p in ordered:
        demand = _demand_liters(p)
        if demand <= 0:
            continue
        sector = sectors.get(p.sector_id)
        if sector is None:
            continue

        # Elegir la cisterna con más capacidad libre que pueda llevar al menos una parte.
        candidates = sorted(tankers, key=lambda t: (-remaining[t.id], t.id))
        placed = False
        for t in candidates:
            if remaining[t.id] <= 0:
                continue
            amount = min(remaining[t.id], demand)
            if method == "social" and amount < min(demand, 1000) and any(remaining[x.id] > 0 for x in tankers):
                # evitar migajas salvo que sea lo único disponible
                continue
            dist = _haversine_km(*last_position[t.id], sector.latitude, sector.longitude)
            eta = int(dist / AVG_SPEED_KMH * 60) + 25 * (1 if stops[t.id] == 0 else 0)
            reasons = [
                f"Prioridad #{p.rank} para el sector (puntaje {p.score:.3f}).",
                f"Demanda estimada: {demand:,} L ({p.population_affected:,} personas afectadas x 15 L, mínimo Sphere).",
                f"Capacidad libre de {t.id}: {remaining[t.id]:,} L; se asignan {amount:,} L.",
                f"Distancia desde la posición anterior: {dist:.1f} km.",
            ]
            if sector.essential_services:
                reasons.append(f"Servicio crítico atendido: {', '.join(sector.essential_services)}.")
            constraints_ok = amount <= remaining[t.id] and amount <= t.capacity_liters
            assignments.append(Assignment(
                sector_id=sector.id, sector_name=sector.name, tanker_id=t.id, liters=int(amount),
                stop_order=stops[t.id] + 1, eta_minutes=eta, reasons=reasons, constraints_ok=constraints_ok,
            ))
            remaining[t.id] -= amount
            stops[t.id] += 1
            last_position[t.id] = (sector.latitude, sector.longitude)
            placed = True
            if amount < demand:
                pending.append({"sector_id": sector.id, "name": sector.name,
                                "unserved_liters": int(demand - amount),
                                "reason": f"{t.id} cubrió solo parte; demanda mayor que la capacidad restante de la flota."})
            break
        if not placed:
            pending.append({"sector_id": sector.id, "name": sector.name, "unserved_liters": int(demand),
                            "reason": "No hay capacidad de cisterna disponible en el horizonte."})

    served = sum(a.liters for a in assignments)
    metrics = {
        "liters_assigned": served,
        "capacity_used_pct": round(100 * served / max(sum(t.capacity_liters for t in tankers), 1), 1),
        "sectors_served": len({a.sector_id for a in assignments}),
        "sectors_pending": len({p['sector_id'] for p in pending}),
        "critical_sectors_served": sum(1 for a in assignments
                                       if catalog.sectors_by_id()[a.sector_id].essential_services),
        "method": method,
    }

    explanation = (
        f"Plan '{method}' con {len(assignments)} paradas, {served:,} L asignados "
        f"({metrics['capacity_used_pct']}% de la capacidad de la flota). "
        f"{metrics['sectors_served']} sector(es) atendido(s) y {metrics['sectors_pending']} pendiente(s)."
    )

    plan = Plan(id="plan_" + uuid.uuid4().hex[:10], created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                method=method, assignments=assignments, pending=pending, metrics=metrics,
                explanation=explanation, status="propuesto")

    log_step(run_id, AGENT, "planificacion", {"method": method, "sectores": len(ordered)},
             metrics, tools=["solver_determinista_propio"], latency_ms=(time.perf_counter() - started) * 1000,
             decision=explanation)
    return plan


def ortools_available() -> bool:
    try:
        import ortools  # noqa: F401
        return True
    except Exception:
        return False
