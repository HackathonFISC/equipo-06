"""
Módulo 2 - Geolocalización y deduplicación.
Contrasta contra el catálogo local de sectores y SUGIERE posibles duplicados.
Nunca fusiona: la decisión es siempre de una persona.
"""

from typing import List, Optional

import config
from models.schemas import CandidatoDuplicado, Reporte, Sector, EstadoReporte
from services.textutil import normalizar, palabras_clave


def resolver_sector(nombre: Optional[str], sectores: List[Sector]) -> Optional[Sector]:
    """Devuelve el sector del catálogo que coincide con `nombre` (sin acentos/mayúsculas)."""
    if not nombre:
        return None
    n = normalizar(nombre)
    for s in sectores:
        if normalizar(s.nombre) == n or n in [normalizar(a) for a in s.alias]:
            return s
    return None


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def sugerir_duplicados(nuevo: Reporte, existentes: List[Reporte],
                       umbral: float = config.UMBRAL_DUPLICADO) -> List[CandidatoDuplicado]:
    """Compara con reportes del MISMO sector. Puntaje 0-1 con motivos legibles."""
    candidatos: List[CandidatoDuplicado] = []
    if not nuevo.sector:
        return candidatos
    for o in existentes:
        if o.id == nuevo.id or o.estado in (EstadoReporte.RECHAZADO, EstadoReporte.DUPLICADO):
            continue
        if o.sector != nuevo.sector:
            continue
        motivos = ["mismo sector"]
        score = 0.30

        if nuevo.horas_sin_agua is not None and o.horas_sin_agua is not None:
            dif = abs(nuevo.horas_sin_agua - o.horas_sin_agua)
            if dif <= 6:
                score += 0.25
                motivos.append(f"tiempo sin agua similar ({nuevo.horas_sin_agua:g} h vs {o.horas_sin_agua:g} h)")
            elif dif <= 12:
                score += 0.10
                motivos.append("tiempo sin agua parecido")

        if nuevo.calle and o.calle:
            sc = _jaccard(palabras_clave(nuevo.calle), palabras_clave(o.calle))
            if sc >= 0.5:
                score += 0.25
                motivos.append(f"misma calle/referencia ('{o.calle}')")

        st = _jaccard(palabras_clave(nuevo.mensaje_original), palabras_clave(o.mensaje_original))
        score += 0.20 * min(st * 2, 1.0)
        if st >= 0.3:
            motivos.append(f"texto parecido ({st:.0%} de palabras clave)")

        score = round(min(score, 1.0), 2)
        if score >= umbral:
            candidatos.append(CandidatoDuplicado(reporte_id=o.id, similitud=score, motivos=motivos, dudoso=True))
    candidatos.sort(key=lambda c: c.similitud, reverse=True)
    return candidatos
