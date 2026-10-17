"""Cliente LLM multi-proveedor (compatible con OpenAI) usando urllib.

Diseño: se intenta una CADENA de proveedores en orden de prioridad:
  1. xAI / Grok          (XAI_API_KEY)            <- recomendado para agentes
  2. Genérico / Gemini   (AGUA_LLM_API_KEY)       <- configuración histórica
  3. OpenAI              (OPENAI_API_KEY)
  4. Gemini directo      (GEMINI_API_KEY)

Si no hay clave, no hay red o el modelo devuelve algo inválido, las funciones
devuelven None y el sistema cae a sus reglas deterministas. La demo nunca se
cae por culpa del modelo.

Capacidades:
  - chat()        -> texto
  - vision_chat() -> imágenes (grok-4 / gpt-4o / gemini soportan visión)
  - transcribe()  -> audio (OpenAI Whisper / Gemini)
"""
from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.request

from config import env


# ---------------------------------------------------------------------------
# Cadena de proveedores
# ---------------------------------------------------------------------------

def providers() -> list[dict]:
    """Proveedores disponibles, en orden de prioridad (el primero gana)."""
    chain: list[dict] = []
    if env("XAI_API_KEY"):
        chain.append({
            "name": "xai",
            "base": env("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/"),
            "key": env("XAI_API_KEY"),
            "model": env("XAI_MODEL", "grok-4"),
            "vision_model": env("XAI_VISION_MODEL", "grok-4"),
        })
    if env("AGUA_LLM_API_KEY"):
        chain.append({
            "name": "generico",
            "base": env("AGUA_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            "key": env("AGUA_LLM_API_KEY"),
            "model": env("AGUA_LLM_MODEL", "gpt-4o-mini"),
            "vision_model": env("AGUA_LLM_MODEL", "gpt-4o-mini"),
        })
    if env("OPENAI_API_KEY"):
        chain.append({
            "name": "openai",
            "base": env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            "key": env("OPENAI_API_KEY"),
            "model": env("OPENAI_MODEL", "gpt-4o-mini"),
            "vision_model": env("OPENAI_MODEL", "gpt-4o-mini"),
        })
    if env("GEMINI_API_KEY"):
        chain.append({
            "name": "gemini",
            "base": env("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/").rstrip("/"),
            "key": env("GEMINI_API_KEY"),
            "model": env("GEMINI_MODEL", "gemini-2.5-flash"),
            "vision_model": env("GEMINI_MODEL", "gemini-2.5-flash"),
        })
    return chain


def active_provider() -> dict | None:
    chain = providers()
    return chain[0] if chain else None


def available() -> bool:
    return bool(providers())


# ---------------------------------------------------------------------------
# Núcleo HTTP
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: dict, key: str, timeout: int) -> dict | None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _completion(prov: dict, messages: list[dict], model: str, temperature: float,
                timeout: int, json_mode: bool = True) -> str | None:
    payload: dict = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
        "max_tokens": int(env("AGUA_LLM_MAX_TOKENS", "4096") or 4096),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post_json(f"{prov['base']}/chat/completions", payload, prov["key"], timeout)
    if not data:
        return None
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API pública (compatible con el código existente)
# ---------------------------------------------------------------------------

def chat(messages: list[dict], temperature: float = 0.0, timeout: int = 25) -> str | None:
    """Chat de texto. Prueba cada proveedor hasta que uno responda."""
    for prov in providers():
        out = _completion(prov, messages, prov["model"], temperature, timeout)
        if out:
            return out
    return None


def vision_chat(messages: list[dict], temperature: float = 0.0, timeout: int = 40) -> str | None:
    """Chat con imágenes (data URLs). Usa el modelo de visión de cada proveedor."""
    for prov in providers():
        out = _completion(prov, messages, prov.get("vision_model") or prov["model"], temperature, timeout)
        if out:
            return out
    return None


def transcribe(media_path: str | None = None, media_base64: str | None = None,
               media_mime: str | None = None, timeout: int = 60) -> str | None:
    """Transcribe audio (o extrae audio de vídeo) con el primer proveedor capaz.

    Soporta el endpoint tipo OpenAI `/audio/transcriptions`. Si ningún proveedor
    lo soporta, devuelve None y el sistema cae a su modo determinista.
    """
    data_bytes: bytes | None = None
    if media_base64:
        import base64
        try:
            data_bytes = base64.b64decode(media_base64)
        except Exception:
            data_bytes = None
    elif media_path:
        try:
            with open(media_path, "rb") as fh:
                data_bytes = fh.read()
        except Exception:
            data_bytes = None
    if not data_bytes:
        return None

    name = "audio"
    if media_path:
        name = media_path.replace("\\", "/").rsplit("/", 1)[-1]
    mime = media_mime or mimetypes.guess_type(name)[0] or "audio/mpeg"

    for prov in providers():
        if prov["name"] not in ("openai", "generico"):
            # xAI/Gemini no exponen /audio/transcriptions en el mismo formato.
            continue
        model = env("OPENAI_TRANSCRIBE_MODEL", "whisper-1") if prov["name"] == "openai" else "whisper-1"
        boundary = "----aguaClaraBoundary"
        parts: list[bytes] = []

        def _field(fname: str, value: str) -> None:
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{fname}\"\r\n\r\n{value}\r\n".encode("utf-8")
            )

        _field("model", model)
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
        )
        parts.append(data_bytes + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        req = urllib.request.Request(
            f"{prov['base']}/audio/transcriptions", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "Authorization": f"Bearer {prov['key']}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            text = out.get("text")
            if text:
                return text
        except Exception:
            continue
    return None


def json_chat(messages: list[dict]) -> dict | None:
    raw = chat(messages)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        # A veces el modelo envuelve el JSON en ```json ... ```
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start:end + 1])
            except Exception:
                return None
        return None
