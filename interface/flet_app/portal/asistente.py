"""Asistente local de demostración: responde con reglas y preguntas frecuentes fijas.

No usa inteligencia artificial, ni Internet, ni Telegram. No guarda nada ni envía incidencias a ninguna institución:
solo orienta al ciudadano hacia el formulario o la consulta. Su identidad es explícita en pantalla.
"""

import flet as ft

from interface.flet_app import components as C
from interface.flet_app import theme as T

TEMAS = {
    "reportar": ("Cómo reportar", "Para reportar: escriba qué pasa y desde cuándo, indique la comunidad o el sector, "
                 "marque el lugar en el mapa si puede y pulse «Enviar reporte». Al terminar le damos un código de seguimiento."),
    "consultar": ("Cómo consultar", "Para consultar, escriba el código que recibió (formato HID-XXXXXXXX) en «Consultar mi reporte». "
                  "Solo verá el estado general de su reporte."),
    "estados": ("Qué significan los estados",
                "Recibido o en revisión: el reporte llegó y una persona lo revisa. "
                "Confirmado: fue validado y está en evaluación. "
                "En atención: está programado, pero no tenemos una hora de llegada confirmada. "
                "Agrupado: es el mismo problema de otro reporte. "
                "No procede: no puede atenderse como solicitud."),
    "informacion": ("Qué información dar",
                    "Ayuda indicar la calle o una referencia cercana, desde cuándo falta el agua, cuántas personas están afectadas, "
                    "si hay niños pequeños, adultos mayores o personas enfermas, y una foto si es posible (sin mostrar personas)."),
    "continua": ("Si el problema continúa",
                 "Consulte el estado de su reporte con su código. Si el problema continúa o es una emergencia, llame al 911."),
    "hora": ("Hora de llegada",
             "No podemos indicar una hora de llegada del servicio. Consulte el estado de su reporte o los avisos de su comunidad."),
}

NO_ENTIENDO = ("No entendí su pregunta. Puede elegir un tema: cómo reportar, cómo consultar, qué significan los estados, "
               "qué información dar o qué hacer si el problema continúa.")

# Palabras clave en orden de prioridad (la primera coincidencia gana).
REGLAS = [
    ("hora", ("hora", "cuando llega", "cuándo llega", "a qué hora")),
    ("continua", ("continua", "continúa", "sigue", "todavía", "todavia", "emergencia")),
    ("estados", ("estado", "significa", "recibido", "confirmado", "atención", "atencion")),
    ("consultar", ("consult", "código", "codigo", "seguimiento", "HID-")),
    ("informacion", ("informacion", "información", "datos", "qué poner", "que poner")),
    ("reportar", ("reportar", "reporte", "falta", "sin agua", "no hay agua", "denunciar")),
]


def responder(texto: str):
    """Devuelve (tema, respuesta). Función pura: no toca base de datos ni red."""
    t = (texto or "").strip()
    if not t:
        return None, "Escriba su pregunta o elija un tema."
    bajo = t.lower()
    for tema, palabras in REGLAS:
        if any(p.lower() in bajo for p in palabras):
            return tema, TEMAS[tema][1]
    return None, NO_ENTIENDO


def build(ctx) -> ft.Control:
    respuesta = ft.Text("", size=14.5, color=T.INK)
    tarjeta_respuesta = ft.Container(
        ft.Column([ft.Text("Asistente", size=13, weight=ft.FontWeight.W_700, color=T.BLUE), respuesta], spacing=6),
        bgcolor=T.WHITE, border=ft.Border.all(1, T.LINE), border_radius=14, padding=16, visible=False)
    entrada = ft.TextField(hint_text="Escriba su pregunta, por ejemplo: ¿cómo reporto?", multiline=False, expand=True,
                           border_radius=10, text_size=14)

    def mostrar(tema_o_texto, es_tema=False):
        if es_tema:
            etiqueta, texto = TEMAS[tema_o_texto]
            respuesta.value = texto
        else:
            _, texto = responder(tema_o_texto)
            respuesta.value = texto
        tarjeta_respuesta.visible = True
        ctx.actualizar()

    def preguntar(_):
        mostrar(entrada.value or "")

    chips = [ft.OutlinedButton(etiqueta, on_click=lambda e, k=k: mostrar(k, es_tema=True))
             for k, (etiqueta, _) in TEMAS.items()]

    return C.seccion(
        C.titulo("Asistente de HIDRO360", "Le orientamos para reportar y consultar"),
        C.nota("Asistente local de demostración: responde con preguntas frecuentes predefinidas. "
               "No usa inteligencia artificial, no necesita Internet y no envía incidencias a ninguna institución.", "info"),
        ft.Row(chips, wrap=True, spacing=8, run_spacing=8),
        ft.Row([entrada, C.boton("Preguntar", preguntar, ft.Icons.SEND, "primario")], spacing=10),
        tarjeta_respuesta,
        ft.Row([C.boton("Hacer un reporte", lambda e: ctx.ir("reportar"), ft.Icons.EDIT_NOTE, "secundario"),
                C.boton("Consultar mi reporte", lambda e: ctx.ir("consultar"), ft.Icons.SEARCH, "secundario")], spacing=10),
    )
