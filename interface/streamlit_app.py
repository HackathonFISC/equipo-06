"""
Interfaz Streamlit de Agua Clara AI (solo presentación).
Toda la lógica vive en services.workflow; aquí no se calcula nada.
"""

import streamlit as st

import config
from models.schemas import AccionDecision, Asignacion, EstadoPlan, EstadoReporte, Severidad
from services import audit, geoloc, workflow
from services.workflow import ErrorDeNegocio

SEVERIDADES = ["(sin dato)"] + [s.value for s in Severidad]
ETIQUETA_ESTADO = {
    "por_revisar": "🟡 por revisar", "confirmado": "🟢 confirmado", "duplicado": "🔁 duplicado",
    "en_plan": "📦 en plan", "rechazado": "⛔ rechazado",
}


def _flash(tipo: str, msg: str) -> None:
    st.session_state["flash"] = (tipo, msg)


def _mostrar_flash() -> None:
    f = st.session_state.pop("flash", None)
    if f:
        getattr(st, f[0])(f[1])


def _intentar(fn, ok_msg: str) -> bool:
    try:
        fn()
    except ErrorDeNegocio as e:
        st.error(str(e))
        return False
    _flash("success", ok_msg)
    st.rerun()
    return True


def _fmt_reporte(r) -> str:
    return f"#{r.id} · {r.sector or 'SIN SECTOR'} · {ETIQUETA_ESTADO[r.estado.value]} · {r.mensaje_original[:50]}…"


# ====================================================================== main
def main() -> None:
    st.set_page_config(page_title=config.APP_NAME, page_icon="💧", layout="wide")
    st.title("💧 Agua Clara AI")
    st.caption(f"v{config.APP_VERSION} · Modo demostración local: sin internet, sin IA externa, sin hardware · "
               "**DATOS FICTICIOS**")

    with st.sidebar:
        st.header("Responsable")
        st.session_state["responsable"] = st.text_input(
            "Nombre de quien opera", value=st.session_state.get("responsable", "supervisor_demo"))
        st.divider()
        if st.button("📥 Cargar / reiniciar datos de ejemplo", use_container_width=True):
            n = workflow.cargar_datos_demo(st.session_state["responsable"])
            _flash("success", f"Datos ficticios cargados: {n['reportes']} reportes, {n['cisternas']} cisternas, "
                              f"{n['sectores']} sectores. Reportes en 'por revisar'.")
            st.rerun()
        st.caption("Reinicia la base local (borra reportes, planes y auditoría).")
        reps = workflow.listar_reportes()
        st.divider()
        st.metric("Reportes", len(reps))
        st.metric("Por revisar", sum(r.estado == EstadoReporte.POR_REVISAR for r in reps))
        st.metric("Confirmados", sum(r.estado == EstadoReporte.CONFIRMADO for r in reps))

    _mostrar_flash()

    if not workflow.listar_sectores():
        st.info("👈 Empiece cargando los datos de ejemplo desde la barra lateral.")
        return

    t1, t2, t3, t4, t5, t6 = st.tabs([
        "1 · Reporte", "2 · Revisar datos", "3 · Ubicación y duplicados",
        "4 · Prioridad", "5 · Plan y aprobación", "6 · Auditoría"])
    with t1:
        tab_reporte()
    with t2:
        tab_revisar()
    with t3:
        tab_duplicados()
    with t4:
        tab_prioridad()
    with t5:
        tab_plan()
    with t6:
        tab_auditoria()


# ================================================================ pestañas
def tab_reporte() -> None:
    st.subheader("Ingresar un reporte")
    st.write("Escriba o pegue el mensaje tal como llegó. El sistema propone campos; usted los revisa en el paso 2.")
    with st.form("nuevo_reporte", clear_on_submit=True):
        texto = st.text_area("Mensaje original", height=110,
                             placeholder="Ej.: Llevamos 2 días sin agua en Chame, calle 5. Unas 30 familias.")
        enviar = st.form_submit_button("Procesar reporte")
    if enviar:
        try:
            r = workflow.crear_reporte(texto, st.session_state["responsable"])
        except ErrorDeNegocio as e:
            st.error(str(e))
        else:
            _flash("success", f"Reporte #{r.id} creado. Pase a «2 · Revisar datos» para confirmarlo.")
            st.rerun()
    st.markdown("**Reportes cargados**")
    reps = workflow.listar_reportes()
    st.dataframe([{
        "id": r.id, "estado": r.estado.value, "sector": r.sector, "horas": r.horas_sin_agua,
        "personas": r.personas_afectadas, "severidad": r.severidad.value if r.severidad else None,
        "faltantes": ", ".join(r.datos_faltantes), "mensaje": r.mensaje_original} for r in reps],
        use_container_width=True, hide_index=True)


