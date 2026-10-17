"""
Flujo de trabajo completo (sin interfaz). La interfaz Flet y la API FastAPI llaman SOLO a estas
funciones; las reglas viven aquí, no en la interfaz.

reporte -> revisión -> sector/duplicados -> prioridad -> plan -> decisión -> auditoría

Consistencia: cada operación que cambia datos corre en UNA transacción SQLite junto con su
registro de auditoría (si algo falla, se revierte todo). Las trazas JSONL son aparte y no
forman parte de la transacción.
"""

import functools
import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import config
from data import database as db
from data.datos_ficticios import CISTERNAS_FICTICIAS, REPORTES_FICTICIOS, SECTORES_FICTICIOS
from models.schemas import (AccionDecision, Asignacion, CandidatoDuplicado, Cisterna,
                            ConfirmacionDispositivo, Decision, EstadoActual, EstadoPlan,
                            EstadoReporte, PrioridadSector, PropuestaPlan, Reporte, Sector,
                            SectorPendiente, Severidad)
from services import (audit, auth, communication, geoloc, ia_tareas, ingest, planner, prioritization,
                      tracing)
from services.auth import requiere_admin
from services.textutil import normalizar


class ErrorDeNegocio(ValueError):
    """Error esperado (validación); la interfaz/API lo muestra al usuario."""


class ErrorLimite(ErrorDeNegocio):
    """Demasiadas solicitudes desde el mismo origen (→ 429 en la API)."""


_SIN_CAMBIO = object()

# Máquina de estados de reportes: el BACKEND impide transiciones inválidas aunque se llame a la API.
TRANSICIONES_REPORTE = {
    EstadoReporte.POR_REVISAR: {EstadoReporte.CONFIRMADO, EstadoReporte.RECHAZADO, EstadoReporte.DUPLICADO},
    EstadoReporte.CONFIRMADO: {EstadoReporte.CONFIRMADO, EstadoReporte.RECHAZADO, EstadoReporte.DUPLICADO,
                               EstadoReporte.EN_PLAN},
    EstadoReporte.DUPLICADO: set(),
    EstadoReporte.RECHAZADO: set(),
    EstadoReporte.EN_PLAN: set(),
}
TRANSICIONES_PLAN = {
    EstadoPlan.PROPUESTO: {EstadoPlan.APROBADO, EstadoPlan.RECHAZADO},
    EstadoPlan.APROBADO: set(),
    EstadoPlan.RECHAZADO: set(),
}


def _mover_reporte(r: Reporte, nuevo: EstadoReporte) -> None:
    if nuevo not in TRANSICIONES_REPORTE[r.estado]:
        raise ErrorDeNegocio(f"Transición no permitida para el reporte {r.id}: '{r.estado.value}' → '{nuevo.value}'.")
    r.estado = nuevo


def _mover_plan(p: PropuestaPlan, nuevo: EstadoPlan) -> None:
    if nuevo not in TRANSICIONES_PLAN[p.estado]:
        raise ErrorDeNegocio(f"Transición no permitida para el plan {p.id}: '{p.estado.value}' → '{nuevo.value}'.")
    p.estado = nuevo


def _exigir_responsable(responsable: str) -> str:
    if not responsable or not responsable.strip():
        raise ErrorDeNegocio("Indique el responsable.")
    return responsable.strip()


def _resolver_responsable(declarado: Optional[str]) -> str:
    """Quién queda en la auditoría. Con sesión de usuario prevalece SIEMPRE el usuario autenticado (el nombre
    declarado se ignora: no se puede firmar como otra persona). Con el token de servicio de la API se respeta el
    nombre declarado, marcado como `servicio:<nombre>`. Sin actor (solo portal público) no hay identidad."""
    a = auth.actor()
    if a is None:
        return _exigir_responsable(declarado)
    if a.origen == "servicio":
        return f"servicio:{_exigir_responsable(declarado)}"
    return a.usuario


# Límite de tasa simple en memoria (por origen). Se pierde al reiniciar; no sustituye a un proxy/WAF.
_LIMITE_REPORTES = (10, 60)    # 10 reportes por minuto y origen
_LIMITE_CONSULTAS = (20, 60)   # 20 consultas de código por minuto y origen (frena la adivinación de códigos)
_intentos: Dict[str, List[float]] = {}


