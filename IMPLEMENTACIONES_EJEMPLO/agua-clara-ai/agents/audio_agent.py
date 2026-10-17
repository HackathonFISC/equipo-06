"""A1c · Agente de audio y vídeo.

Los reportes por WhatsApp llegan mucho en notas de voz. Este agente:
  1. Transcribe audio (o el audio de un vídeo) con el proveedor disponible.
  2. Extrae campos del texto transcrito (horas, personas, tipo, ubicación).
  3. Si no hay proveedor, degrada con elegancia (no inventa nada).

Es determinista en su estructura: siempre devuelve las mismas claves.
"""
from __future__ import annotations

import time

from services import llm, memory
from services.traces import log_step

AGENT = "A1c_Audio"

AUDIO_MIME_PREFIXES = ("audio/",)
VIDEO_MIME_PREFIXES = ("video/",)

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".amr", ".aac", ".flac")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".3gp", ".m4v")


def _kind(media_mime: str | None, media_name: str | None = None) -> str:
    mime = (media_mime or "").lower()
    name = (media_name or "").lower()
    if mime.startswith(AUDIO_MIME_PREFIXES) or name.endswith(AUDIO_EXTS):
        return "audio"
    if mime.startswith(VIDEO_MIME_PREFIXES) or name.endswith(VIDEO_EXTS):
        return "video"
    return "otro"


def _extract_fields(transcript: str) -> dict:
    """Extrae campos del texto transcrito con reglas (y LLM si está disponible)."""
    fields: dict = {"tipo": None, "horas_sin_agua": None, "personas_afectadas": None,
                    "institucion": None, "ubicacion_texto": None}
    # 1) intentar con LLM (mejor con lenguaje natural hablado)
    if llm.available():
        from agents import intake
        data = intake._llm_extract(transcript)  # reutiliza el prompt de ingesta
        if data:
            fields["tipo"] = data.get("tipo").value if hasattr(data.get("tipo"), "value") else data.get("tipo")
            fields["horas_sin_agua"] = data.get("horas_sin_agua")
            fields["personas_afectadas"] = data.get("personas_afectadas")
            fields["institucion"] = data.get("institucion")
            fields["ubicacion_texto"] = data.get("ubicacion_texto")
            return fields
    # 2) reglas deterministas
    from agents import intake
    data = intake._rule_extract(transcript)
    fields["tipo"] = data.get("tipo").value if hasattr(data.get("tipo"), "value") else data.get("tipo")
    fields["horas_sin_agua"] = data.get("horas_sin_agua")
    fields["personas_afectadas"] = data.get("personas_afectadas")
    fields["institucion"] = data.get("institucion")
    return fields


def understand(media_path: str | None = None, media_base64: str | None = None,
               media_mime: str | None = None, media_name: str | None = None,
               run_id: str | None = None) -> dict:
    run_id = run_id or "run_ad_hoc"
    started = time.perf_counter()
    kind = _kind(media_mime, media_name)

    result = {"kind": kind, "transcript": None, "fields": None,
              "provider": None, "notes": None}

    if kind == "otro":
        return result

    transcript = None
    if llm.available():
        transcript = llm.transcribe(media_path=media_path, media_base64=media_base64,
                                    media_mime=media_mime)
    prov = llm.active_provider()
    result["provider"] = prov["name"] if prov else None

    if transcript:
        # Jerga detectada en el audio (p. ej. "no hay ni gota")
        low = transcript.lower()
        slang_intent = next((intent for term, intent in memory.slang().items() if term in low), None)
        fields = _extract_fields(transcript)
        if slang_intent and not fields.get("tipo"):
            fields["tipo"] = slang_intent
        result["transcript"] = transcript
        result["fields"] = fields
        decision = f"transcrito ({kind})"
    elif not llm.available():
        result["notes"] = "Sin proveedor de transcripción: audio registrado, transcripción pendiente."
        decision = "sin proveedor (pendiente)"
    else:
        result["notes"] = "No se pudo transcribir el audio automáticamente."
        decision = "transcripción fallida"

    log_step(run_id, AGENT, f"transcribir_{kind}", {"has_media": bool(media_path or media_base64), "mime": media_mime},
             {"has_transcript": bool(transcript), "provider": result["provider"]},
             tools=["llm.transcribe"], latency_ms=(time.perf_counter() - started) * 1000,
             decision=decision)
    return result
