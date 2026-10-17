"""Portal público: formulario sencillo de reporte. Muestra el código de seguimiento al registrarlo."""

import uuid

import flet as ft

from interface.flet_app import components as C
from interface.flet_app import theme as T
from services import workflow


def build(ctx) -> ft.Control:
    if ctx.envio_hecho:               # el formulario se reabre tras un envío exitoso: nueva clave de idempotencia
        ctx.clave_envio = uuid.uuid4().hex
        ctx.envio_hecho = False
    texto = ft.TextField(label="Cuéntenos qué está pasando", multiline=True, min_lines=4, max_lines=8, max_length=1500, border_radius=12,
                         hint_text="Ej.: En mi calle no tenemos agua desde ayer y somos varias familias", border_color="#cfdcec",
                         focused_border_color=T.BLUE, expand=True, tooltip="Describa el problema con sus palabras")
    comunidad = C.campo("Comunidad o sector (opcional)", expand=True, hint_text="Ej.: Barrio Colón", tooltip="Ayuda a ubicar su reporte")
    estado = ft.Row([], spacing=8)
    zona = ft.Container()
    envio = {"boton": None}

    def confirmacion(codigo) -> ft.Control:
        filas = [ft.Icon(ft.Icons.CHECK_CIRCLE, color=T.GREEN, size=44),
                 ft.Text("Su reporte quedó registrado", size=22, weight=ft.FontWeight.W_800, color=T.NAVY),
                 ft.Text("Gracias por avisar. Será revisado por el equipo.", size=14, color=T.MUTED)]
        if codigo:
            filas += [ft.Text("Su código de seguimiento", size=12, color=T.MUTED),
                      ft.Container(ft.Text(codigo, size=28, weight=ft.FontWeight.W_800, color=T.NAVY, selectable=True),
                                   bgcolor="#eaf4fc", border_radius=12, padding=ft.Padding.symmetric(horizontal=18, vertical=10)),
                      ft.Text("Guárdelo: lo necesitará para consultar el estado de su reporte.", size=13, color=T.INK)]
        filas.append(ft.Row([C.boton("Consultar mi reporte", lambda e: ctx.ir("consultar", codigo=codigo or ""), ft.Icons.SEARCH) if codigo else ft.Container(),
                             C.boton("Enviar otro reporte", lambda e: ctx.ir("reportar"), ft.Icons.ADD, "secundario")], spacing=12, wrap=True))
        return C.panel(ft.Column(filas, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START))

    def enviar(e):
        valor = (texto.value or "").strip()
        if not valor:
            texto.error_text = "Escriba qué está pasando para poder enviar el reporte."
            ctx.actualizar()
            return
        texto.error_text = None
        sector = (comunidad.value or "").strip()
        completo = f"{valor}\nComunidad o sector: {sector}" if sector else valor
        envio["boton"].disabled = True
        estado.controls = [C.cargando("Enviando su reporte…")]
        ctx.actualizar()
        ok, rep = ctx.ejecutar(lambda: workflow.crear_reporte(completo, ctx.responsable, canal="portal", clave_idempotencia=ctx.clave_envio),
                               publico=True)
        envio["boton"].disabled = False
        estado.controls = []
        if ok:
            ctx.envio_hecho = True
            zona.content = confirmacion(getattr(rep, "codigo_seguimiento", None))
        else:
            estado.controls = [C.nota("No pudimos registrar su reporte. Revise el texto e intente de nuevo.", "bad")]
        ctx.actualizar()

    envio["boton"] = C.boton("Enviar reporte", enviar, ft.Icons.SEND, tooltip="Enviar el reporte")
    formulario = C.panel(ft.Column([ft.Row([texto]), ft.Row([comunidad]), ft.Row([envio["boton"], estado], spacing=14, wrap=True),
                                    ft.Text("No escriba contraseñas ni datos bancarios. Si es una emergencia, llame al 911.", size=12, color=T.MUTED)], spacing=12),
                         "Reportar falta de agua")
    zona.content = formulario
    return C.seccion(C.titulo("Reportar falta de agua", "Es rápido y no necesita crear una cuenta"), zona)
