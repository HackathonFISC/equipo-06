"""A8 · Supervisión humana — el único punto que puede aprobar, editar o rechazar.

- Ningún plan se manda a los camiones sin una decisión humana registrada.
- Toda edición se revalida con código determinista (capacidad, mínimo Sphere,
  espera de instituciones críticas). Si viola algo, se exige motivo explícito.
- Todo queda atribuido (operador, hora, motivo) en el registro encadenado.
"""
from __future__ import annotations

from services import catalog, storage
from services.metrics import SPHERE_MIN_LITERS_PER_PERSON
from services.traces import log_step
from schemas import Decision

AGENT = "A8_Supervision"


def evaluate_edit(changes: list[dict]) -> dict:
    """Valida una modificación propuesta por el humano."""
    tankers = {t.id: t for t in catalog.tankers()}
    sectors = catalog.sectors_by_id()
    violations: list[str] = []

    per_tanker: dict[str, int] = {}
    for c in changes:
        per_tanker[c.get("tanker_id", "")] = per_tanker.get(c.get("tanker_id", ""), 0) + int(c.get("liters", 0))

    for tid, total in per_tanker.items():
        t = tankers.get(tid)
        if t and total > t.capacity_liters:
            violations.append(f"{tid} excede su capacidad ({total:,} > {t.capacity_liters:,} L).")

    for c in changes:
        sector = sectors.get(c.get("sector_id", ""))
        if sector and sector.essential_services:
            liters = int(c.get("liters", 0))
            if liters < sector.population * SPHERE_MIN_LITERS_PER_PERSON:
                violations.append(
                    f"{sector.name} tiene servicio crítico ({', '.join(sector.essential_services)}) y "
                    f"recibiría {liters:,} L, por debajo del mínimo Sphere de "
                    f"{sector.population * SPHERE_MIN_LITERS_PER_PERSON:,.0f} L.")

    return {"ok": not violations, "violations": violations}


def decide(decision: Decision, run_id: str = "run_ad_hoc") -> dict:
    if decision.action == "editar":
        check = evaluate_edit([c.model_dump() for c in decision.changes])
        if not check["ok"] and not decision.reason.strip():
            return {"ok": False, "error": "La edición viola restricciones; se requiere un motivo explícito.",
                    "violations": check["violations"]}
        if not check["ok"]:
            storage.audit(decision.operator, "edicion_con_excepcion", {"violations": check["violations"],
                                                                       "reason": decision.reason})

    status_by_action = {"aprobar": "aprobado", "editar": "editado", "rechazar": "rechazado"}
    if decision.action not in status_by_action:
        return {"ok": False, "error": "Acción no válida (aprobar | editar | rechazar)."}

    storage.set_plan_status(decision.plan_id, status_by_action[decision.action])
    storage.insert_decision(decision.model_dump())
    storage.audit(decision.operator, f"decision_{decision.action}",
                  {"plan_id": decision.plan_id, "reason": decision.reason})

    log_step(run_id, AGENT, "decision", {"plan_id": decision.plan_id, "action": decision.action},
             {"status": status_by_action[decision.action]}, tools=["sqlite_registro_encadenado"],
             decision=f"{decision.operator}: {decision.action}")
    return {"ok": True, "status": status_by_action[decision.action]}
