"""
Pruebas de la interfaz Flet SIN abrir ventana: se construyen las páginas con un Ctx sin Page y se invocan los
manejadores de eventos (on_click, on_select) igual que haría Flet. Cubren el portal público (sin sesión) y las
operaciones de la consola de administración (con sesión de administrador). NO sustituyen una revisión visual.
Roles, login y sesión: tests/test_flet_roles.py.
"""
import re
from typing import Callable, Iterator, Optional

import flet as ft
import pytest

from interface.flet_app import main as app
from interface.flet_app.contexto import Ctx
from models.schemas import AccionDecision, EstadoPlan, EstadoReporte
from services import auth, workflow

CLAVE = "Clave-Segura-1"
ATRIBUTOS = ("content", "controls", "rows", "cells", "title", "actions", "leading", "trailing")
# El portal ciudadano no debe mostrar nada técnico (ni siquiera como etiqueta o ayuda).
PROHIBIDAS = ("pytest", "pass", "fail", "runner", "gemini", "traza", "auditor", "hash")


def recorrer(c) -> Iterator[ft.Control]:
    if isinstance(c, ft.Control):
        yield c
        for a in ATRIBUTOS:
            v = getattr(c, a, None)
            if isinstance(v, ft.Control):
                yield from recorrer(v)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    yield from recorrer(x)


def buscar(raiz, tipo, pred: Callable = lambda c: True) -> Optional[ft.Control]:
    return next((c for c in recorrer(raiz) if isinstance(c, tipo) and pred(c)), None)


def boton(raiz, texto: str):
    b = buscar(raiz, (ft.Button, ft.OutlinedButton, ft.FilledButton, ft.TextButton), lambda c: isinstance(c.content, str) and texto in c.content)
    assert b is not None, f"no hay botón «{texto}»"
    return b


def campo(raiz, etiqueta: str):
    c = buscar(raiz, (ft.TextField, ft.Dropdown), lambda c: c.label and etiqueta in str(c.label))
    assert c is not None, f"no hay campo «{etiqueta}»"
    return c


def textos(raiz) -> str:
    return " | ".join(str(c.value) for c in recorrer(raiz) if isinstance(c, ft.Text))


def todo_el_texto(raiz) -> str:
    """Todo lo que una persona podría leer u oír: textos, botones, etiquetas, ayudas, tooltips y errores."""
    partes = []
    for c in recorrer(raiz):
        for atr in ("value", "label", "hint_text", "tooltip", "error_text", "helper_text", "semantics_label", "text"):
            v = getattr(c, atr, None)
            if isinstance(v, str):
                partes.append(v)
        if isinstance(getattr(c, "content", None), str):
            partes.append(c.content)
    return " | ".join(partes)


def construir_ctx(admin: bool = False) -> Ctx:
    c = Ctx(None)
    c.destinos = []
    c._mostrar = lambda pagina: (c.destinos.append(pagina), setattr(c, "pagina_actual", app.resolver(c, pagina)))
    if admin:
        auth.crear_usuario("admin1", CLAVE, auth.Rol.ADMIN)
        c.abrir_sesion("admin1", CLAVE)
    return c


@pytest.fixture
def portal():
    return construir_ctx()


@pytest.fixture
def ctx():
    """Contexto con sesión de administrador (lo normal en la consola)."""
    return construir_ctx(admin=True)


def pagina(c, clave):
    return app.construir_pagina(c, clave)


def confirmar_todo():
    for r in workflow.listar_reportes():
        if r.sector:
            workflow.corregir_y_confirmar(r.id, "t", r.sector, r.horas_sin_agua, r.personas_afectadas, r.severidad.value if r.severidad else None, r.calle)


# ================================================================ PORTAL PÚBLICO
def test_portal_paginas_construyen_sin_sesion_y_sin_textos_tecnicos(portal):
    confirmar_todo()
    workflow.generar_plan("t")
    for clave, _, _, _ in app.PORTAL:
        p = pagina(portal, clave)
        t = todo_el_texto(p)
        assert "No se pudo mostrar" not in t, clave
        bajo = t.lower()
        for palabra in PROHIBIDAS:
            assert not re.search(re.escape(palabra), bajo), f"«{palabra}» aparece en el portal ({clave}): {t[:200]}"
    assert not portal.es_admin