def tab_revisar() -> None:
    st.subheader("Revisar y corregir lo que entendió el sistema")
    reps = [r for r in workflow.listar_reportes() if r.estado in (EstadoReporte.POR_REVISAR, EstadoReporte.CONFIRMADO)]
    if not reps:
        st.info("No hay reportes por revisar.")
        return
    pendientes = [r for r in reps if r.estado == EstadoReporte.POR_REVISAR]
    st.caption(f"{len(pendientes)} por revisar · {len(reps) - len(pendientes)} ya confirmados")
    r = st.selectbox("Reporte", reps, format_func=_fmt_reporte, key="sel_revisar")

    izq, der = st.columns(2)
    with izq:
        st.markdown("**Texto original (no se modifica)**")
        st.info(r.mensaje_original)
        if r.datos_faltantes:
            st.error("Faltan: " + ", ".join(r.datos_faltantes))
        if r.datos_inciertos:
            st.warning("Inciertos: " + ", ".join(r.datos_inciertos))
        for n in r.notas:
            st.caption("• " + n)
    with der:
        catalogo = [s.nombre for s in workflow.listar_sectores()]
        with st.form(f"form_rev_{r.id}_{r.estado.value}"):
            sector = st.selectbox("Sector (catálogo)", ["(elegir)"] + catalogo,
                                  index=catalogo.index(r.sector) + 1 if r.sector in catalogo else 0)
            c1, c2 = st.columns(2)
            horas = c1.number_input("Horas sin agua (0 = desconocido)", min_value=0.0, step=1.0,
                                    value=float(r.horas_sin_agua or 0))
            personas = c2.number_input("Personas afectadas (0 = desconocido)", min_value=0, step=5,
                                       value=int(r.personas_afectadas or 0))
            sev = st.selectbox("Severidad", SEVERIDADES,
                               index=SEVERIDADES.index(r.severidad.value) if r.severidad else 0)
            calle = st.text_input("Calle / referencia", value=r.calle or "")
            ok = st.form_submit_button("✔ Confirmar datos y ubicación" if r.estado == EstadoReporte.POR_REVISAR
                                       else "Guardar correcciones")
        if ok:
            _intentar(lambda: workflow.corregir_y_confirmar(
                r.id, st.session_state["responsable"], None if sector == "(elegir)" else sector,
                horas or None, personas or None, None if sev == SEVERIDADES[0] else sev, calle.strip() or None),
                f"Reporte #{r.id} confirmado. Revise duplicados en el paso 3.")
        with st.expander("Rechazar este reporte"):
            motivo = st.text_input("Motivo", key=f"mrech_{r.id}")
            if st.button("Rechazar reporte", key=f"rech_{r.id}"):
                _intentar(lambda: workflow.rechazar_reporte(r.id, st.session_state["responsable"], motivo),
                          f"Reporte #{r.id} rechazado.")


