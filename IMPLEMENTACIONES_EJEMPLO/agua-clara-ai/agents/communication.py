"""A7 · Comunicación — redacta avisos por sector a partir de datos confirmados.

Reglas:
- Nunca inventa datos. Si no hay ETA confirmada, no promete hora.
- El aviso solo se genera/enviía DESPUÉS de la aprobación humana.
- Con LLM disponible, redacta en lenguaje sencillo sobre una plantilla; un
  verificador comprueba que cada número del texto exista en los datos. Si no,
  se usa la plantilla fija. El envío real es un efecto lateral (outbox/Telegram).
"""
from __future__ import annotations

import re

from config import env, llm_available
from services import llm, storage
from services.traces import log_step

AGENT = "A7_Comunicacion"


def _template(sector_name: str, liters: int, eta_minutes: int | None) -> str:
    eta = f"Llegada estimada en {eta_minutes} minutos." if eta_minutes is not None else "Hora de llegada por confirmar."
    return (f"AVISO (pendiente de aprobación): al sector {sector_name} se le asignaron {liters:,} litros "
            f"de agua potable. {eta} Guarde recipientes limpios y priorice a personas mayores y con "
            f"discapacidad. Este aviso no es una orden de servicio.")


def draft(sector_name: str, liters: int, eta_minutes: int | None, run_id: str = "run_ad_hoc") -> str:
    text = _template(sector_name, liters, eta_minutes)
    if llm_available():
        rewritten = llm.chat([
            {"role": "system", "content": "Reescribe este aviso en español sencillo, máximo 3 frases. "
                                          "No cambies ni agregues números, nombres ni horas."},
            {"role": "user", "content": text},
        ])
        if rewritten and _numbers_consistent(rewritten, liters, eta_minutes):
            text = rewritten.strip()
    log_step(run_id, AGENT, "borrador_aviso", {"sector": sector_name, "liters": liters},
             {"preview": text[:120]}, tools=["plantilla", "verificador_numerico"],
             decision="redactado")
    return text


def _numbers_consistent(text: str, liters: int, eta_minutes: int | None) -> bool:
    flat = text.replace(",", "")
    found = set(int(n) for n in re.findall(r"\d+", flat))
    allowed = {liters}
    if eta_minutes is not None:
        allowed.add(eta_minutes)
    # Aceptamos números pequeños de estilo ("2 frases"); rechazamos cifras inventadas grandes.
    return all(n <= 5 or n in allowed for n in found)


def send(channel: str, recipient: str, body: str, run_id: str = "run_ad_hoc") -> dict:
    """Herramienta que ACTÚA: intenta enviar de verdad y siempre deja registro."""
    token = env("AGUA_TELEGRAM_TOKEN")
    chat_id = env("AGUA_TELEGRAM_CHAT_ID") or recipient
    status = "pendiente"
    if channel == "telegram" and token and chat_id:
        status = _telegram_send(token, chat_id, body)
    else:
        status = "simulado_sin_credenciales"
    oid = storage.insert_outbox(channel, recipient, body, status)
    log_step(run_id, AGENT, "envio", {"channel": channel, "recipient": recipient},
             {"outbox_id": oid, "status": status}, tools=["outbox", "telegram_api" if token else "sin_token"],
             decision=status)
    return {"outbox_id": oid, "status": status}


def _telegram_send(token: str, chat_id: str, body: str) -> str:
    import json
    import urllib.parse
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": body}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            json.loads(resp.read().decode("utf-8"))
        return "enviado"
    except Exception:
        return "error_envio"