def test_portal_inicio_tiene_las_acciones_y_pasos(portal):
    p = pagina(portal, "inicio")
    t = textos(p)
    assert "HIDRO360" in t and "¿Cómo funciona?" in t and "Avisos para su comunidad" in t
    boton(p, "Reportar falta de agua").on_click(None)
    assert portal.destinos[-1] == "reportar"
    boton(p, "Consultar con mi código").on_click(None)
    assert portal.destinos[-1] == "consultar"


def test_portal_reportar_registra_y_muestra_codigo(portal):
    p = pagina(portal, "reportar")
    campo(p, "Cuéntenos").value = "Se rompió una tubería en Chame, llevamos 2 días sin agua, unas 30 familias"
    antes = len(workflow.listar_reportes())
    boton(p, "Enviar reporte").on_click(None)
    nuevos = workflow.listar_reportes()[antes:]
    assert len(nuevos) == 1 and nuevos[0].estado == EstadoReporte.POR_REVISAR
    assert nuevos[0].mensaje_original.startswith("Se rompió una tubería")
    assert re.fullmatch(r"HID-[A-Z0-9]{8}", nuevos[0].codigo_seguimiento)
    t = textos(p)
    assert "Su reporte quedó registrado" in t and nuevos[0].codigo_seguimiento in t
    assert str(nuevos[0].id) not in re.findall(r"\b\d+\b", t.replace(nuevos[0].codigo_seguimiento, ""))   # sin ids internos
    assert nuevos[0].canal == "portal" if hasattr(nuevos[0], "canal") else True


def test_portal_reportar_doble_clic_no_duplica(portal):
    p = pagina(portal, "reportar")
    campo(p, "Cuéntenos").value = "En Vista Alegre no tenemos agua desde ayer"
    antes = len(workflow.listar_reportes())
    enviar = boton(p, "Enviar reporte")                  # el formulario se reemplaza por la confirmación: se conserva el botón
    enviar.on_click(None)
    enviar.on_click(None)                                # segundo clic: misma clave de idempotencia
    assert len(workflow.listar_reportes()) == antes + 1
    # al reabrir el formulario se usa una clave nueva
    clave_vieja = portal.clave_envio
    pagina(portal, "reportar")
    assert portal.clave_envio != clave_vieja


def test_portal_reportar_rechaza_texto_vacio(portal):
    p = pagina(portal, "reportar")
    antes = len(workflow.listar_reportes())
    campo(p, "Cuéntenos").value = "   "
    boton(p, "Enviar reporte").on_click(None)
    assert len(workflow.listar_reportes()) == antes and campo(p, "Cuéntenos").error_text


def test_portal_consultar_muestra_solo_estado_publico(portal):
    p = pagina(portal, "reportar")
    campo(p, "Cuéntenos").value = "Sin agua en El Coco desde hace tres dias, mi nombre es Secreto Privado"
    boton(p, "Enviar reporte").on_click(None)
    codigo = workflow.listar_reportes()[-1].codigo_seguimiento
    c = pagina(portal, "consultar")
    campo(c, "Código").value = codigo.lower()
    boton(c, "Consultar").on_click(None)
    t = textos(c)
    assert codigo in t and "revisión" in t
    assert "Secreto Privado" not in t and "tres dias" not in t


def test_portal_consultar_codigo_inexistente_no_revela_nada(portal):
    c = pagina(portal, "consultar")
    campo(c, "Código").value = "HID-ZZZZZZZZ"
    boton(c, "Consultar").on_click(None)
    assert "No encontramos un reporte" in textos(c)
    campo(c, "Código").value = ""
    boton(c, "Consultar").on_click(None)
    assert campo(c, "Código").error_text


def test_portal_avisos_son_comprensibles_y_sin_datos_internos(portal):
    confirmar_todo()
    plan = workflow.generar_plan("t")
    workflow.decidir_plan(plan.id, AccionDecision.APROBAR, "t")
    t = textos(pagina(portal, "avisos"))
    assert "atención programada" in t or "en evaluación" in t
    for prohibido in ("litros", "cisterna", "borrador", "puntaje", "motivo", "supervisor"):
        assert prohibido not in t.lower()
    for r in workflow.listar_reportes():                      # ningún texto de reportes de otras personas
        assert r.mensaje_original[:30] not in t


