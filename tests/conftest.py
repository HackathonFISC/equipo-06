import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def bd_temporal(tmp_path, monkeypatch):
    """Base y trazas temporales y, por defecto, un actor administrador de servicio para que las pruebas de lógica
    de negocio no tengan que autenticarse. Las pruebas de autorización lo anulan con `auth.como(None)`
    (o `auth.actor_actual.set(None)`)."""
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "TRACE_PATH", tmp_path / "trazas.jsonl")
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AGUA_CLARA_API_TOKEN", raising=False)
    monkeypatch.delenv("AGUA_CLARA_DEVICE_TOKEN", raising=False)
    from api import main as api_main
    from services import auth, workflow
    auth.reiniciar_estado()
    workflow.reiniciar_limites()
    api_main.reiniciar_limites()
    token = auth.actor_actual.set(auth.Actor("tests", auth.Rol.ADMIN, "servicio"))
    try:
        workflow.cargar_datos_demo("test")
        yield
    finally:
        auth.actor_actual.reset(token)
        auth.reiniciar_estado()
