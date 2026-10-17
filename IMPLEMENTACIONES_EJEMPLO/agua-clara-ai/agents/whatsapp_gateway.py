"""A0 · Gateway de WhatsApp — el "agente de canal" (estilo Lindy).

Recibe el webhook real de WhatsApp (Meta Cloud API o Twilio), normaliza el
mensaje y separa texto de multimedia (imagen, audio, vídeo, documento, sticker,
ubicación). Descarga el archivo (con el token configurado) y lo deja listo para
que lo entiendan A1c (audio), A1 (visión/texto) y A2b (ubicación).

Sin token real funciona igual: marca la media como "pendiente" y no se cae.

También redacta respuestas (p. ej. la pregunta de aclaración de A2b) y las
encola en la bandeja de salida, canal 'whatsapp'.
"""
from __future__ import annotations

import json
import mimetypes
import time
import urllib.parse
import urllib.request
import uuid

import config
from schemas import MediaItem, WhatsAppIncoming
from services import storage
from services.traces import log_step

AGENT = "A0_WhatsApp"

_MEDIA_KIND_BY_MIME = {
    "image/": "image", "audio/": "audio", "video/": "video",
}
_MEDIA_EXT = {
    "image": ".jpg", "audio": ".ogg", "video": ".mp4", "document": ".bin", "sticker": ".webp",
}


def _kind_from(mtype: str, mime: str | None = None) -> str:
    if mtype in ("image", "audio", "video", "document", "sticker"):
        return mtype
    for prefix, kind in _MEDIA_KIND_BY_MIME.items():
        if (mime or "").startswith(prefix):
            return kind
    return "document"


def _ts(value) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except Exception:
        from config import now_iso
        return now_iso()


# ---------------------------------------------------------------------------
# Parseo de payloads
# ---------------------------------------------------------------------------

def _parse_meta(value: dict) -> list[WhatsAppIncoming]:
    contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts", [])}
    out: list[WhatsAppIncoming] = []
    for msg in value.get("messages", []):
        mtype = msg.get("type", "text")
        sender = msg.get("from", "desconocido")
        text, media, loc = "", [], None
        if mtype == "text":
            text = (msg.get("text") or {}).get("body", "")
        elif mtype == "location":
            L = msg.get("location") or {}
            loc = {"latitude": L.get("latitude"), "longitude": L.get("longitude"),
                   "name": L.get("name"), "address": L.get("address")}
            text = "Ubicación compartida" + (f": {L.get('name')}" if L.get("name") else "")
        elif mtype == "contacts":
            text = "Contacto compartido"
        elif mtype in ("image", "video", "audio", "document", "sticker"):
            node = msg.get(mtype) or {}
            caption = node.get("caption") or ""
            text = caption
            media.append(MediaItem(
                kind=_kind_from(mtype, node.get("mime_type")),
                mime=node.get("mime_type"), name=node.get("filename"),
                media_id=node.get("id"), caption=caption or None,
            ))
        elif mtype in ("button", "interactive"):
            obj = msg.get(mtype) or {}
            text = (obj.get("text") or (obj.get("button") or {}).get("text") or "").strip()
        out.append(WhatsAppIncoming(
            message_id=msg.get("id") or ("wa_" + uuid.uuid4().hex[:10]),
            sender=sender, sender_name=contacts.get(sender),
            text=text, media=media, location=loc,
            timestamp=_ts(msg.get("timestamp")), channel="whatsapp",
        ))
    return out


def _parse_twilio(payload: dict) -> list[WhatsAppIncoming]:
    sender = str(payload.get("From", "desconocido")).replace("whatsapp:", "")
    n = int(payload.get("NumMedia", 0) or 0)
    media = []
    for i in range(n):
        mime = payload.get(f"MediaContentType{i}")
        url = payload.get(f"MediaUrl{i}")
        media.append(MediaItem(kind=_kind_from("", mime), mime=mime, url=url))
    loc = None
    if payload.get("Latitude") and payload.get("Longitude"):
        try:
            loc = {"latitude": float(payload["Latitude"]), "longitude": float(payload["Longitude"])}
        except Exception:
            loc = None
    return [WhatsAppIncoming(
        message_id=payload.get("MessageSid") or ("wa_" + uuid.uuid4().hex[:10]),
        sender=sender, sender_name=payload.get("ProfileName"),
        text=payload.get("Body", ""), media=media, location=loc,
        timestamp=_ts(payload.get("SmsTimestamp")) if payload.get("SmsTimestamp") else None,
        channel="whatsapp",
    )]


