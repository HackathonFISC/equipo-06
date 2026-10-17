"""Métricas operativas: indicadores, estado de reportes y planes, prioridades, mapa esquemático, integridad y sectores sin información."""

import flet as ft

import config
from interface.flet_app import components as C
from interface.flet_app import theme as T
from models.schemas import EstadoPlan, EstadoReporte
from services import audit, tracing, workflow


def _mapa(sectores, prios) -> ft.Control:
    """Mapa ESQUEMÁTICO (no cartográfico) con las coordenadas del catálogo; color según la prioridad calculada."""
    con_coord = [s for s in sectores if s.lat is not None and s.lng is not None]
    if not con_coord:
        return C.vacio("Los sectores no tienen coordenadas.")
    ancho, alto = 560, 300
    lat0, lat1 = min(s.lat for s in con_coord), max(s.lat for s in con_coord)
    lng0, lng1 = min(s.lng for s in con_coord), max(s.lng for s in con_coord)
    cat = {p.sector: p for p in prios}
    hijos = [ft.Container(width=ancho, height=alto, bgcolor="#eaf4fc", border_radius=14)]
    for s in con_coord:
        x = 24 + (s.lng - lng0) / ((lng1 - lng0) or 1) * (ancho - 110)
        y = 18 + (lat1 - s.lat) / ((lat1 - lat0) or 1) * (alto - 52)
        p = cat.get(s.nombre)
        color = T.CATEGORIA_COLOR.get(p.categoria, T.BLUE) if p else "#9fb0c6"
        hijos.append(ft.Container(width=14, height=14, left=x, top=y, bgcolor=color, border_radius=999,
                                  border=ft.Border.all(2, T.WHITE), tooltip=f"{s.nombre}" + (f" · {p.puntaje} pts" if p else " · sin prioridad")))
        hijos.append(ft.Text(s.nombre, size=9.5, color=T.INK, left=x + 16, top=y - 1))
    leyenda = ft.Row([C.pill("crítica", "bad"), C.pill("alta", "warn"), C.pill("media", "info"), C.pill("baja", "ok"),
                      C.pill("sin prioridad", "neutro")], spacing=6, wrap=True)
    return ft.Column([ft.Stack(hijos, width=ancho, height=alto), leyenda,
                      ft.Text("Mapa esquemático con coordenadas ficticias del catálogo; no es un mapa real.", size=11, color=T.MUTED)],
                     spacing=8)