def _limitar(clave: str, limite) -> None:
    maximo, ventana = limite
    ahora = time.monotonic()
    recientes = [t for t in _intentos.get(clave, []) if ahora - t < ventana]
    if len(recientes) >= maximo:
        _intentos[clave] = recientes
        raise ErrorLimite("Demasiadas solicitudes. Espere un minuto e inténtelo de nuevo.")
    recientes.append(ahora)
    _intentos[clave] = recientes


def reiniciar_limites() -> None:
    """Pruebas: borra los contadores de tasa."""
    _intentos.clear()


def operacion(nombre: str):
    """Transacción SQLite + ejecución trazada para una operación de negocio."""
    def deco(fn):
        @functools.wraps(fn)
        def envoltura(*a, **k):
            with tracing.ejecucion():
                with tracing.traza("workflow", nombre, {"args": [type(x).__name__ for x in a], "kwargs": list(k)}) as t:
                    with db.transaccion():
                        resultado = fn(*a, **k)
                    t["output"] = {"tipo": type(resultado).__name__,
                                   "id": getattr(resultado, "id", None)}
                    return resultado
        return envoltura
    return deco


# ---------------------------------------------------------------- catálogos
# Decisión de seguridad: listar_sectores/listar_cisternas NO exigen rol en la capa de negocio porque son el
# catálogo FICTICIO de referencia que usan por dentro casi todas las operaciones (y la interfaz para sus
# listas desplegables). La API NO los expone sin rol de administrador (/cisternas exige admin) y el portal
# público tampoco. Si el catálogo llegara a contener datos reales sensibles, deben pasar a @requiere_admin.
def listar_sectores() -> List[Sector]:
    return [Sector(**d) for d in db.listar("sectores")]


def listar_cisternas() -> List[Cisterna]:
    return [Cisterna(**d) for d in db.listar("cisternas")]


@requiere_admin
@operacion("cargar_datos_demo")
def cargar_datos_demo(responsable: str = "sistema") -> Dict[str, int]:
    """Reinicia la base con datos FICTICIOS y procesa los reportes de ejemplo (quedan 'por_revisar').
    No borra las cuentas de usuario (tabla `usuarios`)."""
    responsable = _resolver_responsable(responsable)
    db.vaciar()
    for s in SECTORES_FICTICIOS:
        sec = Sector(**s)
        db.insertar("sectores", sec.model_dump(mode="json"), clave=sec.nombre)
    for c in CISTERNAS_FICTICIAS:
        cis = Cisterna(**c)
        db.insertar("cisternas", cis.model_dump(mode="json"), clave=cis.id)
    for texto in REPORTES_FICTICIOS:
        _crear_reporte(texto, responsable=responsable, canal="demo", ficticio=True, auditar=False)
    audit.registrar(responsable, "cargar_datos_demo", "sistema", "demo",
                    detalle={"reportes": len(REPORTES_FICTICIOS), "cisternas": len(CISTERNAS_FICTICIAS),
                             "sectores": len(SECTORES_FICTICIOS), "ficticio": True})
    return {"reportes": len(REPORTES_FICTICIOS), "cisternas": len(CISTERNAS_FICTICIAS),
            "sectores": len(SECTORES_FICTICIOS)}


# ----------------------------------------------------------------- reportes
def _listar_reportes() -> List[Reporte]:
    return [Reporte(**d) for d in db.listar("reportes")]


@requiere_admin
def listar_reportes() -> List[Reporte]:
    return _listar_reportes()


def _obtener_reporte(reporte_id: int) -> Reporte:
    d = db.obtener("reportes", reporte_id)
    if d is None:
        raise ErrorDeNegocio(f"El reporte {reporte_id} no existe.")
    return Reporte(**d)


@requiere_admin
def obtener_reporte(reporte_id: int) -> Reporte:
    return _obtener_reporte(reporte_id)


def _guardar_reporte(r: Reporte) -> None:
    db.actualizar("reportes", r.id, r.model_dump(mode="json"))


_ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin I, O, 0, 1 (ambiguos)
_RE_CODIGO = re.compile(r"HID-[" + _ALFABETO_CODIGO + r"]{8}")


def _nuevo_codigo(usados: set) -> str:
    while True:
        c = "HID-" + "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(8))
        if c not in usados:
            return c