def tab_duplicados() -> None:
    st.subheader("Ubicación sugerida y posibles duplicados")
    st.caption("El sistema solo SUGIERE. Nada se fusiona sin su decisión.")
    reps = [r for r in workflow.listar_reportes() if r.estado in (EstadoReporte.POR_REVISAR, EstadoReporte.CONFIRMADO)]
    if not reps:
        st.info("No hay reportes activos.")
        return
    r = st.selectbox("Reporte", reps, format_func=_fmt_reporte, key="sel_dup")
    sec = geoloc.resolver_sector(r.sector, workflow.listar_sectores())
    if sec:
        c1, c2, c3 = st.columns(3)
        c1.metric("Sector", sec.nombre)
        c2.metric("Población estimada", f"{sec.poblacion_estimada:,}".replace(",", " "))
        c3.metric("Vulnerabilidad", sec.vulnerabilidad.value)
        if sec.lat is not None:
            st.map([{"lat": sec.lat, "lon": sec.lng}], zoom=9, size=300)
        if r.estado == EstadoReporte.POR_REVISAR:
            st.warning("Ubicación aún sin confirmar (paso 2).")
    else:
        st.error("Este reporte no tiene sector reconocido. Corríjalo en el paso 2.")
        return

    cands = workflow.sugerir_duplicados(r.id)
    if not cands:
        st.success("Sin posibles duplicados con el umbral actual.")
    for c in cands:
        otro = workflow.obtener_reporte(c.reporte_id)
        with st.container(border=True):
            st.markdown(f"**Posible duplicado de #{otro.id}** · similitud {c.similitud:.0%} · ⚠️ dudoso")
            st.write("Motivos: " + "; ".join(c.motivos))
            st.caption(f"Este reporte: {r.mensaje_original}")
            st.caption(f"#{otro.id}: {otro.mensaje_original}")
            motivo = st.text_input("Comentario (opcional)", key=f"dm_{r.id}_{otro.id}")
            b1, b2 = st.columns(2)
            if b1.button("Sí, es duplicado (excluir de prioridad)", key=f"ds_{r.id}_{otro.id}"):
                _intentar(lambda: workflow.resolver_duplicado(r.id, otro.id, True, st.session_state["responsable"], motivo),
                          f"#{r.id} marcado como duplicado de #{otro.id}.")
            if b2.button("No, son casos distintos", key=f"dn_{r.id}_{otro.id}"):
                _intentar(lambda: workflow.resolver_duplicado(r.id, otro.id, False, st.session_state["responsable"], motivo),
                          "Decisión registrada: no son duplicados.")
    if r.duplicado_de:
        st.info(f"Este reporte fue marcado como duplicado de #{r.duplicado_de}.")


def tab_prioridad() -> None:
    st.subheader("Prioridad por sector")
    st.caption("Fórmula determinista: 40 % horas sin agua + 30 % población afectada + 30 % vulnerabilidad. "
               "El número de quejas NO suma puntos (por sector se usa el máximo). Solo cuentan reportes confirmados.")
    prios = workflow.calcular_prioridades()
    if not prios:
        st.info("Aún no hay reportes confirmados.")
        return
    st.dataframe([{
        "sector": p.sector, "puntaje": p.puntaje, "categoría": p.categoria, "horas": p.horas_sin_agua,
        "personas": p.personas_afectadas, "reportes": p.reportes_contados} for p in prios],
        use_container_width=True, hide_index=True)
    for p in prios:
        with st.expander(f"{p.sector} — {p.puntaje} pts ({p.categoria})"):
            st.dataframe([{"factor": f.nombre, "dato": f.valor, "normalizado": f.normalizado,
                           "peso": f.peso, "puntos": f.contribucion, "explicación": f.explicacion}
                          for f in p.factores], use_container_width=True, hide_index=True)
            for razon in p.razones:
                st.write("• " + razon)
            st.caption(f"Reportes considerados: {p.reportes_ids}")


