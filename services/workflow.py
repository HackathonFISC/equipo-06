"""
Flujo de trabajo completo (sin interfaz). La UI de Streamlit y la API FastAPI
llaman SOLO a estas funciones; así la lógica puede alojarse en una Raspberry Pi
detrás de cualquier interfaz.

reporte -> revisión -> sector/duplicados -> prioridad -> plan -> decisión -> auditoría
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import config
from data import database as db
from data.datos_ficticios import CISTERNAS_FICTICIAS, REPORTES_FICTICIOS, SECTORES_FICTICIOS
from models.schemas import (AccionDecision, Asignacion, Cisterna, ConfirmacionDispositivo,
                            Decision, EstadoActual, EstadoPlan, EstadoReporte, PropuestaPlan,
                            Reporte, Sector, Severidad, CandidatoDuplicado, PrioridadSector,
                            SCHEMA_VERSION)
from services import audit, communication, geoloc, ingest, planner, prioritization


class ErrorDeNegocio(ValueError):
    """Error esperado (validación); la interfaz lo muestra al usuario."""


# ---------------------------------------------------------------- catálogos
def listar_sectores() -> List[Sector]:
    return [Sector(**d) for d in db.listar("sectores")]


def listar_cisternas() -> List[Cisterna]:
    return [Cisterna(**d) for d in db.listar("cisternas")]


def cargar_datos_demo(responsable: str = "sistema") -> Dict[str, int]:
    """Reinicia la base con datos FICTICIOS y procesa los reportes de ejemplo
    (queda en 'por_revisar': una persona debe confirmarlos)."""
    db.vaciar()
    for s in SECTORES_FICTICIOS:
        sec = Sector(**s)
        db.insertar("sectores", sec.model_dump(mode="json"), clave=sec.nombre)
    for c in CISTERNAS_FICTICIAS:
        cis = Cisterna(**c)
        db.insertar("cisternas", cis.model_dump(mode="json"), clave=cis.id)
    for texto in REPORTES_FICTICIOS:
        crear_reporte(texto, responsable=responsable, ficticio=True, auditar=False)
    audit.registrar(responsable, "cargar_datos_demo", "sistema", "demo",
                    detalle={"reportes": len(REPORTES_FICTICIOS), "cisternas": len(CISTERNAS_FICTICIAS),
                             "sectores": len(SECTORES_FICTICIOS), "ficticio": True})
    return {"reportes": len(REPORTES_FICTICIOS), "cisternas": len(CISTERNAS_FICTICIAS),
            "sectores": len(SECTORES_FICTICIOS)}


# ----------------------------------------------------------------- reportes
def _reporte(d: Dict[str, Any]) -> Reporte:
    return Reporte(**d)


def listar_reportes() -> List[Reporte]:
    return [_reporte(d) for d in db.listar("reportes")]


def obtener_reporte(reporte_id: int) -> Reporte:
    d = db.obtener("reportes", reporte_id)
    if d is None:
        raise ErrorDeNegocio(f"El reporte {reporte_id} no existe.")
    return _reporte(d)


def crear_reporte(texto: str, responsable: str = "anónimo", ficticio: bool = False,
                  auditar: bool = True) -> Reporte:
    """Ingesta: guarda el texto original y los campos extraídos (sin confirmar)."""
    texto = (texto or "").strip()
    if not texto:
        raise ErrorDeNegocio("El texto del reporte no puede estar vacío.")
    ex = ingest.interpretar(texto, listar_sectores())
    datos = {
        "mensaje_original": texto, "fecha_creacion": datetime.now().isoformat(timespec="seconds"),
        "estado": EstadoReporte.POR_REVISAR.value, "sector": ex.sector, "calle": ex.calle,
        "horas_sin_agua": ex.horas_sin_agua, "personas_afectadas": ex.personas_afectadas,
        "severidad": ex.severidad.value if ex.severidad else None,
        "datos_faltantes": ex.datos_faltantes, "datos_inciertos": ex.datos_inciertos,
        "notas": ex.notas, "campos_corregidos": [], "ficticio": ficticio, "id": 0,
    }
    rid = db.insertar("reportes", datos)
    rep = obtener_reporte(rid)
    if auditar:
        audit.registrar(responsable, "crear_reporte", "reporte", rid,
                        detalle={"extraccion": ex.model_dump(mode="json")})
    return rep


def _recalcular_faltantes(r: Reporte) -> None:
    campos = ("sector", "horas_sin_agua", "personas_afectadas", "severidad")
    r.datos_faltantes = [c for c in campos if getattr(r, c) is None]
    r.datos_inciertos = [c for c in r.datos_inciertos
                         if c not in r.campos_corregidos and c not in r.datos_faltantes]


def corregir_y_confirmar(reporte_id: int, responsable: str, sector: Optional[str],
                         horas_sin_agua: Optional[float], personas_afectadas: Optional[int],
                         severidad: Optional[str], calle: Optional[str]) -> Reporte:
    """Una persona revisa/corrige lo extraído y confirma. Requiere sector válido del catálogo."""
    if not responsable.strip():
        raise ErrorDeNegocio("Indique el responsable.")
    r = obtener_reporte(reporte_id)
    if r.estado not in (EstadoReporte.POR_REVISAR, EstadoReporte.CONFIRMADO):
        raise ErrorDeNegocio(f"El reporte está '{r.estado.value}' y no se puede editar.")
    sec = geoloc.resolver_sector(sector, listar_sectores())
    if sec is None:
        raise ErrorDeNegocio("Elija un sector válido del catálogo para confirmar la ubicación.")
    if horas_sin_agua is not None and horas_sin_agua < 0:
        raise ErrorDeNegocio("Las horas sin agua no pueden ser negativas.")
    if personas_afectadas is not None and personas_afectadas < 0:
        raise ErrorDeNegocio("Las personas afectadas no pueden ser negativas.")
    sev = Severidad(severidad) if severidad else None

    nuevos = {"sector": sec.nombre, "horas_sin_agua": horas_sin_agua,
              "personas_afectadas": personas_afectadas, "severidad": sev, "calle": calle or None}
    cambios = {}
    for campo, nuevo in nuevos.items():
        anterior = getattr(r, campo)
        if anterior != nuevo:
            cambios[campo] = {"antes": getattr(anterior, "value", anterior), "despues": getattr(nuevo, "value", nuevo)}
            setattr(r, campo, nuevo)
            if campo not in r.campos_corregidos:
                r.campos_corregidos.append(campo)
    _recalcular_faltantes(r)
    r.estado = EstadoReporte.CONFIRMADO
    r.confirmado_por = responsable
    db.actualizar("reportes", r.id, r.model_dump(mode="json"))
    audit.registrar(responsable, "confirmar_reporte", "reporte", r.id, detalle={"cambios": cambios})
    return r


def rechazar_reporte(reporte_id: int, responsable: str, motivo: str) -> Reporte:
    if not motivo.strip():
        raise ErrorDeNegocio("Indique el motivo del rechazo.")
    r = obtener_reporte(reporte_id)
    r.estado = EstadoReporte.RECHAZADO
    db.actualizar("reportes", r.id, r.model_dump(mode="json"))
    audit.registrar(responsable, "rechazar_reporte", "reporte", r.id, motivo=motivo)
    return r


# --------------------------------------------------------------- duplicados
def sugerir_duplicados(reporte_id: int) -> List[CandidatoDuplicado]:
    r = obtener_reporte(reporte_id)
    return geoloc.sugerir_duplicados(r, listar_reportes())


def resolver_duplicado(reporte_id: int, otro_id: int, es_duplicado: bool,
                       responsable: str, motivo: str = "") -> Reporte:
    """La persona decide. Si es duplicado, `reporte_id` queda ligado a `otro_id`
    y sale del cálculo; nada se fusiona ni se borra."""
    if not responsable.strip():
        raise ErrorDeNegocio("Indique el responsable.")
    r = obtener_reporte(reporte_id)
    obtener_reporte(otro_id)
    if es_duplicado:
        r.estado = EstadoReporte.DUPLICADO
        r.duplicado_de = otro_id
        db.actualizar("reportes", r.id, r.model_dump(mode="json"))
    db.insertar("decisiones_duplicado", {"reporte_id": reporte_id, "otro_id": otro_id,
                                         "es_duplicado": es_duplicado, "responsable": responsable})
    audit.registrar(responsable, "duplicado_si" if es_duplicado else "duplicado_no", "reporte", reporte_id,
                    motivo=motivo, detalle={"otro_reporte": otro_id})
    return r


def decisiones_duplicado() -> List[Dict[str, Any]]:
    return db.listar("decisiones_duplicado")


# ---------------------------------------------------------------- prioridad
def calcular_prioridades() -> List[PrioridadSector]:
    return prioritization.calcular_prioridades(listar_reportes(), listar_sectores())


# --------------------------------------------------------------------- plan
def _plan(d: Dict[str, Any]) -> PropuestaPlan:
    return PropuestaPlan(**d)


def listar_planes() -> List[PropuestaPlan]:
    return [_plan(d) for d in db.listar("planes")]


def obtener_plan(plan_id: int) -> PropuestaPlan:
    d = db.obtener("planes", plan_id)
    if d is None:
        raise ErrorDeNegocio(f"El plan {plan_id} no existe.")
    return _plan(d)


def _resumen(asig: List[Asignacion], pend, prios: List[PrioridadSector], cist: List[Cisterna]) -> Dict[str, Any]:
    total_disp = sum(c.litros_disponibles for c in cist if c.estado.value == "disponible")
    usado = sum(a.litros for a in asig)
    return {
        "sectores_con_prioridad": len(prios),
        "sectores_atendidos": len({a.sector for a in asig if a.sector not in {p.sector for p in pend}}),
        "sectores_pendientes": sorted({p.sector for p in pend}),
        "litros_disponibles": total_disp, "litros_asignados": usado, "litros_sobrantes": total_disp - usado,
    }


def _guardar_derivados(plan: PropuestaPlan) -> None:
    plan.borradores_comunicacion = communication.redactar_borradores(plan.asignaciones, plan.pendientes)
    plan.resumen = _resumen(plan.asignaciones, plan.pendientes, plan.prioridades, listar_cisternas())


def generar_plan(responsable: str) -> PropuestaPlan:
    """Calcula prioridades y propone asignaciones. NO aprueba ni envía nada."""
    prios = calcular_prioridades()
    if not prios:
        raise ErrorDeNegocio("No hay reportes confirmados. Confirme al menos un reporte primero.")
    cist = listar_cisternas()
    asig, pend = planner.proponer_asignaciones(prios, cist)
    plan = PropuestaPlan(id=0, fecha_creacion=datetime.now(), litros_por_persona=config.LITROS_POR_PERSONA,
                         asignaciones=asig, pendientes=pend, prioridades=prios)
    _guardar_derivados(plan)
    pid = db.insertar("planes", plan.model_dump(mode="json"))
    plan.id = pid
    db.actualizar("planes", pid, plan.model_dump(mode="json"))
    audit.registrar(responsable, "generar_plan", "plan", pid,
                    detalle={"resumen": plan.resumen, "asignaciones": len(asig), "pendientes": len(pend)})
    return plan


def editar_plan(plan_id: int, nuevas_asignaciones: List[Asignacion], responsable: str, motivo: str) -> PropuestaPlan:
    """Modifica asignaciones de un plan 'propuesto'. Valida capacidad; registra antes/después."""
    if not responsable.strip():
        raise ErrorDeNegocio("Indique el responsable.")
    if not motivo.strip():
        raise ErrorDeNegocio("Indique el motivo de la modificación.")
    plan = obtener_plan(plan_id)
    if plan.estado != EstadoPlan.PROPUESTO:
        raise ErrorDeNegocio(f"El plan está '{plan.estado.value}' y ya no se puede editar.")
    errores = planner.validar_asignaciones(nuevas_asignaciones, listar_cisternas())
    if errores:
        raise ErrorDeNegocio("El plan editado no es válido: " + " ".join(errores))
    antes = [a.model_dump(mode="json") for a in plan.asignaciones]
    despues = [a.model_dump(mode="json") for a in nuevas_asignaciones]
    if antes == despues:
        raise ErrorDeNegocio("No hay cambios que guardar.")
    plan.asignaciones = nuevas_asignaciones
    plan.editado = True
    plan.version += 1
    _recalcular_pendientes(plan)
    _guardar_derivados(plan)
    db.actualizar("planes", plan.id, plan.model_dump(mode="json"))
    audit.registrar(responsable, "editar_plan", "plan", plan.id, motivo=motivo,
                    detalle={"antes": antes, "despues": despues, "version": plan.version})
    return plan


def _recalcular_pendientes(plan: PropuestaPlan) -> None:
    """Tras una edición manual, recalcula qué demanda queda sin cubrir (determinista)."""
    from models.schemas import SectorPendiente
    cubierto: Dict[str, int] = {}
    for a in plan.asignaciones:
        cubierto[a.sector] = cubierto.get(a.sector, 0) + a.litros
    pend = []
    for p in plan.prioridades:
        if not p.personas_afectadas:
            pend.append(SectorPendiente(sector=p.sector, prioridad=p.puntaje, litros_requeridos=0,
                                        litros_cubiertos=0, litros_faltantes=0,
                                        motivo="Falta el dato de personas afectadas."))
            continue
        req = planner.litros_requeridos(p.personas_afectadas, plan.litros_por_persona)
        cub = min(cubierto.get(p.sector, 0), req)
        if cub < req:
            pend.append(SectorPendiente(sector=p.sector, prioridad=p.puntaje, litros_requeridos=req,
                                        litros_cubiertos=cub, litros_faltantes=req - cub,
                                        motivo="Cobertura incompleta tras la modificación manual del plan."))
    plan.pendientes = pend


def decidir_plan(plan_id: int, accion: AccionDecision, responsable: str, motivo: str = "") -> PropuestaPlan:
    """Aprobar o rechazar. Rechazar exige motivo. Aprobar revalida capacidad."""
    if accion == AccionDecision.EDITAR:
        raise ErrorDeNegocio("Para editar use editar_plan().")
    if not responsable.strip():
        raise ErrorDeNegocio("Indique el responsable.")
    plan = obtener_plan(plan_id)
    if plan.estado != EstadoPlan.PROPUESTO:
        raise ErrorDeNegocio(f"El plan ya está '{plan.estado.value}'.")
    if accion == AccionDecision.RECHAZAR:
        if not motivo.strip():
            raise ErrorDeNegocio("Indique el motivo del rechazo.")
        plan.estado = EstadoPlan.RECHAZADO
    else:
        errores = planner.validar_asignaciones(plan.asignaciones, listar_cisternas())
        if errores:
            raise ErrorDeNegocio("No se puede aprobar: " + " ".join(errores))
        if plan.editado and not motivo.strip():
            raise ErrorDeNegocio("El plan fue modificado: indique el motivo/comentario de la aprobación.")
        plan.estado = EstadoPlan.APROBADO
        atendidos = {a.sector for a in plan.asignaciones}
        for r in listar_reportes():
            if r.estado == EstadoReporte.CONFIRMADO and r.sector in atendidos:
                r.estado = EstadoReporte.EN_PLAN
                db.actualizar("reportes", r.id, r.model_dump(mode="json"))
    db.actualizar("planes", plan.id, plan.model_dump(mode="json"))
    dec = Decision(plan_id=plan.id, accion=accion, responsable=responsable, motivo=motivo)
    audit.registrar(responsable, f"{accion.value}_plan", "plan", plan.id, motivo=motivo,
                    detalle={"decision": dec.model_dump(mode="json"), "editado": plan.editado,
                             "version": plan.version})
    return plan


# ------------------------------------------------- contratos para dispositivos
def estado_actual() -> EstadoActual:
    planes = listar_planes()
    aprobados = [p for p in planes if p.estado == EstadoPlan.APROBADO]
    propuestos = [p for p in planes if p.estado == EstadoPlan.PROPUESTO]
    activos = [r for r in listar_reportes() if r.estado in (EstadoReporte.CONFIRMADO, EstadoReporte.POR_REVISAR)]
    return EstadoActual(generado=datetime.now(), plan_aprobado=aprobados[-1] if aprobados else None,
                        plan_pendiente_de_revision=propuestos[-1] if propuestos else None,
                        reportes_activos=len(activos), cisternas=listar_cisternas())


def registrar_confirmacion_dispositivo(c: ConfirmacionDispositivo) -> None:
    """Un dispositivo publica una confirmación; solo se AUDITA, no cambia planes ni cisternas."""
    plan = obtener_plan(c.plan_id)
    if plan.estado != EstadoPlan.APROBADO:
        raise ErrorDeNegocio("Solo se aceptan confirmaciones sobre planes aprobados.")
    audit.registrar(f"dispositivo:{c.dispositivo_id}", f"confirmacion_{c.tipo}", "plan", c.plan_id,
                    detalle=c.model_dump(mode="json"))
