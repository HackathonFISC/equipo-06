"""poseidon_core.route · router de FastAPI del Proyecto Poseidón.

Se integra en una línea desde la app principal::

    from poseidon_core.route import router as poseidon_router
    app.include_router(poseidon_router)

Endpoints:
- ``POST /poseidon/analizar``   multipart (archivo + barriada) -> evidencia + decisión.
- ``POST /poseidon/simular``    genera una muestra sintética y la analiza (demo offline).
- ``POST /poseidon/webhook``    JSON compatible con una pasarela de WhatsApp.
- ``GET  /poseidon/lecturas``   histórico de lecturas + alertas encoladas.
- ``GET  /poseidon/sector``     estado agregado de una barriada.
"""
from __future__ import annotations

import os
import tempfile
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

import config
from poseidon_core import audio, vision
from poseidon_core.agents import ORQUESTADOR
from poseidon_core.store import ALMACEN

router = APIRouter(prefix="/poseidon", tags=["Proyecto Poseidón"])

_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".m4a", ".aac", ".opus", ".amr", ".flac"}
_MAX_BYTES = config.MULTIMODAL_MAX_MB * 1024 * 1024


class WebhookPayload(BaseModel):
    """Payload de la pasarela de WhatsApp (compatible con la pasarela Meta)."""
    telefono_usuario: str
    barriada: str
    tipo_archivo: str                     # "audio" | "imagen"
    url_archivo_temporal: str = ""


# ----------------------------- helpers -----------------------------

def _guardar_local(contenido: bytes, nombre: str) -> str:
    if len(contenido) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande.")
    seguro = Path(nombre).name or f"media_{uuid.uuid4().hex[:8]}.bin"
    destino = config.UPLOADS_DIR / f"poseidon_{uuid.uuid4().hex[:8]}_{seguro}"
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return str(destino)


def _es_audio(nombre: str, mime: str) -> bool:
    if mime and mime.startswith("audio/"):
        return True
    return Path(nombre).suffix.lower() in _AUDIO_EXTS


def _procesar(path: str, barriada: str, telefono: str, tipo: str) -> Dict[str, Any]:
    """Clasifica (acústica o visión) y pasa la lectura al enjambre."""
    if tipo == "audio":
        evidencia = audio.analizar_espectro_grifo(path)
        estado = evidencia.get("estado", "desconocido")
        confianza = evidencia.get("confianza", 0.0)
        segundo = evidencia.get("segundo_inicio", 0)
        lectura_tipo = "audio"
    else:
        evidencia = vision.analizar_infraestructura_visual(path)
        estado = evidencia.get("estado", "desconocido")
        confianza = evidencia.get("confianza", 0.0)
        segundo = 0
        lectura_tipo = "imagen"

    lectura = {
        "phone": telefono, "tipo": lectura_tipo, "estado": estado,
        "confianza": confianza, "segundo": segundo,
    }
    decision = ORQUESTADOR.procesar_lectura_sectorial(barriada, lectura)
    return {"ok": True, "archivo": os.path.basename(path), "tipo": lectura_tipo,
            "evidencia": evidencia, "lectura": lectura, "decision": decision}


# ----------------------------- endpoints -----------------------------

@router.post("/analizar")
async def analizar(file: UploadFile = File(...), barriada: str = Form(...),
                   telefono: str = Form("")) -> Dict[str, Any]:
    """Recibe un audio o una foto (multipart) y devuelve evidencia + decisión."""
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="Archivo vacío.")
    nombre = Path(file.filename or "media").name
    tipo = "audio" if _es_audio(nombre, file.content_type or "") else "imagen"
    ruta = _guardar_local(contenido, nombre)
    try:
        return _procesar(ruta, barriada, telefono, tipo)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error procesando el archivo: {exc}")


@router.post("/simular")
async def simular(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Genera una muestra sintética (offline) y la procesa con el enjambre.

    Body: ``{"barriada": "Burunga", "estado": "aire"|"flujo_normal"|"seco",
    "telefono": "5076...", "segundos": 6}``
    """
    barriada = str(payload.get("barriada") or "").strip()
    if not barriada:
        raise HTTPException(status_code=400, detail="Falta la barriada.")
    estado = str(payload.get("estado") or "aire").lower()
    if estado not in ("aire", "flujo_normal", "seco"):
        raise HTTPException(status_code=400, detail="estado inválido: usa aire|flujo_normal|seco")
    try:
        segundos = float(payload.get("segundos") or 6)
        segundos = max(2.0, min(20.0, segundos))
    except Exception:
        segundos = 6.0
    telefono = str(payload.get("telefono") or "")

    ruta = audio.sintetizar_muestra(estado, segundos=segundos)
    return _procesar(ruta, barriada, telefono, "audio")


@router.post("/webhook")
async def webhook(payload: WebhookPayload) -> Dict[str, Any]:
    """Webhook de la pasarela: descarga la media (si hay URL) y analiza."""
    barriada = payload.barriada.strip()
    if not barriada:
        raise HTTPException(status_code=400, detail="Falta la barriada.")
    tipo = "audio" if (payload.tipo_archivo or "").lower().startswith("audio") else "imagen"
    ruta: Optional[str] = None

    if payload.url_archivo_temporal:
        try:
            if payload.url_archivo_temporal.startswith(("http://", "https://")):
                req = urllib.request.Request(payload.url_archivo_temporal,
                                             headers={"User-Agent": "agua-clara-ai"})
                with urllib.request.urlopen(req, timeout=25) as resp:
                    datos = resp.read(_MAX_BYTES + 1)
            else:
                datos = Path(payload.url_archivo_temporal).read_bytes()
            if len(datos) > _MAX_BYTES:
                raise HTTPException(status_code=413, detail="Archivo demasiado grande.")
            ruta = _guardar_local(datos, "whatsapp_media")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"No se pudo descargar la media: {exc}")
    else:
        # Sin archivo: se registra la lectura como "desconocido" y no se rompe nada.
        decision = ORQUESTADOR.procesar_lectura_sectorial(
            barriada,
            {"phone": payload.telefono_usuario, "tipo": tipo,
             "estado": "desconocido", "confianza": 0.0, "segundo": 0})
        return {"ok": True, "archivo": None, "tipo": tipo, "evidencia": None,
                "lectura": None, "decision": decision}

    return _procesar(ruta, barriada, payload.telefono_usuario, tipo)


@router.get("/lecturas")
async def lecturas(sector: Optional[str] = None, minutos: int = Query(1440, ge=1, le=43200)) -> Dict[str, Any]:
    """Histórico de lecturas hidroacústicas + alertas predictivas encoladas."""
    sid = None
    if sector:
        sid, _, _ = ORQUESTADOR.resolver_sector(sector)
    filas = ALMACEN.lecturas_recientes(sid, minutos)
    try:
        from services import storage
        alertas = [o for o in storage.list_outbox(limit=100) if o.get("channel") in ("whatsapp", "sms")]
        alertas = [a for a in alertas if str(a.get("recipient", "")).startswith("sector:")]
    except Exception:
        alertas = []
    return {"backend": ALMACEN.backend, "total": len(filas),
            "lecturas": filas[:200], "alertas": alertas[:50]}


@router.get("/sector")
async def sector(barriada: str = Query(...), minutos: int = Query(1440, ge=1, le=43200)) -> Dict[str, Any]:
    """Estado agregado de una barriada (racha, conteo por estado, alerta)."""
    return ORQUESTADOR.resumen_sector(barriada, minutos)
