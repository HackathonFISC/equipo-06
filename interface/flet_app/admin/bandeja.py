"""Bandeja de reportes: recibir un reporte nuevo (con idempotencia) y listar/filtrar los existentes."""

import uuid

import flet as ft

from interface.flet_app import components as C
from interface.flet_app import theme as T
from models.schemas import EstadoReporte
from services import workflow


def build(ctx) -> ft.Control:
    reps = workflow.listar_reportes()
    texto = ft.TextField(label="Reporte ciudadano (texto tal como llegó)", multiline=True, min_lines=3, max_lines=6,
                         hint_text="Ej.: En Vista Alegre no tenemos agua desde ayer", border_radius=12,
                         border_color="#cfdcec", focused_border_color=T.BLUE, expand=True)
    estado_envio = ft.Row([], spacing=8)
    boton_envio = None

    def enviar(e):
        valor = (texto.value or "").strip()
        if not valor:
            texto.error_text = "El texto del reporte no puede estar vacío."
            ctx.actualizar()
            return
        texto.error_text = None
        boton_envio.disabled = True
        estado_envio.controls = [C.cargando("Guardando e interpretando…")]
        ctx.actualizar()
        ok, rep = ctx.ejecutar(lambda: workflow.crear_reporte(valor, ctx.responsable, clave_idempotencia=ctx.clave_envio))
        boton_envio.disabled = False
        estado_envio.controls = []
        if ok:
            ctx.clave_envio = uuid.uuid4().hex
            ctx.toast(f"Reporte #{rep.id} guardado ({rep.interprete}). Revíselo y confírmelo.")
            ctx.ir("revision", reporte_id=rep.id)
        else:
            ctx.actualizar()

    boton_envio = C.boton("Recibir reporte", enviar, ft.Icons.ADD)
    nuevo = C.panel(ft.Column([ft.Row([texto]), ft.Row([boton_envio, estado_envio], spacing=14),
                               ft.Text("Ejemplos: «Se rompió una tubería cerca de la escuela» · «En mi casa llevamos tres días sin agua y somos seis» · "
                                       "«Ya reporté el problema, pero todavía no tenemos agua»", size=11.5, color=T.MUTED)], spacing=10),
                    "Nuevo reporte")

    f_estado = C.lista_desplegable("Estado", ["(todos)"] + [e.value for e in EstadoReporte], "(todos)", width=190)
    f_sector = C.lista_desplegable("Sector", ["(todos)"] + sorted({r.sector for r in reps if r.sector}), "(todos)", width=210)
    f_inc = ft.Switch(label="Solo con faltantes/inciertos", value=False)
    lista = ft.Column([], spacing=0)

    def pintar(e=None):
        filas = []
        for r in reversed(reps):
            if f_estado.value not in (None, "(todos)") and r.estado.value != f_estado.value:
                continue
            if f_sector.value not in (None, "(todos)") and r.sector != f_sector.value:
                continue
            if f_inc.value and not (r.datos_faltantes or r.datos_inciertos):
                continue
            filas.append([f"#{r.id}", C.pill_estado(r.estado.value), r.sector or "—", r.horas_sin_agua if r.horas_sin_agua is not None else "—",
                          r.personas_afectadas if r.personas_afectadas is not None else "—",
                          r.severidad.value if r.severidad else "—", ", ".join(r.datos_faltantes) or "—",
                          r.interprete, ft.Text((r.mensaje_original[:70] + "…") if len(r.mensaje_original) > 70 else r.mensaje_original, size=12, width=330),
                          ft.IconButton(icon=ft.Icons.EDIT, tooltip="Abrir en revisión", icon_color=T.BLUE,
                                        on_click=lambda e, rid=r.id: ctx.ir("revision", reporte_id=rid))])
        lista.controls = [C.tabla(["ID", "Estado", "Sector", "Horas", "Personas", "Severidad", "Faltantes", "Intérprete", "Mensaje", ""], filas),
                          ft.Text(f"{len(filas)} reportes · el mensaje original nunca se modifica. "
                                  f"{'Datos ficticios marcados en cada reporte de demo.' if any(r.ficticio for r in reps) else ''}",
                                  size=11.5, color=T.MUTED)]
        ctx.actualizar() if e is not None else None

    for ctl in (f_estado, f_sector):
        ctl.on_select = pintar
    f_inc.on_change = pintar
    pintar()
    return C.seccion(C.titulo("Bandeja de reportes", "Recibir, filtrar y abrir reportes ciudadanos"), nuevo,
                     C.panel(ft.Column([ft.Row([f_estado, f_sector, f_inc], spacing=12, wrap=True), lista], spacing=12), "Reportes"))