def tab_plan() -> None:
    st.subheader("Plan de asignación de cisternas")
    cist = workflow.listar_cisternas()
    st.dataframe([{"cisterna": c.id, "estado": c.estado.value, "capacidad L": c.capacidad_litros,
                   "disponible L": c.litros_disponibles, "sede": c.sector_base} for c in cist],
                 use_container_width=True, hide_index=True)

    if st.button("⚙️ Generar propuesta de plan"):
        _intentar(lambda: workflow.generar_plan(st.session_state["responsable"]),
                  "Propuesta generada. Revísela abajo: aún NO está aprobada.")

    planes = workflow.listar_planes()
    if not planes:
        st.info("Genere una propuesta cuando tenga reportes confirmados.")
        return
    plan = st.selectbox("Plan", list(reversed(planes)), key="sel_plan",
                        format_func=lambda p: f"Plan #{p.id} · {p.estado.value} · v{p.version}"
                                              f"{' · editado' if p.editado else ''}")
    icono = {"propuesto": "🟡", "aprobado": "🟢", "rechazado": "⛔"}[plan.estado.value]
    st.markdown(f"### {icono} Plan #{plan.id} — {plan.estado.value}")
    rs = plan.resumen
    c1, c2, c3 = st.columns(3)
    c1.metric("Litros disponibles", rs.get("litros_disponibles"))
    c2.metric("Litros asignados", rs.get("litros_asignados"))
    c3.metric("Sectores pendientes", len(rs.get("sectores_pendientes", [])))
    st.caption(f"Estimación de demanda: {plan.litros_por_persona} L por persona (valor de demo). "
               "El plan no incluye horas de llegada.")

    st.markdown("**Asignaciones**")
    editable = plan.estado == EstadoPlan.PROPUESTO
    ids = [c.id for c in cist]
    editado = st.data_editor(
        [{"sector": a.sector, "cisterna": a.cisterna_id, "litros": a.litros, "prioridad": a.prioridad,
          "nota": a.nota} for a in plan.asignaciones],
        key=f"ed_{plan.id}_{plan.version}", hide_index=True, use_container_width=True,
        disabled=(not editable) or ["sector", "prioridad", "nota"],
        column_config={"cisterna": st.column_config.SelectboxColumn(options=ids, required=True),
                       "litros": st.column_config.NumberColumn(min_value=0, step=100,
                                                               help="0 = quitar esta asignación")})
    st.markdown("**Pendientes (no cubiertos)**")
    if plan.pendientes:
        st.dataframe([{"sector": p.sector, "prioridad": p.prioridad, "requeridos L": p.litros_requeridos,
                       "cubiertos L": p.litros_cubiertos, "faltan L": p.litros_faltantes, "motivo": p.motivo}
                      for p in plan.pendientes], use_container_width=True, hide_index=True)
    else:
        st.success("Todos los sectores quedan cubiertos.")

    with st.expander("✉️ Borradores de comunicación (no se envían)"):
        for b in plan.borradores_comunicacion:
            st.markdown(f"**{b['sector']}** · {b['tipo']}")
            st.text(b["texto"])

    if plan.estado != EstadoPlan.PROPUESTO:
        return
    st.divider()
    st.markdown("#### Supervisión humana")
    motivo = st.text_area("Motivo / comentario", key=f"mot_{plan.id}",
                          help="Obligatorio para rechazar, para guardar modificaciones y para aprobar un plan editado.")
    b1, b2, b3 = st.columns(3)
    if b1.button("💾 Guardar modificaciones", key=f"ed_btn_{plan.id}"):
        nuevas = [Asignacion(sector=f["sector"], cisterna_id=f["cisterna"], litros=int(f["litros"]),
                             prioridad=f["prioridad"], nota=f.get("nota") or "")
                  for f in editado.to_dict("records") if int(f["litros"]) > 0] if hasattr(editado, "to_dict") \
            else [Asignacion(sector=f["sector"], cisterna_id=f["cisterna"], litros=int(f["litros"]),
                             prioridad=f["prioridad"], nota=f.get("nota") or "")
                  for f in editado if int(f["litros"]) > 0]
        _intentar(lambda: workflow.editar_plan(plan.id, nuevas, st.session_state["responsable"], motivo),
                  "Modificaciones guardadas y auditadas.")
    if b2.button("✅ Aprobar plan", type="primary", key=f"ap_{plan.id}"):
        _intentar(lambda: workflow.decidir_plan(plan.id, AccionDecision.APROBAR, st.session_state["responsable"], motivo),
                  "Plan aprobado y registrado en auditoría. Nada se ha enviado.")
    if b3.button("⛔ Rechazar plan", key=f"re_{plan.id}"):
        _intentar(lambda: workflow.decidir_plan(plan.id, AccionDecision.RECHAZAR, st.session_state["responsable"], motivo),
                  "Plan rechazado y registrado en auditoría.")


def tab_auditoria() -> None:
    st.subheader("Auditoría")
    ok = audit.verificar_integridad()
    (st.success if ok else st.error)("Cadena de hashes íntegra ✔" if ok else "¡La cadena de auditoría fue alterada!")
    entradas = audit.listar()
    c1, c2 = st.columns(2)
    ent = c1.selectbox("Entidad", ["(todas)", "plan", "reporte", "sistema"])
    eid = c2.text_input("Id de entidad (opcional)")
    if ent != "(todas)":
        entradas = [e for e in entradas if e.entidad == ent]
    if eid.strip():
        entradas = [e for e in entradas if e.entidad_id == eid.strip()]
    st.dataframe([{"#": e.id, "fecha": e.fecha, "responsable": e.responsable, "acción": e.accion,
                   "entidad": f"{e.entidad} {e.entidad_id}", "motivo": e.motivo} for e in reversed(entradas)],
                 use_container_width=True, hide_index=True)
    if entradas:
        sel = st.selectbox("Ver detalle (cambios antes/después, extracción…)", list(reversed(entradas)),
                           format_func=lambda e: f"#{e.id} {e.accion} · {e.entidad} {e.entidad_id} · {e.responsable}")
        st.json(sel.detalle)
        st.caption(f"hash {sel.hash[:16]}… · previo {sel.hash_previo[:16]}…")
