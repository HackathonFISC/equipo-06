"""Runner de evals: ejecuta los 35 casos y devuelve métricas por agente.

Se puede ejecutar como script (`python -m evals.run_evals`) o desde la API.
Usa una base de datos temporal y una memoria temporal para no ensuciar la demo
ni arrastrar estado entre corridas (la suite es hermética e idempotente).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from evals.cases import get_cases


def _use_temp_db():
    """Redirige almacenamiento y memoria a rutas temporales; devuelve el estado previo.

    Importante: devuelve el estado original para poder RESTAURARLO, de lo contrario
    el proceso del servidor quedaría apuntando a la base/memoria temporal vacías
    tras ejecutar los evals desde la interfaz.
    """
    from services import memory, storage
    prev = (storage.DATA_DIR, storage.DB_PATH, memory.MEMORY_PATH)
    tmpdir = Path(tempfile.mkdtemp(prefix="agua_evals_"))
    storage.DATA_DIR = tmpdir
    storage.DB_PATH = tmpdir / "evals.sqlite"
    storage.init_db(reset=True)
    # Memoria hermética: el aprendizaje del eval no contamina data/memory.jsonl.
    memory.MEMORY_PATH = tmpdir / "memory.jsonl"
    memory.reset()
    return prev


def _restore_db(prev) -> None:
    from services import memory, storage
    storage.DATA_DIR, storage.DB_PATH, mem_path = prev
    storage.init_db()
    memory.MEMORY_PATH = mem_path
    memory.reload()


def _aggregate_metrics(results: list[dict]) -> dict:
    """Métricas exigidas por el reto: equidad (Gini), cobertura y seguridad."""
    from agents import estimator, orchestrator
    from services import catalog, storage

    comp = orchestrator.compare_methods()
    social = comp["social"]["metrics"]
    base = comp["baseline_quejas"]["metrics"]
    sectors = catalog.sectors()
    critical = {s.id for s in sectors if s.essential_services}
    estimates = estimator.estimate(sectors, storage.list_reports(limit=500), "run_eval_metrics")
    sampling = estimator.sampling_targets(sectors, estimates)
    fp_avoided = sum(1 for r in results if r["id"] in ("EV13", "EV14") and r["passed"])
    from services import memory
    mem = memory.stats()
    return {
        "gini_social": social.get("gini_hours_without_water"),
        "gini_baseline_quejas": base.get("gini_hours_without_water"),
        "critical_served_social": social.get("critical_sectors_served"),
        "critical_served_baseline": base.get("critical_sectors_served"),
        "critical_total": len(critical),
        "coverage_social_pct": social.get("capacity_used_pct"),
        "coverage_baseline_pct": base.get("capacity_used_pct"),
        "deprivation_social": social.get("deprivation_total"),
        "deprivation_baseline": base.get("deprivation_total"),
        "false_positives_avoided": fp_avoided,
        "silent_sectors_sampled": len(sampling),
        "eval_cases_total": len(results),
        "memory_corrections": mem.get("correcciones"),
        "memory_aliases": mem.get("alias_totales"),
        "memory_slang": mem.get("jerga"),
    }


def run_all() -> dict:
    prev = _use_temp_db()
    from services import catalog, memory
    catalog.reload()
    memory.ensure_trained()

    try:
        results = []
        by_agent: dict[str, dict] = {}
        passed_total = 0
        for case in get_cases():
            try:
                passed, detail = case["fn"]()
            except Exception as exc:  # un caso que revienta cuenta como fallo, con su traza
                passed, detail = False, f"excepción: {exc}"
            passed = bool(passed)
            passed_total += int(passed)
            results.append({"id": case["id"], "case": case["case"], "agent": case["agent"],
                            "passed": passed, "detail": detail})
            bucket = by_agent.setdefault(case["agent"], {"passed": 0, "total": 0})
            bucket["total"] += 1
            bucket["passed"] += int(passed)

        total = len(results)
        try:
            metrics = _aggregate_metrics(results)
        except Exception as exc:  # las métricas no deben tumbar la suite
            metrics = {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        # Restaura la base real del servidor (los evals usan una temporal).
        _restore_db(prev)

    return {
        "total": total,
        "passed": passed_total,
        "pass_rate": round(passed_total / total, 3) if total else 0.0,
        "by_agent": by_agent,
        "results": results,
        "metrics": metrics,
    }


if __name__ == "__main__":
    report = run_all()
    print(f"\nEvals: {report['passed']}/{report['total']} aprobados "
          f"({report['pass_rate']*100:.0f}%)\n")
    print(f"{'ID':<6} {'Resultado':<10} {'Caso':<55} Detalle")
    print("-" * 120)
    for r in report["results"]:
        mark = "OK" if r["passed"] else "FALLA"
        print(f"{r['id']:<6} {mark:<10} {r['case'][:53]:<55} {r['detail']}")
    m = report.get("metrics", {})
    print("\nMétricas agregadas (equidad · cobertura · seguridad):")
    print(f"  Gini horas sin agua        social={m.get('gini_social')}  base(quejas)={m.get('gini_baseline_quejas')}")
    print(f"  Sectores críticos atendidos social={m.get('critical_served_social')}/{m.get('critical_total')}  base={m.get('critical_served_baseline')}/{m.get('critical_total')}")
    print(f"  Cobertura de capacidad (%)  social={m.get('coverage_social_pct')}  base={m.get('coverage_baseline_pct')}")
    print(f"  Deprivación total           social={m.get('deprivation_social')}  base={m.get('deprivation_baseline')}")
    print(f"  Falsos positivos evitados   {m.get('false_positives_avoided')}")
    print(f"  Sectores silenciosos muestreados {m.get('silent_sectors_sampled')}")
    print(f"  Casos de evaluación         {m.get('eval_cases_total')}")
    print(f"  Memoria aprendida           correcciones={m.get('memory_corrections')} "
          f"alias={m.get('memory_aliases')} jerga={m.get('memory_slang')}\n")