@operacion("crear_reporte")
def crear_reporte(texto: str, responsable: str = "anónimo", ficticio: bool = False, auditar: bool = True,
                  canal: str = "manual", clave_idempotencia: Optional[str] = None,
                  origen: Optional[str] = None) -> Reporte:
    """Ingesta. Es la única operación de escritura abierta al ciudadano anónimo (portal público): no exige rol.
    `origen` (p. ej. la IP del portal) activa el límite de tasa. Sin actor el responsable queda como «ciudadano»."""
    if origen:
        _limitar("reporte:" + origen, _LIMITE_REPORTES)
    return _crear_reporte(texto, responsable, ficticio, auditar, canal, clave_idempotencia)


def _crear_reporte(texto: str, responsable: str = "anónimo", ficticio: bool = False, auditar: bool = True,
                   canal: str = "manual", clave_idempotencia: Optional[str] = None) -> Reporte:
    """Guarda el texto original (inalterable) y los campos extraídos, sin confirmar.
    Idempotencia: la misma `clave_idempotencia`, o el mismo texto reciente dentro de
    config.IDEMPOTENCIA_SEGUNDOS, devuelve el reporte ya creado en vez de duplicarlo."""
    texto = (texto or "").strip()
    if not texto:
        raise ErrorDeNegocio("El texto del reporte no puede estar vacío.")
    if len(texto) > 4000:
        raise ErrorDeNegocio("El texto del reporte excede 4000 caracteres.")
    existentes = _listar_reportes()
    if clave_idempotencia:
        for r in existentes:
            if r.clave_idempotencia == clave_idempotencia:
                tracing.emitir("workflow", "crear_reporte_idempotente", "ok", {"reporte_id": r.id})
                return r
    elif not ficticio:
        huella = normalizar(texto)
        ahora = datetime.now()
        for r in reversed(existentes):
            if (ahora - r.fecha_creacion).total_seconds() > config.IDEMPOTENCIA_SEGUNDOS:
                break
            if normalizar(r.mensaje_original) == huella and not r.ficticio:
                tracing.emitir("workflow", "crear_reporte_idempotente", "ok", {"reporte_id": r.id, "motivo": "mismo texto reciente"})
                return r
    ex = ingest.interpretar(texto, listar_sectores())  # catálogo ficticio, ver nota de catálogos
    datos = {
        "mensaje_original": texto, "fecha_creacion": datetime.now().isoformat(timespec="seconds"),
        "estado": EstadoReporte.POR_REVISAR.value, "sector": ex.sector, "calle": ex.calle,
        "horas_sin_agua": ex.horas_sin_agua, "personas_afectadas": ex.personas_afectadas,
        "severidad": ex.severidad.value if ex.severidad else None,
        "datos_faltantes": ex.datos_faltantes, "datos_inciertos": ex.datos_inciertos,
        "notas": ex.notas, "campos_corregidos": [], "ficticio": ficticio, "id": 0, "canal": canal,
        "referencia_ubicacion": ex.referencia_ubicacion, "tipo_incidencia": ex.tipo_incidencia,
        "vulnerabilidades": ex.vulnerabilidades, "servicio_esencial": ex.servicio_esencial,
        "evidencia": ex.evidencia, "confianza_declarada": ex.confianza_declarada,
        "interprete": ex.metodo, "sector_candidatos": ex.sector_candidatos,
        "clave_idempotencia": clave_idempotencia,
        "codigo_seguimiento": _nuevo_codigo({r.codigo_seguimiento for r in existentes if r.codigo_seguimiento}),
    }
    rid = db.insertar("reportes", datos)
    tracing.correlacionar(f"reporte:{rid}")
    rep = _obtener_reporte(rid)
    if auditar:
        quien = "ciudadano" if auth.actor() is None else _resolver_responsable(responsable)
        audit.registrar(quien, "crear_reporte", "reporte", rid,
                        detalle={"extraccion": ex.model_dump(mode="json"), "canal": canal})
    return rep


def _recalcular_faltantes(r: Reporte) -> None:
    campos = ("sector", "horas_sin_agua", "personas_afectadas", "severidad")
    r.datos_faltantes = [c for c in campos if getattr(r, c) is None]
    r.datos_inciertos = [c for c in r.datos_inciertos
                         if c not in r.campos_corregidos and c not in r.datos_faltantes]


