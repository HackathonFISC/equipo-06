"""
API HTTP local (FastAPI) - contrato para dispositivos futuros (Raspberry Pi / ESP32-S3).
Es una capa fina sobre services.workflow; no contiene lógica de negocio.

Iniciar:  uvicorn api.main:app --port 8000      Documentación interactiva: /docs
"""

from typing import List

from fastapi import FastAPI, HTTPException

from models.schemas import (Cisterna, ConfirmacionDispositivo, EstadoActual, PropuestaPlan,
                            Reporte, SCHEMA_VERSION)
from services import audit, workflow
from services.workflow import ErrorDeNegocio

app = FastAPI(title="Agua Clara AI - API local", version=SCHEMA_VERSION)


def _err(e: ErrorDeNegocio) -> HTTPException:
    return HTTPException(status_code=422 if "existe" not in str(e) else 404, detail=str(e))


@app.get("/api/v1/salud")
def salud():
    return {"ok": True, "schema_version": SCHEMA_VERSION}


@app.get("/api/v1/estado", response_model=EstadoActual)
def estado():
    """Estado actual: plan aprobado, plan pendiente de revisión, cisternas."""
    return workflow.estado_actual()


@app.get("/api/v1/cisternas", response_model=List[Cisterna])
def cisternas():
    return workflow.listar_cisternas()


@app.get("/api/v1/reportes", response_model=List[Reporte])
def reportes():
    return workflow.listar_reportes()


@app.get("/api/v1/planes", response_model=List[PropuestaPlan])
def planes():
    return workflow.listar_planes()


@app.get("/api/v1/planes/{plan_id}", response_model=PropuestaPlan)
def plan(plan_id: int):
    try:
        return workflow.obtener_plan(plan_id)
    except ErrorDeNegocio as e:
        raise _err(e)


@app.post("/api/v1/dispositivos/confirmaciones", status_code=202)
def confirmacion(c: ConfirmacionDispositivo):
    """Un dispositivo confirma recepción/ejecución. Solo se audita; no modifica el plan."""
    try:
        workflow.registrar_confirmacion_dispositivo(c)
    except ErrorDeNegocio as e:
        raise _err(e)
    return {"aceptada": True}


@app.get("/api/v1/auditoria")
def auditoria(entidad: str = None, entidad_id: str = None):
    return {"integra": audit.verificar_integridad(), "entradas": audit.listar(entidad, entidad_id)}