def test_portal_no_invoca_funciones_administrativas(portal, monkeypatch):
    """Aunque quien navega sea la ciudadanía, el portal solo usa funciones públicas: ejecutar sin actor no debe fallar por permisos."""
    n = len(workflow.listar_reportes())                 # (conftest da actor admin a la prueba; el portal no lo usa)
    with auth.como(None):
        for clave, _, _, _ in app.PORTAL:
            assert "No se pudo mostrar" not in textos(pagina(portal, clave)), clave
        p = pagina(portal, "reportar")
        campo(p, "Cuéntenos").value = "No hay agua en Arraiján"
        boton(p, "Enviar reporte").on_click(None)
    assert len(workflow.listar_reportes()) == n + 1


# =============================================================== CONSOLA (con sesión)
def test_todas_las_paginas_admin_construyen_sin_caer_en_el_limite_de_errores(ctx):
    confirmar_todo()
    workflow.generar_plan("t")
    for clave, etiqueta, _, _ in app.PAGINAS:
        assert "No se pudo mostrar" not in textos(pagina(ctx, clave)), clave


def test_registro_de_paginas_cubre_los_modulos():
    import importlib
    for _, _, _, modulo in app.PAGINAS:
        assert hasattr(importlib.import_module(f"interface.flet_app.admin.{modulo}"), "build")
    for _, _, _, modulo in app.PORTAL:
        assert hasattr(importlib.import_module(f"interface.flet_app.portal.{modulo}"), "build")
    assert hasattr(importlib.import_module("interface.flet_app.admin.login"), "build")


def test_bandeja_recibe_reporte_con_el_responsable_de_la_sesion(ctx):
    p = pagina(ctx, "bandeja")
    campo(p, "Reporte ciudadano").value = "Se rompió una tubería en Chame, llevamos 2 días sin agua, unas 30 familias"
    antes = len(workflow.listar_reportes())
    boton(p, "Recibir reporte").on_click(None)
    nuevos = workflow.listar_reportes()[antes:]
    assert len(nuevos) == 1 and nuevos[0].estado == EstadoReporte.POR_REVISAR and nuevos[0].sector == "Chame"
    assert ctx.destinos[-1] == "revision" and ctx.seleccion["reporte_id"] == nuevos[0].id
    clave_usada = nuevos[0].clave_idempotencia
    ctx.clave_envio = clave_usada
    campo(p, "Reporte ciudadano").value = "texto distinto pero misma clave"
    boton(p, "Recibir reporte").on_click(None)
    assert len(workflow.listar_reportes()) == antes + 1


def test_bandeja_rechaza_texto_vacio(ctx):
    p = pagina(ctx, "bandeja")
    antes = len(workflow.listar_reportes())
    campo(p, "Reporte ciudadano").value = "   "
    boton(p, "Recibir reporte").on_click(None)
    assert len(workflow.listar_reportes()) == antes and campo(p, "Reporte ciudadano").error_text


def test_revision_confirma_y_valida(ctx):
    ctx.seleccion["reporte_id"] = 4  # Bejuco (50 personas)
    p = pagina(ctx, "revision")
    campo(p, "Horas sin agua").value = "abc"
    boton(p, "Confirmar datos").on_click(None)
    assert workflow.obtener_reporte(4).estado == EstadoReporte.POR_REVISAR  # número inválido: no se guarda
    campo(p, "Horas sin agua").value = "30"
    campo(p, "Personas afectadas").value = "55"
    boton(p, "Confirmar datos").on_click(None)
    r = workflow.obtener_reporte(4)
    assert r.estado == EstadoReporte.CONFIRMADO and r.horas_sin_agua == 30 and r.personas_afectadas == 55
    assert r.confirmado_por == "admin1"          # el responsable es el usuario autenticado, no un texto editable


def test_revision_sin_sector_no_confirma(ctx):
    r = workflow.crear_reporte("Se rompió una tubería cerca de la escuela", "t")  # sin sector
    ctx.seleccion["reporte_id"] = r.id
    p = pagina(ctx, "revision")
    boton(p, "Confirmar datos").on_click(None)
    assert workflow.obtener_reporte(r.id).estado == EstadoReporte.POR_REVISAR