@requiere_admin
@operacion("confirmar_reporte")
def corregir_y_confirmar(reporte_id: int, responsable: str, sector: Optional[str],
                         horas_sin_agua: Optional[float], personas_afectadas: Optional[int],
                         severidad: Optional[str], calle: Optional[str],
                         servicio_esencial: Any = _SIN_CAMBIO, vulnerabilidades: Any = _SIN_CAMBIO,
                         tipo_incidencia: Any = _SIN_CAMBIO, referencia_ubicacion: Any = _SIN_CAMBIO) -> Reporte:
    """Una persona revisa/corrige lo extraído y confirma. Requiere sector válido del catálogo.
    El mensaje original no se modifica nunca."""
    responsable = _resolver_responsable(responsable)
    r = _obtener_reporte(reporte_id)
    _mover_reporte(r, EstadoReporte.CONFIRMADO)
    sec = geoloc.resolver_sector(sector, listar_sectores())
    if sec is None:
        raise ErrorDeNegocio("Elija un sector válido del catálogo para confirmar la ubicación.")
    if horas_sin_agua is not None and not (0 <= horas_sin_agua <= 24 * 365):
        raise ErrorDeNegocio("Las horas sin agua deben estar entre 0 y 8760.")
    if personas_afectadas is not None and not (0 <= personas_afectadas <= 100000):
        raise ErrorDeNegocio("Las personas afectadas deben estar entre 0 y 100000.")
    try:
        sev = Severidad(severidad) if severidad else None
    except ValueError:
        raise ErrorDeNegocio(f"Severidad inválida: {severidad}")

    nuevos: Dict[str, Any] = {"sector": sec.nombre, "horas_sin_agua": horas_sin_agua,
                              "personas_afectadas": personas_afectadas, "severidad": sev, "calle": calle or None}
    if servicio_esencial is not _SIN_CAMBIO:
        nuevos["servicio_esencial"] = servicio_esencial or None
    if vulnerabilidades is not _SIN_CAMBIO:
        nuevos["vulnerabilidades"] = sorted(set(vulnerabilidades or []))
    if tipo_incidencia is not _SIN_CAMBIO:
        if tipo_incidencia and tipo_incidencia not in ingest.TIPOS_INCIDENCIA:
            raise ErrorDeNegocio(f"Tipo de incidencia inválido: {tipo_incidencia}")
        nuevos["tipo_incidencia"] = tipo_incidencia or None
    if referencia_ubicacion is not _SIN_CAMBIO:
        nuevos["referencia_ubicacion"] = referencia_ubicacion or None
    cambios = {}
    for campo, nuevo in nuevos.items():
        anterior = getattr(r, campo)
        if anterior != nuevo:
            cambios[campo] = {"antes": getattr(anterior, "value", anterior), "despues": getattr(nuevo, "value", nuevo)}
            setattr(r, campo, nuevo)
            if campo not in r.campos_corregidos:
                r.campos_corregidos.append(campo)
    _recalcular_faltantes(r)
    r.confirmado_por = responsable
    _guardar_reporte(r)
    audit.registrar(responsable, "confirmar_reporte", "reporte", r.id, detalle={"cambios": cambios})
    return r


@requiere_admin
@operacion("rechazar_reporte")
def rechazar_reporte(reporte_id: int, responsable: str, motivo: str) -> Reporte:
    responsable = _resolver_responsable(responsable)
    if not (motivo or "").strip():
        raise ErrorDeNegocio("Indique el motivo del rechazo.")
    r = _obtener_reporte(reporte_id)
    _mover_reporte(r, EstadoReporte.RECHAZADO)
    r.motivo_rechazo = motivo.strip()
    _guardar_reporte(r)
    audit.registrar(responsable, "rechazar_reporte", "reporte", r.id, motivo=motivo)
    return r


# --------------------------------------------------------------- duplicados
@requiere_admin
def sugerir_duplicados(reporte_id: int) -> List[CandidatoDuplicado]:
    r = _obtener_reporte(reporte_id)
    with tracing.traza("geolocalizacion_dedup", "sugerir_duplicados", {"reporte_id": reporte_id},
                       correlation_id=f"reporte:{reporte_id}") as t:
        c = geoloc.sugerir_duplicados(r, _listar_reportes())
        t["output"] = {"candidatos": [(x.reporte_id, x.similitud) for x in c]}
    return c