def parse_webhook(payload: dict, run_id: str | None = None) -> list[WhatsAppIncoming]:
    run_id = run_id or "run_wa"
    started = time.perf_counter()
    incoming: list[WhatsAppIncoming] = []
    try:
        if "entry" in payload:  # Meta Cloud API
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    incoming.extend(_parse_meta(change.get("value", {})))
        elif "From" in payload or "Body" in payload:  # Twilio
            incoming.extend(_parse_twilio(payload))
        elif "messages" in payload:  # payload simplificado
            incoming.extend(_parse_meta(payload))
    except Exception:
        incoming = []

    log_step(run_id, AGENT, "parsear_webhook", {"keys": list(payload.keys())[:6]},
             {"mensajes": len(incoming),
              "con_media": sum(1 for m in incoming if m.media),
              "con_ubicacion": sum(1 for m in incoming if m.location)},
             tools=["parse_meta", "parse_twilio"],
             latency_ms=(time.perf_counter() - started) * 1000, decision="mensajes normalizados")
    return incoming


# ---------------------------------------------------------------------------
# Descarga de multimedia
# ---------------------------------------------------------------------------

def _max_bytes() -> int:
    return config.MULTIMODAL_MAX_MB * 1024 * 1024


def _download(url: str, dest, headers: dict | None = None) -> bool:
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = resp.read(_max_bytes() + 1)
        if len(data) > _max_bytes():
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def _resolve_meta_media_url(media_id: str) -> str | None:
    token = config.WHATSAPP_ACCESS_TOKEN
    if not token or not media_id:
        return None
    try:
        req = urllib.request.Request(
            f"https://graph.facebook.com/v20.0/{media_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8")).get("url")
    except Exception:
        return None


def download_media(item: MediaItem) -> MediaItem:
    """Descarga la media si es posible. Devuelve el item actualizado."""
    ext = mimetypes.guess_extension(item.mime or "") or _MEDIA_EXT.get(item.kind, ".bin")
    dest = config.WHATSAPP_MEDIA_DIR / f"wa_{uuid.uuid4().hex[:12]}{ext}"

    if item.url:
        item.downloaded = _download(item.url, dest)
    elif item.media_id:
        url = _resolve_meta_media_url(item.media_id)
        if url:
            headers = {"Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}"} if config.WHATSAPP_ACCESS_TOKEN else {}
            item.downloaded = _download(url, dest, headers)
    if item.downloaded:
        item.url = str(dest)
    return item


# ---------------------------------------------------------------------------
# Respuestas
# ---------------------------------------------------------------------------

def queue_reply(recipient: str, body: str) -> int:
    oid = storage.insert_outbox("whatsapp", recipient, body)
    storage.audit("A0_WhatsApp", "respuesta_whatsapp_encolada", {"to": recipient, "len": len(body)})
    return oid


def simulate_payload(sender: str, text: str = "", media_kind: str | None = None,
                     caption: str | None = None, latitude: float | None = None,
                     longitude: float | None = None) -> dict:
    """Construye un payload tipo Meta para probar el canal desde la interfaz."""
    msg: dict = {
        "from": sender, "id": "wamid." + uuid.uuid4().hex[:16],
        "timestamp": str(int(time.time())), "type": "text", "text": {"body": text or ""},
    }
    if media_kind in ("image", "video", "audio", "document", "sticker"):
        mime = {"image": "image/jpeg", "video": "video/mp4", "audio": "audio/ogg",
                "document": "application/pdf", "sticker": "image/webp"}[media_kind]
        msg["type"] = media_kind
        msg[media_kind] = {"id": "sim_" + uuid.uuid4().hex[:10], "mime_type": mime,
                           "caption": caption or ""}
    elif latitude is not None and longitude is not None:
        msg["type"] = "location"
        msg["location"] = {"latitude": latitude, "longitude": longitude, "name": "Ubicación en vivo"}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "demo", "changes": [{"value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "507-0000", "phone_number_id": "demo"},
            "contacts": [{"profile": {"name": sender}, "wa_id": sender}],
            "messages": [msg],
        }}]}],
    }


def build_reply(text: str) -> str:
    return text.strip()