def test_duplicados_decide_una_persona(ctx):
    ctx.seleccion["reporte_id"] = 2   # La Chorrera, duplicado probable de #1
    p = pagina(ctx, "duplicados")
    assert "Posible duplicado de #" in textos(p)
    boton(p, "Sí, es el mismo incidente").on_click(None)   # primer candidato (el más similar)
    r = workflow.obtener_reporte(2)
    assert r.estado == EstadoReporte.DUPLICADO and r.duplicado_de in (1, 3)
    assert workflow.obtener_reporte(r.duplicado_de).estado == EstadoReporte.POR_REVISAR  # nada se fusiona ni se borra
    assert workflow.obtener_reporte(2).mensaje_original  # el mensaje original se conserva


def test_plan_generar_aprobar_y_rechazar_con_reglas(ctx):
    confirmar_todo()
    p = pagina(ctx, "plan")
    boton(p, "Generar propuesta").on_click(None)
    assert len(workflow.listar_planes()) == 1
    p = pagina(ctx, "plan")
    plan = workflow.listar_planes()[0]
    assert plan.estado == EstadoPlan.PROPUESTO and "PROPUESTA" in textos(p)
    boton(p, "Rechazar plan").on_click(None)       # sin motivo: el backend lo impide y la interfaz avisa
    assert workflow.obtener_plan(plan.id).estado == EstadoPlan.PROPUESTO and ctx.avisos[-1][0] == "bad"
    boton(p, "Aprobar plan").on_click(None)
    assert workflow.obtener_plan(plan.id).estado == EstadoPlan.APROBADO
    p = pagina(ctx, "plan")
    assert "ya no se puede modificar" in textos(p)


def test_plan_edicion_exige_motivo_y_respeta_capacidad(ctx):
    confirmar_todo()
    workflow.generar_plan("t")
    p = pagina(ctx, "plan")
    campo(p, "Litros").value = "0"  # quitar la primera asignación
    boton(p, "Guardar modificaciones").on_click(None)
    assert not workflow.listar_planes()[0].editado and ctx.avisos[-1][0] == "bad"        # sin motivo
    campo(p, "Motivo").value = "cisterna reservada"
    boton(p, "Guardar modificaciones").on_click(None)
    assert workflow.listar_planes()[0].editado
    p = pagina(ctx, "plan")
    campo(p, "Litros").value = "999999"
    campo(p, "Motivo").value = "exceso"
    boton(p, "Guardar modificaciones").on_click(None)
    assert ctx.avisos[-1][0] == "bad" and "excede" in ctx.avisos[-1][1]               # capacidad validada en el backend


def test_comunicacion_borrador_local_no_se_envia(ctx):
    confirmar_todo()
    plan = workflow.generar_plan("t")
    p = pagina(ctx, "comunicacion")
    assert "BORRADOR" in textos(p) and "no se envían" in textos(p)
    boton(p, "Redactar con IA").on_click(None)   # sin Gemini: devuelve la plantilla local y lo dice
    assert "origen: local" in textos(p)
    assert workflow.obtener_plan(plan.id).estado == EstadoPlan.PROPUESTO


def test_navegacion_desde_el_panel(ctx):
    p = pagina(ctx, "panel")
    boton(p, "Bandeja de reportes").on_click(None)
    assert ctx.destinos[-1] == "bandeja"


def test_cargar_demo_vive_en_diagnostico_y_pide_confirmacion():
    """La acción destructiva usa ctx.confirmar (diálogo); sin Page se ejecuta directo, por eso se prueba el contrato."""
    import inspect

    from interface.flet_app.admin import datos_ejemplo
    fuente = inspect.getsource(datos_ejemplo)
    assert "ctx.confirmar(" in fuente and "BORRA" in fuente
    grupos = dict(app.GRUPOS_ADMIN)
    assert "datos_ejemplo" in [k for k, *_ in grupos[app.GRUPO_DIAGNOSTICO]]


def test_error_en_una_pagina_no_tumba_la_aplicacion(ctx, monkeypatch):
    import importlib
    mod = importlib.import_module("interface.flet_app.admin.panel")
    monkeypatch.setattr(mod, "build", lambda c: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "No se pudo mostrar" in textos(pagina(ctx, "panel"))
