"""A6 · Verificador de entrega — una entrega cuenta solo si el GPS, los litros y la
comunidad coinciden.

Inspiración: la prensa documentó motos con GPS simulando camiones cisternas, y el
IDAAN ya exige caudalímetro digital e indicador de nivel. Por eso el GPS solo no basta.

Reglas deterministas -> luego una capa de umbrales. El sistema NO acusa a nadie:
marca la entrega como dudosa/rechazada y deja un paquete de evidencia para el humano.
"""
from __future__ import annotations

from schemas import DeliveryEvidence, DeliveryVerdict
from services.traces import log_step

AGENT = "A6_Verificador"

MAX_TRUCK_SPEED_KMH = 90.0
MIN_STOP_SECONDS = 45.0
MIN_CONFIRMATIONS = 2


def verify(ev: DeliveryEvidence, run_id: str = "run_ad_hoc") -> DeliveryVerdict:
    checks: list[dict] = []
    reasons: list[str] = []

    # 1) GPS: velocidad imposible, fuera de vía o sin detenerse.
    gps_ok = True
    if ev.gps_max_speed_kmh > MAX_TRUCK_SPEED_KMH:
        gps_ok = False
        reasons.append(f"Velocidad máxima {ev.gps_max_speed_kmh:.0f} km/h: no es un camión cargado (posible moto).")
    if ev.gps_offroad_ratio > 0.35:
        gps_ok = False
        reasons.append(f"{ev.gps_offroad_ratio:.0%} del recorrido fuera de vía.")
    if ev.seconds_stopped_at_point < MIN_STOP_SECONDS:
        gps_ok = False
        reasons.append("El camión no se detuvo el tiempo suficiente en el punto de entrega.")
    checks.append({"signal": "gps", "ok": gps_ok})

    # 2) Litros: balance de masa y límite físico del tanque.
    liters_ok = True
    if ev.liters_reported > ev.tank_capacity_liters:
        liters_ok = False
        reasons.append(f"Litros reportados ({ev.liters_reported:,}) mayores que el tanque ({ev.tank_capacity_liters:,}).")
    if ev.liters_reported <= 0:
        liters_ok = False
        reasons.append("Cero litros entregados: entrega fantasma.")
    checks.append({"signal": "litros", "ok": liters_ok})

    # 3) Comunidad: confirmaciones válidas dentro de 500 m.
    valid_conf = ev.community_confirmations - ev.confirmations_from_outside
    community_ok = valid_conf >= MIN_CONFIRMATIONS
    if not community_ok:
        reasons.append(f"Solo {max(valid_conf, 0)} confirmación(es) válida(s); se requieren {MIN_CONFIRMATIONS}.")
    checks.append({"signal": "comunidad", "ok": community_ok})

    # 4) Repetición: traza calcada de una vieja.
    repeat_ok = ev.trace_similarity_to_history < 0.95
    if not repeat_ok:
        reasons.append("La traza es casi idéntica a una entrega anterior (posible repetición).")
    checks.append({"signal": "repeticion", "ok": repeat_ok})

    failures = sum(1 for c in checks if not c["ok"])
    physical_violation = ev.liters_reported > ev.tank_capacity_liters
    if failures == 0:
        status = "confirmada"
    elif failures >= 2 or physical_violation:
        status = "rechazada"
    else:
        status = "dudosa"

    verdict = DeliveryVerdict(status=status, checks=checks, reasons=reasons or ["Las tres señales coinciden."])
    log_step(run_id, AGENT, "verificacion_entrega",
             {"sector": ev.sector_id, "litros": ev.liters_reported},
             {"status": status, "fallos": failures}, tools=["reglas_deterministas"],
             decision=status)
    return verdict