@requiere_admin
@operacion("resolver_duplicado")
def resolver_duplicado(reporte_id: int, otro_id: int, es_duplicado: bool,
                       responsable: str, motivo: str = "") -> Reporte:
    """La persona decide. Si es duplicado, `reporte_id` queda ligado a `otro_id` y sale del cálculo;
    nada se fusiona ni se borra (ambos mensajes originales se conservan)."""
    responsable = _resolver_responsable(responsable)
    if reporte_id == otro_id:
        raise ErrorDeNegocio("Un reporte no puede ser duplicado de sí mismo.")
    r = _obtener_reporte(reporte_id)
    otro = _obtener_reporte(otro_id)
    if es_duplicado:
        if otro.estado in (EstadoReporte.DUPLICADO, EstadoReporte.RECHAZADO):
            raise ErrorDeNegocio(f"El reporte {otro_id} está '{otro.estado.value}': no puede ser el original.")
        _mover_reporte(r, EstadoReporte.DUPLICADO)
        r.duplicado_de = otro_id
        _guardar_reporte(r)
    db.insertar("decisiones_duplicado", {"reporte_id": reporte_id, "otro_id": otro_id,
                                         "es_duplicado": es_duplicado, "responsable": responsable,
                                         "fecha": datetime.now().isoformat(timespec="seconds")})
    audit.registrar(responsable, "duplicado_si" if es_duplicado else "duplicado_no", "reporte", reporte_id,
                    motivo=motivo, detalle={"otro_reporte": otro_id})
    return r


@requiere_admin
def decisiones_duplicado() -> List[Dict[str, Any]]:
    return db.listar("decisiones_duplicado")


# ---------------------------------------------------------------- prioridad
def _calcular_prioridades() -> List[PrioridadSector]:
    with tracing.traza("priorizacion", "calcular_prioridades") as t:
        p = prioritization.calcular_prioridades(_listar_reportes(), listar_sectores())
        t["output"] = [(x.sector, x.puntaje) for x in p[:8]]
    return p


@requiere_admin
def calcular_prioridades() -> List[PrioridadSector]:
    return _calcular_prioridades()


@requiere_admin
def explicar_prioridad_ia(sector: str) -> Dict[str, str]:
    """Resumen explicable de un puntaje ya calculado (Gemini redacta; el código valida). Informativo."""
    p = next((x for x in _calcular_prioridades() if x.sector == sector), None)
    if p is None:
        raise ErrorDeNegocio(f"El sector {sector} no tiene prioridad calculada.")
    return ia_tareas.explicar_prioridad(p)


@requiere_admin
def redactar_borrador_ia(plan_id: int, sector: str) -> Dict[str, str]:
    """Borrador de comunicación para un sector de un plan. NO se envía ni se guarda: lo revisa una persona."""
    plan = _obtener_plan(plan_id)
    items = [a for a in plan.asignaciones if a.sector == sector]
    if not items:
        raise ErrorDeNegocio(f"El plan {plan_id} no asigna cisternas al sector {sector}.")
    return ia_tareas.borrador_comunicacion(sector, sum(a.litros for a in items), sorted({a.cisterna_id for a in items}))


# ----------------------------------------------------------- visibilidad
ESTADOS_VISIBILIDAD = {
    "con_reportes_confirmados": "Hay reportes confirmados con datos clave: se prioriza.",
    "con_reportes_por_revisar": "Hay reportes sin confirmar: revisar antes de priorizar.",
    "sin_informacion_suficiente": "Hay reportes confirmados pero sin horas o personas: necesidad no cuantificada.",
    "sin_reportes_recientes": "Sin reportes recientes. NO significa que no haya necesidad.",
    "necesidad_no_evaluada": "Sin reportes ni antecedentes registrados: necesidad no evaluada.",
}


@requiere_admin
def visibilidad_sectores(ahora: Optional[datetime] = None) -> List[Dict[str, Any]]:
    return _visibilidad_sectores(ahora)


