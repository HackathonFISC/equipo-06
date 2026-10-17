"""
Módulo 4 - Planificador (determinista).

Recorre los sectores de mayor a menor prioridad y les asigna litros de cisternas
DISPONIBLES, sin superar litros_disponibles de ninguna cisterna. Prefiere la cisterna
con sede en el mismo sector y luego la de mayor disponibilidad restante. Un sector
puede usar varias cisternas. Si no alcanza, queda (parcial o totalmente) pendiente
con el motivo. No promete horas de llegada.
"""

from typing import Dict, List, Tuple

import config
from models.schemas import (Asignacion, Cisterna, EstadoCisterna, PrioridadSector,
                            SectorPendiente)


def litros_requeridos(personas: int, litros_por_persona: int = config.LITROS_POR_PERSONA) -> int:
    # redondeo hacia arriba a múltiplos de 100 L
    bruto = personas * litros_por_persona
    return ((bruto + 99) // 100) * 100


def proponer_asignaciones(prioridades: List[PrioridadSector], cisternas: List[Cisterna],
                          litros_por_persona: int = config.LITROS_POR_PERSONA
                          ) -> Tuple[List[Asignacion], List[SectorPendiente]]:
    libre: Dict[str, int] = {c.id: c.litros_disponibles for c in cisternas
                             if c.estado == EstadoCisterna.DISPONIBLE}
    base: Dict[str, str] = {c.id: (c.sector_base or "") for c in cisternas}
    asignaciones: List[Asignacion] = []
    pendientes: List[SectorPendiente] = []
    hay_cisternas = bool(libre)

    for p in prioridades:  # ya vienen ordenadas por puntaje desc
        if p.personas_afectadas is None or p.personas_afectadas <= 0:
            pendientes.append(SectorPendiente(
                sector=p.sector, prioridad=p.puntaje, litros_requeridos=0, litros_cubiertos=0,
                litros_faltantes=0,
                motivo="Falta el dato de personas afectadas: no se estima la demanda. Corrija el reporte."))
            continue
        requerido = litros_requeridos(p.personas_afectadas, litros_por_persona)
        falta = requerido
        orden = sorted(libre, key=lambda cid: (base[cid] != p.sector, -libre[cid], cid))
        for cid in orden:
            if falta <= 0:
                break
            if libre[cid] <= 0:
                continue
            tomar = min(libre[cid], falta)
            libre[cid] -= tomar
            falta -= tomar
            asignaciones.append(Asignacion(
                sector=p.sector, cisterna_id=cid, litros=tomar, prioridad=p.puntaje,
                nota=("cisterna con sede en el sector" if base[cid] == p.sector else "")))
        if falta > 0:
            if not hay_cisternas:
                motivo = "No hay cisternas disponibles."
            elif falta == requerido:
                motivo = "Capacidad agotada: las cisternas disponibles ya se asignaron a sectores de mayor prioridad."
            else:
                motivo = "Cobertura parcial: la capacidad restante de las cisternas no alcanza para toda la demanda."
            pendientes.append(SectorPendiente(
                sector=p.sector, prioridad=p.puntaje, litros_requeridos=requerido,
                litros_cubiertos=requerido - falta, litros_faltantes=falta, motivo=motivo))
    return asignaciones, pendientes


def validar_asignaciones(asignaciones: List[Asignacion], cisternas: List[Cisterna]) -> List[str]:
    """Devuelve errores si un plan (p. ej. editado a mano) viola capacidad o disponibilidad."""
    errores: List[str] = []
    por_id = {c.id: c for c in cisternas}
    usados: Dict[str, int] = {}
    for a in asignaciones:
        c = por_id.get(a.cisterna_id)
        if c is None:
            errores.append(f"La cisterna {a.cisterna_id} no existe.")
            continue
        if c.estado != EstadoCisterna.DISPONIBLE:
            errores.append(f"{c.id} no está disponible ({c.estado.value}).")
        usados[c.id] = usados.get(c.id, 0) + a.litros
    for cid, total in usados.items():
        c = por_id.get(cid)
        if c and total > c.litros_disponibles:
            errores.append(f"{cid} excede su disponibilidad: {total} L asignados de {c.litros_disponibles} L.")
    return errores
