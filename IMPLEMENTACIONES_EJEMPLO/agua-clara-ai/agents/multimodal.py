"""A1 multimodale — enriquece un reporte con lo que se pueda extraer de la
evidencia (imagen, audio, vídeo, documento) usando el proveedor disponible.

- Imagen  -> visión (llm.vision_chat).
- Audio/Vídeo -> agente A1c (transcripción + campos).
- Documento de texto -> lectura directa.
- Sin proveedor -> devuelve solo el texto, sin inventar nada.

No rompe el flujo existente; siempre devuelve las mismas claves.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, Optional

import config
from services import llm
from services.traces import log_step

AGENT = "A1_Multimodal"

MM_SYSTEM = (
    "Eres un extractor crítico para reportes de corte de agua. "
    "Extrae SOLO lo que hay en evidencia (texto/imagen/audio). "
    "NO inventes GPS. NO inventes litros. Marca ambigüedad. "
    "Devuelve JSON con keys: ubicacion_texto, horas_sin_agua (num|null), "
    "personas_afectadas (int|null), sector_hint, transcript (str|null), "
    "image_text (str|null), confidence (0-1), notes (str|null)."
)

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".amr", ".aac", ".flac")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".3gp", ".m4v")


def _guess_mime(path: Path) -> str:
    import mimetypes
    mt, _ = mimetypes.guess_type(str(path))
    if mt:
        return mt
    m = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
        ".pdf": "application/pdf", ".txt": "text/plain",
    }
    return m.get(path.suffix.lower(), "application/octet-stream")


def _classify(mime: str, name: str | None) -> str:
    mime = (mime or "").lower()
    name = (name or "").lower()
    if mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return "image"
    if mime.startswith("audio/") or name.endswith(AUDIO_EXTS):
        return "audio"
    if mime.startswith("video/") or name.endswith(VIDEO_EXTS):
        return "video"
    if mime.startswith("text/") or name.endswith((".txt", ".csv")):
        return "textdoc"
    if mime or name:
        return "document"
    return "none"


def _empty(text: str) -> Dict[str, Any]:
    return {
        "raw_text": text,
        "ubicacion_texto": None, "horas_sin_agua": None, "personas_afectadas": None,
        "sector_hint": None, "transcript": None, "image_text": None,
        "confidence": 0.5, "notes": None, "kind": "none",
    }


def enrich(text: str, media_path: Optional[str] = None, media_base64: Optional[str] = None,
           media_mime: Optional[str] = None, media_name: Optional[str] = None,
           run_id: str = "run_mm") -> Dict[str, Any]:
    enriched = _empty(text)
    if not config.MULTIMODAL_ENABLED:
        return enriched

    path = Path(media_path) if media_path else None
    mime = media_mime or (_guess_mime(path) if path and path.exists() else None)
    name = media_name or (path.name if path else None)
    kind = _classify(mime or "", name)
    enriched["kind"] = kind

    # Sin media: la extracción de texto la hace A1 (evita una segunda llamada).
    if kind == "none" and not media_base64 and not (path and path.exists()):
        return enriched

    # Audio / vídeo: delega al agente A1c
    if kind in ("audio", "video"):
        from agents import audio_agent
        res = audio_agent.understand(media_path=str(path) if path and path.exists() else None,
                                     media_base64=media_base64, media_mime=mime,
                                     media_name=name, run_id=run_id)
        fields = res.get("fields") or {}
        enriched["transcript"] = res.get("transcript")
        enriched["ubicacion_texto"] = fields.get("ubicacion_texto")
        enriched["horas_sin_agua"] = fields.get("horas_sin_agua")
        enriched["personas_afectadas"] = fields.get("personas_afectadas")
        enriched["notes"] = res.get("notes")
        enriched["confidence"] = 0.72 if res.get("transcript") else 0.5
        return enriched

    # Documento de texto: se lee directo
    if kind == "textdoc" and path and path.exists():
        try:
            enriched["image_text"] = path.read_text(encoding="utf-8", errors="ignore")[:4000]
            enriched["confidence"] = 0.6
        except Exception:
            pass
        return enriched

    # Imagen: visión (necesita proveedor)
    if not llm.available():
        enriched["notes"] = "Sin proveedor de visión: imagen registrada, análisis pendiente."
        return enriched

    b64 = media_base64
    if path and path.exists() and not b64:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    if kind == "image" and b64:
        content = [
            {"type": "text", "text": "TEXTO DEL REPORTE: " + (text or "(sin texto)")},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]
        try:
            raw = llm.vision_chat([
                {"role": "system", "content": MM_SYSTEM},
                {"role": "user", "content": content},
            ])
            if raw:
                j = _loads(raw)
                for k in enriched:
                    if k in j and j[k] is not None:
                        enriched[k] = j[k]
                enriched["confidence"] = float(enriched.get("confidence") or 0.6)
            log_step(run_id, AGENT, "vision", {"has_image": True, "mime": mime},
                     {"conf": enriched["confidence"], "has_h": enriched["horas_sin_agua"] is not None},
                     tools=["llm.vision_chat"], decision="imagen analizada")
        except Exception:
            pass
    return enriched


def _loads(raw: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e != -1:
            try:
                return json.loads(raw[s:e + 1])
            except Exception:
                return {}
        return {}
