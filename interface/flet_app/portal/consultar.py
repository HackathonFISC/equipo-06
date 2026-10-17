"""Portal público: consulta del estado de un reporte con su código de seguimiento (solo consultar_reporte_publico)."""

import re

import flet as ft

from interface.flet_app import components as C
from interface.flet_app import theme as T
from interface.flet_app.portal import datos
from services import workflow


def _resultado(d: dict) -> ft.Control:
    filas = [("Código", d.get("codigo")), ("Estado", d.get("estado_publico")), ("Sector", d.get("sector")),
             ("Recibido", datos.fecha_legible(d.get("fecha_creacion")))]
    if "tiene_ubicacion" in d:       # solo si el servidor lo informa; nunca se muestran coordenadas ni fotos
        filas.append(("Ubicación", "Marcada en el mapa" if d.get("tiene_ubicacion") else "Sin ubicación en el mapa"))
    if "n_fotos" in d:
        n = int(d.get("n_fotos") or 0)
        filas.append(("Fotos", "Sin fotos" if n == 0 else f"{n} foto{'s' if n != 1 else ''} recibida{'s' if n != 1 else ''}"))
    cuerpo = [ft.Row([ft.Text(k, size=12.5, color=T.MUTED, width=90),
                      ft.Text(str(v), size=15, weight=ft.FontWeight.W_700 if k == "Estado" else ft.FontWeight.W_400,
                              color=T.NAVY if k == "Estado" else T.INK, selectable=True, expand=True)], spacing=10)
              for k, v in filas if v]
    return C.panel(ft.Column(cuerpo, spacing=8), "Estado de su reporte")


def build(ctx) -> ft.Control:
    codigo = C.campo("Código de seguimiento", ctx.seleccion.pop("codigo", ""), hint_text="HID-XXXXXXXX", expand=True,
                     tooltip="Es el código que recibió al enviar su reporte", autofocus=True)
    salida = ft.Column([], spacing=10)
    b = {}

    def consultar(e=None):
        valor = re.sub(r"\s+", "", codigo.value or "").upper()
        if not valor:
            codigo.error_text = "Escriba su código de seguimiento."
            ctx.actualizar()
            return
        codigo.error_text = None
        b["x"].disabled = True
        salida.controls = [C.cargando("Buscando su reporte…")]
        ctx.actualizar()
        ok, res = ctx.ejecutar(lambda: workflow.consultar_reporte_publico(valor), publico=True)
        b["x"].disabled = False
        if ok and isinstance(res, dict) and res:
            salida.controls = [_resultado(res)]
        else:
            salida.controls = [C.nota("No encontramos un reporte con ese código. Revise que esté bien escrito (por ejemplo HID-ABC12345).", "warn")]
        ctx.actualizar()

    codigo.on_submit = consultar
    b["x"] = C.boton("Consultar", consultar, ft.Icons.SEARCH, tooltip="Consultar el estado")
    if codigo.value:
        consultar()
    return C.seccion(C.titulo("Consultar mi reporte", "Escriba el código que recibió al enviarlo"),
                     C.panel(ft.Column([ft.Row([codigo]), b["x"]], spacing=12)), salida,
                     C.nota("Por privacidad solo mostramos el estado general de su reporte.", "info"))