def _visibilidad_sectores(ahora: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Distingue 'sin reportes' de 'sin necesidad'. Nunca asigna prioridad crítica ni cero por ausencia de reportes."""
    ahora = ahora or datetime.now()
    limite = ahora - timedelta(hours=config.VENTANA_REPORTES_RECIENTES_HORAS)
    reps = _listar_reportes()
    salida = []
    for s in listar_sectores():
        propios = [r for r in reps if r.sector == s.nombre]
        confirmados = [r for r in propios if r.estado in (EstadoReporte.CONFIRMADO, EstadoReporte.EN_PLAN)]
        pendientes = [r for r in propios if r.estado == EstadoReporte.POR_REVISAR]
        recientes = [r for r in propios if r.fecha_creacion >= limite and r.estado != EstadoReporte.RECHAZADO]
        if confirmados:
            completos = any(r.horas_sin_agua is not None and r.personas_afectadas is not None for r in confirmados)
            estado = "con_reportes_confirmados" if completos else "sin_informacion_suficiente"
        elif pendientes:
            estado = "con_reportes_por_revisar"
        elif recientes:
            estado = "sin_informacion_suficiente"
        elif s.antecedentes_interrupciones is None:
            estado = "necesidad_no_evaluada"
        else:
            estado = "sin_reportes_recientes"
        verificar = estado in ("sin_reportes_recientes", "necesidad_no_evaluada") and (
            (s.antecedentes_interrupciones or 0) > 0 or s.vulnerabilidad.value in ("alta", "crítica"))
        salida.append({
            "sector": s.nombre, "estado": estado, "descripcion": ESTADOS_VISIBILIDAD[estado],
            "reportes_confirmados": len(confirmados), "reportes_por_revisar": len(pendientes),
            "vulnerabilidad": s.vulnerabilidad.value, "poblacion": s.poblacion_estimada,
            "antecedentes_interrupciones": s.antecedentes_interrupciones,
            "requiere_verificacion_proactiva": verificar,
            "fuente_datos": s.fuente_datos, "fecha_datos": s.fecha_datos,
        })
    return salida


# --------------------------------------------------------------------- plan
def _listar_planes() -> List[PropuestaPlan]:
    return [PropuestaPlan(**d) for d in db.listar("planes")]


@requiere_admin
def listar_planes() -> List[PropuestaPlan]:
    return _listar_planes()


def _obtener_plan(plan_id: int) -> PropuestaPlan:
    d = db.obtener("planes", plan_id)
    if d is None:
        raise ErrorDeNegocio(f"El plan {plan_id} no existe.")
    return PropuestaPlan(**d)


@requiere_admin
def obtener_plan(plan_id: int) -> PropuestaPlan:
    return _obtener_plan(plan_id)


def _guardar_plan(p: PropuestaPlan) -> None:
    db.actualizar("planes", p.id, p.model_dump(mode="json"))


def _resumen(asig: List[Asignacion], pend, prios: List[PrioridadSector], cist: List[Cisterna]) -> Dict[str, Any]:
    total_disp = sum(min(c.litros_disponibles, c.capacidad_litros) for c in cist if c.estado.value == "disponible")
    usado = sum(a.litros for a in asig)
    pend_set = {p.sector for p in pend}
    return {
        "sectores_con_prioridad": len(prios),
        "sectores_atendidos": len({a.sector for a in asig} - pend_set),
        "sectores_pendientes": sorted(pend_set),
        "litros_disponibles": total_disp, "litros_asignados": usado, "litros_sobrantes": total_disp - usado,
    }


def _guardar_derivados(plan: PropuestaPlan) -> None:
    plan.borradores_comunicacion = communication.redactar_borradores(plan.asignaciones, plan.pendientes)
    plan.resumen = _resumen(plan.asignaciones, plan.pendientes, plan.prioridades, listar_cisternas())


@requiere_admin
@operacion("generar_plan")
def generar_plan(responsable: str, metodo: str = "flujo") -> PropuestaPlan:
    """Calcula prioridades y propone asignaciones. NO aprueba ni envía nada."""
    responsable = _resolver_responsable(responsable)
    prios = _calcular_prioridades()
    if not prios:
        raise ErrorDeNegocio("No hay reportes confirmados. Confirme al menos un reporte primero.")
    cist = listar_cisternas()
    with tracing.traza("planificador", "proponer_asignaciones", {"sectores": len(prios), "cisternas": len(cist),
                                                                 "metodo": metodo}, tools=[f"planner.{metodo}"]) as t:
        asig, pend = planner.proponer_asignaciones(prios, cist, metodo=metodo)
        t["output"] = {"asignaciones": len(asig), "pendientes": len(pend)}
    plan = PropuestaPlan(id=0, fecha_creacion=datetime.now(), litros_por_persona=config.LITROS_POR_PERSONA,
                         metodo="flujo_maximo_lexicografico" if metodo == "flujo" else "greedy",
                         version_reglas=config.VERSION_REGLAS,
                         asignaciones=asig, pendientes=pend, prioridades=prios)
    _guardar_derivados(plan)
    pid = db.insertar("planes", plan.model_dump(mode="json"))
    plan.id = pid
    _guardar_plan(plan)
    tracing.correlacionar(f"plan:{pid}")
    audit.registrar(responsable, "generar_plan", "plan", pid,
                    detalle={"resumen": plan.resumen, "asignaciones": len(asig), "pendientes": len(pend),
                             "metodo": plan.metodo})
    return plan


@requiere_admin
@operacion("editar_plan")
def editar_plan(plan_id: int, nuevas_asignaciones: List[Asignacion], responsable: str, motivo: str) -> PropuestaPlan:
    """Modifica asignaciones de un plan 'propuesto'. Valida capacidad; registra antes/después."""
    responsable = _resolver_responsable(responsable)
    if not (motivo or "").strip():
        raise ErrorDeNegocio("Indique el motivo de la modificación.")
    plan = _obtener_plan(plan_id)
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
    _guardar_plan(plan)
    audit.registrar(responsable, "editar_plan", "plan", plan.id, motivo=motivo,
                    detalle={"antes": antes, "despues": despues, "version": plan.version})
    return plan


def _recalcular_pendientes(plan: PropuestaPlan) -> None:
    """Tras una edición manual, recalcula qué demanda queda sin cubrir (determinista)."""
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


@requiere_admin
@operacion("decidir_plan")
def decidir_plan(plan_id: int, accion: AccionDecision, responsable: str, motivo: str = "") -> PropuestaPlan:
    """Aprobar o rechazar. Rechazar exige motivo. Aprobar revalida capacidad. El estado solo avanza
    por TRANSICIONES_PLAN."""
    if accion == AccionDecision.EDITAR:
        raise ErrorDeNegocio("Para editar use editar_plan().")
    responsable = _resolver_responsable(responsable)
    plan = _obtener_plan(plan_id)
    if accion == AccionDecision.RECHAZAR:
        if not (motivo or "").strip():
            raise ErrorDeNegocio("Indique el motivo del rechazo.")
        _mover_plan(plan, EstadoPlan.RECHAZADO)
    else:
        _mover_plan(plan, EstadoPlan.APROBADO)
        errores = planner.validar_asignaciones(plan.asignaciones, listar_cisternas())
        if errores:
            raise ErrorDeNegocio("No se puede aprobar: " + " ".join(errores))
        if plan.editado and not (motivo or "").strip():
            raise ErrorDeNegocio("El plan fue modificado: indique el motivo/comentario de la aprobación.")
        atendidos = {a.sector for a in plan.asignaciones}
        for r in _listar_reportes():
            if r.estado == EstadoReporte.CONFIRMADO and r.sector in atendidos:
                _mover_reporte(r, EstadoReporte.EN_PLAN)
                _guardar_reporte(r)
    _guardar_plan(plan)
    dec = Decision(plan_id=plan.id, accion=accion, responsable=responsable, motivo=motivo or "")
    audit.registrar(responsable, f"{accion.value}_plan", "plan", plan.id, motivo=motivo or "",
                    detalle={"decision": dec.model_dump(mode="json"), "editado": plan.editado,
                             "version": plan.version})
    return plan


# ------------------------------------------------- contratos para dispositivos
def estado_actual() -> EstadoActual:
    """Lectura para dispositivos: sin borradores de comunicación ni textos de ciudadanos."""
    planes = _listar_planes()
    aprobados = [p for p in planes if p.estado == EstadoPlan.APROBADO]
    propuestos = [p for p in planes if p.estado == EstadoPlan.PROPUESTO]
    reps = _listar_reportes()
    activos = [r for r in reps if r.estado in (EstadoReporte.CONFIRMADO, EstadoReporte.POR_REVISAR)]
    por_revisar = sum(r.estado == EstadoReporte.POR_REVISAR for r in reps)

    def limpio(p):
        return p.model_copy(update={"borradores_comunicacion": []}) if p else None

    prios = [{"sector": p.sector, "puntaje": p.puntaje, "categoria": p.categoria}
             for p in prioritization.calcular_prioridades(reps, listar_sectores())[:5]]
    vis = _visibilidad_sectores()
    return EstadoActual(generado=datetime.now(), plan_aprobado=limpio(aprobados[-1] if aprobados else None),
                        plan_pendiente_de_revision=limpio(propuestos[-1] if propuestos else None),
                        reportes_activos=len(activos), reportes_por_revisar=por_revisar,
                        cisternas=listar_cisternas(), prioridades_top=prios,
                        sectores_sin_informacion=sum(v["estado"] in ("sin_informacion_suficiente", "necesidad_no_evaluada",
                                                                      "sin_reportes_recientes") for v in vis))


@operacion("confirmacion_dispositivo")
def registrar_confirmacion_dispositivo(c: ConfirmacionDispositivo) -> None:
    """Un dispositivo publica una confirmación; solo se AUDITA, no cambia planes ni cisternas."""
    plan = _obtener_plan(c.plan_id)
    if plan.estado != EstadoPlan.APROBADO:
        raise ErrorDeNegocio("Solo se aceptan confirmaciones sobre planes aprobados.")
    audit.registrar(f"dispositivo:{c.dispositivo_id}", f"confirmacion_{c.tipo}", "plan", c.plan_id,
                    detalle=c.model_dump(mode="json"))


# ------------------------------------------------------------ portal público (sin cuenta)
MENSAJE_CODIGO_INVALIDO = "No existe un reporte con ese código."

# Estados internos -> texto comprensible para el ciudadano. Nunca promete hora de llegada.
_ESTADO_PUBLICO = {
    EstadoReporte.POR_REVISAR: "Recibido, en revisión.",
    EstadoReporte.CONFIRMADO: "Confirmado, en evaluación.",
    EstadoReporte.EN_PLAN: "Atención programada, hora aún sin confirmar.",
    EstadoReporte.DUPLICADO: "Agrupado con otro reporte del mismo problema.",
    EstadoReporte.RECHAZADO: "No procede como reporte.",
}


def consultar_reporte_publico(codigo: str, origen: Optional[str] = None) -> Dict[str, Any]:
    """Consulta por código de seguimiento, sin cuenta. Devuelve SOLO estado comprensible, sector (si está
    confirmado) y fecha: jamás el texto original, datos extraídos, motivos, ids ni responsables.
    Código mal formado y código inexistente dan EXACTAMENTE el mismo error; los intentos se limitan por origen."""
    _limitar("consulta:" + (origen or "global"), _LIMITE_CONSULTAS)
    c = (codigo or "").strip().upper()
    r = None
    if _RE_CODIGO.fullmatch(c):
        r = next((x for x in _listar_reportes() if x.codigo_seguimiento == c), None)
    if r is None:
        raise ErrorDeNegocio(MENSAJE_CODIGO_INVALIDO)
    confirmado = r.estado in (EstadoReporte.CONFIRMADO, EstadoReporte.EN_PLAN)
    return {"codigo": c, "estado_publico": _ESTADO_PUBLICO[r.estado],
            "sector": r.sector if confirmado else None,
            "fecha_creacion": r.fecha_creacion.isoformat(timespec="minutes")}


def avisos_publicos() -> List[Dict[str, Any]]:
    """Avisos para el público: atención programada por sector (planes APROBADOS; sin litros, cisternas ni horas
    ni borradores) y conteo agregado de reportes confirmados en evaluación por sector (sin textos)."""
    avisos: List[Dict[str, Any]] = []
    programados = sorted({a.sector for p in _listar_planes() if p.estado == EstadoPlan.APROBADO
                          for a in p.asignaciones})
    for s in programados:
        avisos.append({"tipo": "atencion_programada", "sector": s,
                       "mensaje": f"{s}: atención programada, hora aún sin confirmar."})
    conteo: Dict[str, int] = {}
    for r in _listar_reportes():
        if r.estado == EstadoReporte.CONFIRMADO and r.sector:
            conteo[r.sector] = conteo.get(r.sector, 0) + 1
    for s in sorted(conteo):
        n = conteo[s]
        avisos.append({"tipo": "en_evaluacion", "sector": s, "reportes_en_evaluacion": n,
                       "mensaje": f"{s}: {n} reporte(s) confirmado(s) en evaluación."})
    return avisos
