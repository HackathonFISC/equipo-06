"""/api/v1/salud comprueba la base de verdad: con la base caída responde 503 y no declara persistencia funcional."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from data import database as db


@pytest.fixture
def c():
    return TestClient(app)


def test_salud_con_base_disponible(c):
    r = c.get("/api/v1/salud")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["ok"] is True
    assert cuerpo["persistencia"] == "sqlite"  # las pruebas usan SQLite temporal


def test_salud_con_base_caida_no_declara_persistencia(c, monkeypatch):
    def caida():
        raise RuntimeError("detalle interno que no debe salir")
    monkeypatch.setattr(db, "conexion", caida)
    r = c.get("/api/v1/salud")
    assert r.status_code == 503
    cuerpo = r.json()
    assert cuerpo["ok"] is False
    assert cuerpo["persistencia"] == "no_disponible"
    assert "detalle interno" not in r.text
