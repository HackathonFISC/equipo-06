"""Estado de dispositivos y del servidor: contrato con la API para el ESP32-S3 / Raspberry. Sin dispositivos verificados."""

import json

import flet as ft

import config
from interface.flet_app import components as C
from interface.flet_app import theme as T
from services import audit, workflow


def build(ctx) -> ft.Control:
    aviso = C.nota("Ningún dispositivo físico está verificado todavía. La API ya expone el contrato; la pantalla ESP32-S3 y la Raspberry Pi están "
                   "pendientes de prueba física. Un dispositivo solo LEE el estado y publica confirmaciones: no aprueba planes y accede por la API, "
                   "nunca a SQLite.", "warn")
    tokens = ft.Row([ft.Text("Token de operador:", size=13), C.pill("configurado" if config.API_TOKEN() else "sin configurar (solo localhost)", "ok" if config.API_TOKEN() else "warn"),
                     ft.Text("Token de dispositivo:", size=13), C.pill("configurado" if config.DEVICE_TOKEN() else "sin configurar (solo localhost)", "ok" if config.DEVICE_TOKEN() else "warn")],
                    spacing=10, wrap=True)
    conf = [x for x in audit.listar() if x.responsable.startswith("dispositivo:")]
    tabla_conf = C.tabla(["Fecha", "Dispositivo", "Acción", "Plan"], [[str(x.fecha)[:19], x.responsable, x.accion, x.entidad_id] for x in reversed(conf)]) \
        if conf else C.nota("Sin confirmaciones: ningún dispositivo ha publicado datos.", "info")
    estado = json.loads(workflow.estado_actual().model_dump_json())
    endpoints = C.tabla(["Método", "Ruta", "Uso"], [["GET", "/api/v1/estado", "plan aprobado/pendiente, top de prioridades, cisternas (sin borradores ni textos de ciudadanos)"],
                                                     ["POST", "/api/v1/dispositivos/confirmaciones", "confirmar recepción/ejecución (solo se audita)"],
                                                     ["GET", "/api/v1/salud", "comprobación de salud"]])
    return C.seccion(C.titulo("Estado de dispositivos", "Contrato con la API para el ESP32-S3 y la Raspberry Pi"), aviso,
                     C.panel(tokens, "Seguridad de la API"), C.panel(endpoints, "Endpoints para dispositivos"),
                     C.panel(tabla_conf, "Confirmaciones recibidas"),
                     C.panel(ft.Container(ft.Text(json.dumps(estado, ensure_ascii=False, indent=2)[:6000], size=11, selectable=True, font_family="monospace"),
                                          bgcolor="#f3f7fb", border_radius=10, padding=12), "Lo que ve un dispositivo (GET /api/v1/estado)"))
