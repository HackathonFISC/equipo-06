"""A2b · Resolutor de ubicación ambigua (el "agente de ubicación").

Casos que resuelve:
  1. WhatsApp comparte ubicación GPS -> se asigna el sector más cercano.
  2. El texto es vago ("por ahí", "detrás del hospital", "no sé dónde vivo"):
     se usan referencias locales (gacetero) + alias aprendidos y, si sigue
     ambiguo, el agente REDACTEA UNA PREGUNTA para devolver al ciudadano.
  3. Caso normal: delega en A2 (geolocalización difusa).

Este agente no adivina: cuando no está seguro, pregunta. Esa pregunta se puede
enviar por WhatsApp (bandeja de salida), cerrando el ciclo conversacional.
"""
from __future__ import annotations

import math
import time

from config import VAGUE_LOCATION_MARKERS
from services import catalog
from schemas import Report
from services.traces import log_step
from agents import geolocation

AGENT = "A2b_Geo_Ambiguo"


def _norm(text: str) -> str:
    import re
    text = (text or "").lower()
    text = re.sub(r"[^a-záéíóúñ0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_sector(lat: float, lon: float) -> tuple[str, str, float]:
    best = (None, None, 1e9)
    for s in catalog.sectors():
        d = _haversine_km(lat, lon, s.latitude, s.longitude)
        if d < best[2]:
            best = (s.id, s.name, round(d, 3))
    return best  # (sector_id, name, km)


def _is_vague(text: str) -> bool:
    low = _norm(text)
    if not low or len(low.split()) <= 2:
        return True
    return any(m in low for m in VAGUE_LOCATION_MARKERS)


def _clarify_question(report: Report) -> str:
    candidates = report.meta.get("geo_candidates", [])
    if len(candidates) >= 2:
        names = " o ".join(c["sector_name"] for c in candidates[:3])
        return (f"Recibimos tu reporte pero no estamos seguros de la zona. "
                f"¿Te refieres a {names}? Responde con el nombre de tu barriada.")
    if len(candidates) == 1:
        return (f"¿Confirmas que es en {candidates[0]['sector_name']}? "
                f"Responde SÍ o dime tu barriada exacta.")
    return ("Para enviarte el camión cisterna necesitamos tu zona. "
            "¿En qué barriada o corregimiento estás? (por ejemplo: Burunga, "
            "Vista Alegre, Barrio Colón...)")


def resolve(report: Report, run_id: str) -> Report:
    started = time.perf_counter()

    # 1) Ubicación GPS compartida por WhatsApp
    gps = report.meta.get("gps") or {}
    if gps.get("latitude") is not None and gps.get("longitude") is not None:
        sid, name, km = nearest_sector(float(gps["latitude"]), float(gps["longitude"]))
        if sid and km <= 6.0:
            report.sector_id = sid
            report.status = "recibido" if report.status != "rechazado" else report.status
            report.meta["geo_source"] = f"gps_whatsapp ({km} km)"
            report.meta["needs_clarification"] = False
            log_step(run_id, AGENT, "geo_gps", {"lat": gps.get("latitude"), "lon": gps.get("longitude")},
                     {"sector_id": sid, "name": name, "km": km}, tools=["haversine"],
                     latency_ms=(time.perf_counter() - started) * 1000,
                     decision=f"GPS -> {name}")
            return report

    # 2) Resolución textual (A2, ya enriquecida con gacetero y alias aprendidos)
    report = geolocation.resolve_location(report, run_id)

    # 3) ¿Hace falta preguntar?
    vague = _is_vague(report.sector_hint or report.raw_text)
    needs = report.sector_id is None
    if needs:
        report.meta["needs_clarification"] = True
        report.meta["clarify_question"] = _clarify_question(report)
        report.meta["vague_text"] = vague
        decision = "pregunta de aclaración generada" if vague else "ubicación no resuelta -> preguntar"
    else:
        report.meta["needs_clarification"] = False
        decision = "ubicación resuelta"

    log_step(run_id, AGENT, "resolver_ubicacion",
             {"hint": report.sector_hint, "vago": vague},
             {"sector_id": report.sector_id, "needs_clarification": report.meta.get("needs_clarification"),
              "pregunta": report.meta.get("clarify_question")},
             tools=["gacetero_local", "memoria_alias", "haversine"],
             latency_ms=(time.perf_counter() - started) * 1000, decision=decision)
    return report
