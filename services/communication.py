"""
Módulo 5 - Comunicación.
Solo redacta BORRADORES informativos. No envía nada y no promete hora de llegada.
"""

from typing import Dict, List

from models.schemas import Asignacion, SectorPendiente

AVISO = "BORRADOR - no enviado. Requiere revisión humana antes de cualquier uso."


def redactar_borradores(asignaciones: List[Asignacion], pendientes: List[SectorPendiente]) -> List[Dict[str, str]]:
    borradores: List[Dict[str, str]] = []
    por_sector: Dict[str, List[Asignacion]] = {}
    for a in asignaciones:
        por_sector.setdefault(a.sector, []).append(a)

    for sector, items in por_sector.items():
        total = sum(i.litros for i in items)
        total_txt = f"{total:,}".replace(",", " ")
        cist = ", ".join(sorted({i.cisterna_id for i in items}))
        borradores.append({
            "sector": sector,
            "tipo": "asignación propuesta",
            "texto": (
                f"Aviso para {sector}: hemos recibido los reportes de falta de agua y se está "
                f"programando abastecimiento con cisternas ({cist}), hasta {total_txt} litros previstos. "
                "La hora de llegada aún no está confirmada; informaremos cuando lo esté. "
                "Gracias por su paciencia.\n\n" + AVISO),
        })
    for p in pendientes:
        borradores.append({
            "sector": p.sector,
            "tipo": "pendiente",
            "texto": (
                f"Aviso para {p.sector}: su reporte fue recibido y está en evaluación. "
                "Por ahora no podemos confirmar abastecimiento ni horario. "
                "Le mantendremos informado.\n\n" + AVISO),
        })
    return borradores