def build(ctx) -> ft.Control:
    reps, planes = workflow.listar_reportes(), workflow.listar_planes()
    sectores = workflow.listar_sectores()
    cont = {e: sum(r.estado == e for r in reps) for e in EstadoReporte}
    prios = workflow.calcular_prioridades()
    vis = workflow.visibilidad_sectores()
    sin_info = [v for v in vis if v["estado"] in ("sin_informacion_suficiente", "sin_reportes_recientes", "necesidad_no_evaluada")]
    aprobados = sum(p.estado == EstadoPlan.APROBADO for p in planes)
    propuestos = sum(p.estado == EstadoPlan.PROPUESTO for p in planes)

    kpis = ft.Row([
        C.kpi(len(reps), "Reportes totales", ft.Icons.INBOX),
        C.kpi(cont[EstadoReporte.POR_REVISAR], "Por revisar", ft.Icons.FACT_CHECK, "warn" if cont[EstadoReporte.POR_REVISAR] else ""),
        C.kpi(cont[EstadoReporte.CONFIRMADO] + cont[EstadoReporte.EN_PLAN], "Confirmados", ft.Icons.CHECK_CIRCLE, "ok"),
        C.kpi(len(prios), "Sectores priorizados", ft.Icons.INSIGHTS),
        C.kpi(len(sin_info), "Sectores sin información", ft.Icons.VISIBILITY, "warn" if sin_info else ""),
    ], spacing=12, wrap=True, run_spacing=12)

    pasos = ft.Row([ft.Container(ft.Column([ft.Text(str(v), size=18, weight=ft.FontWeight.W_800, color=T.NAVY if not fut else T.MUTED),
                                            ft.Text(n, size=11, color=T.MUTED)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                                 bgcolor="#f4f4f4" if fut else "#eaf4fc", border=ft.Border.all(1, T.LINE), border_radius=10,
                                 padding=ft.Padding.symmetric(horizontal=12, vertical=8), width=118)
                    for n, v, fut in [("Por revisar", cont[EstadoReporte.POR_REVISAR], False), ("Confirmados", cont[EstadoReporte.CONFIRMADO], False),
                                      ("Duplicados", cont[EstadoReporte.DUPLICADO], False), ("Priorizados", len(prios), False),
                                      ("Planes propuestos", propuestos, False), ("Planes aprobados", aprobados, False),
                                      ("Dispositivos (futuro)", "—", True)]], spacing=8, wrap=True, run_spacing=8)

    if cont[EstadoReporte.POR_REVISAR]:
        siguiente = C.boton(f"Revisar {cont[EstadoReporte.POR_REVISAR]} reportes pendientes", lambda e: ctx.ir("revision"), ft.Icons.FACT_CHECK, "secundario")
    elif prios and not planes:
        siguiente = C.boton("Generar propuesta de plan", lambda e: ctx.ir("plan"), ft.Icons.LOCAL_SHIPPING, "secundario")
    else:
        siguiente = ft.Container()

    top = ft.Column([ft.Row([ft.Container(ft.Text(f"{i + 1}", size=12, color=T.WHITE, weight=ft.FontWeight.W_800),
                                          bgcolor=T.CATEGORIA_COLOR.get(p.categoria, T.BLUE), width=24, height=24, border_radius=999,
                                          alignment=ft.Alignment.CENTER),
                             ft.Column([ft.Text(p.sector, size=14, weight=ft.FontWeight.W_700, color=T.NAVY),
                                        ft.Text(f"{p.horas_sin_agua or '?'} h · {p.personas_afectadas or '?'} personas · {p.reportes_contados} reporte(s)",
                                                size=11.5, color=T.MUTED)], spacing=0, expand=True),
                             ft.Text(f"{p.puntaje}", size=15, weight=ft.FontWeight.W_800, color=T.NAVY), C.pill_estado(p.categoria)],
                            spacing=10) for i, p in enumerate(prios[:6])], spacing=10) if prios else C.vacio("Aún no hay reportes confirmados.")

    integridad = ft.Column([
        ft.Row([ft.Text("Auditoría", size=13), C.pill_estado("ok" if audit.verificar_integridad() else "error")], spacing=8),
        ft.Row([ft.Text(f"Trazas ({tracing.verificar_integridad()['eventos']} eventos)", size=13),
                C.pill_estado("ok" if tracing.verificar_integridad()["integra"] else "error")], spacing=8),
        ft.Row([ft.Text("Proveedor de IA", size=13), C.pill("Gemini" if config.ai_provider() == "gemini" else "Local (reglas)",
                                                          "info" if config.ai_provider() == "gemini" else "neutro")], spacing=8)], spacing=6)

    info = ft.Column([ft.Text("Sin reportes ≠ sin necesidad: estos sectores no reciben prioridad automática ni cero.", size=11.5, color=T.MUTED),
                      *[ft.Row([ft.Text(v["sector"], size=12.5, expand=True), C.pill("verificar" if v["requiere_verificacion_proactiva"] else v["estado"].replace("_", " "),
                                                                                   "warn" if v["requiere_verificacion_proactiva"] else "neutro")]) for v in sin_info[:7]]],
                     spacing=5)

    return C.seccion(
        C.titulo("Métricas operativas", "Estado de reportes, planes y prioridades"),
        ft.Row([ft.Container(), C.ficticio()] if any(s.ficticio for s in sectores) else [ft.Container()], alignment=ft.MainAxisAlignment.END),
        kpis,
        C.panel(ft.Column([pasos, siguiente], spacing=10), "Recorrido operativo"),
        ft.ResponsiveRow([
            ft.Container(C.panel(top, "Prioridades actuales"), col={"xs": 12, "lg": 7}),
            ft.Container(C.panel(_mapa(sectores, prios), "Mapa de sectores"), col={"xs": 12, "lg": 5})], run_spacing=14),
        ft.ResponsiveRow([
            ft.Container(C.panel(integridad, "Integridad y proveedor"), col={"xs": 12, "md": 5}),
            ft.Container(C.panel(info, "Sectores sin información"), col={"xs": 12, "md": 7})], run_spacing=14))
