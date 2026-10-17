"""Recorrido completo de la interfaz con el motor de pruebas de Streamlit (sin navegador)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _click(at, label):
    [b for b in at.button if label in b.label][0].click().run()


def test_recorrido_ui():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    # confirmar el primer reporte tal cual (paso 2)
    [b for b in at.get("form_submit_button") if "Confirmar" in b.label][0].click().run()
    assert not at.exception, at.exception
    assert any("confirmado" in s.value for s in at.success)
    # generar plan
    _click(at, "Generar propuesta")
    assert not at.exception, at.exception
    _click(at, "Aprobar plan")
    assert not at.exception, at.exception
    assert any("aprobado" in s.value for s in at.success)
