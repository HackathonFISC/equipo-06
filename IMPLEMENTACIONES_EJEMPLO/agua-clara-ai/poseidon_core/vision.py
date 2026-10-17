"""poseidon_core.vision · análisis visual de infraestructura hidráulica.

Analiza una foto (tubería, unión de PVC o medidor residencial) y devuelve un
estado hidráulico estructurado. Estrategia de proveedores, en orden:

1. ``openai`` con ``gpt-4o`` y ``response_format={"type": "json_object"}``
   (si está instalado y hay ``api_key`` o ``OPENAI_API_KEY``).
2. El cliente multimodal del propio proyecto (``services.llm.vision_chat``),
   que ya soporta xAI/Grok, Gemini y OpenAI con la misma interfaz.
3. Sin proveedor: degrada a ``desconocido`` sin romper y deja la imagen
   registrada para revisión humana (nunca inventa un diagnóstico).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PROMPT_ESTRICTO: str = (
    "Eres un inspector hidráulico experto de Panamá Oeste. Observa la imagen de "
    "una tubería, unión de PVC o medidor residencial y clasifica el estado con "
    "rigor técnico:\n"
    "- 'aire': hay señales de aire en la red (condensación/vibración anómala en "
    "uniones, ausencia de agua en el interior, medidor que no gira).\n"
    "- 'flujo_normal': se observa agua circulando con normalidad (medidor girando, "
    "tubería llena, sin anomalías).\n"
    "- 'seco': la toma está cerrada o la tubería está seca sin señal de presión.\n"
    "Responde EXCLUSIVAMENTE en JSON válido con esta forma exacta: "
    '{"estado": "seco"|"aire"|"flujo_normal", "confianza": 0.0-1.0, "observacion": "breve"}. '
    "No agregues texto fuera del JSON."
)


def _es_url(valor: str) -> bool:
    return valor.startswith(("http://", "https://"))


def _a_data_uri_para_local(path: str) -> Tuple[str, str]:
    p = Path(path)
    mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}", mime


def _parsear_json(texto: str) -> Dict[str, Any]:
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except Exception:
        s, e = texto.find("{"), texto.rfind("}")
        if s != -1 and e != -1:
            try:
                return json.loads(texto[s:e + 1])
            except Exception:
                return {}
        return {}


def _normalizar(datos: Dict[str, Any], proveedor: str) -> Dict[str, Any]:
    estado = str(datos.get("estado", "desconocido")).strip().lower()
    if estado not in ("seco", "aire", "flujo_normal"):
        estado = "desconocido"
    try:
        confianza = float(datos.get("confianza", 0.0))
    except Exception:
        confianza = 0.0
    return {
        "estado": estado,
        "confianza": max(0.0, min(1.0, round(confianza, 3))),
        "observacion": str(datos.get("observacion") or "").strip()[:400],
        "proveedor": proveedor,
    }


def _con_openai(image_url: str, api_key: str) -> Dict[str, Any]:
    from openai import OpenAI  # type: ignore

    cliente = OpenAI(api_key=api_key)
    if _es_url(image_url):
        fuente = {"type": "image_url", "image_url": {"url": image_url}}
    else:
        data_uri, _ = _a_data_uri_para_local(image_url)
        fuente = {"type": "image_url", "image_url": {"url": data_uri}}
    resp = cliente.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": PROMPT_ESTRICTO},
            {"role": "user", "content": [
                {"type": "text", "text": "Clasifica el estado hidráulico de esta imagen."},
                fuente,
            ]},
        ],
        max_tokens=300,
    )
    texto = resp.choices[0].message.content or ""
    return _normalizar(_parsear_json(texto), "openai:gpt-4o")


def _con_llm_proyecto(image_url: str) -> Optional[Dict[str, Any]]:
    """Usa el cliente multimodal del propio proyecto (xAI/Gemini/OpenAI)."""
    try:
        from services import llm  # type: ignore
    except Exception:
        return None
    if not getattr(llm, "available", lambda: False)():
        return None
    try:
        if _es_url(image_url):
            url = image_url
        else:
            url, _ = _a_data_uri_para_local(image_url)
        contenido = [
            {"type": "text", "text": "Clasifica el estado hidráulico de esta imagen."},
            {"type": "image_url", "image_url": {"url": url}},
        ]
        crudo = llm.vision_chat([
            {"role": "system", "content": PROMPT_ESTRICTO},
            {"role": "user", "content": contenido},
        ])
        if crudo:
            proveedor = getattr(llm, "active_provider", lambda: "llm")()
            return _normalizar(_parsear_json(crudo), f"proyecto:{proveedor}")
    except Exception:
        return None
    return None


def analizar_infraestructura_visual(image_url: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Clasifica el estado hidráulico de una foto de tubería/medidor.

    Args:
        image_url: URL http(s), ruta local o data-URI.
        api_key: clave de OpenAI; si es ``None`` se intenta ``OPENAI_API_KEY``.

    Returns:
        ``{"estado", "confianza", "observacion", "proveedor"}``. Nunca lanza:
        si algo falla, ``estado`` es ``"desconocido"`` y se explica en
        ``observacion``.
    """
    if not image_url:
        return _normalizar({"estado": "desconocido", "confianza": 0.0,
                            "observacion": "No se recibió imagen."}, "sin_fuente")

    clave = api_key or os.getenv("OPENAI_API_KEY", "")

    # 1) cliente oficial de OpenAI (gpt-4o)
    if clave:
        try:
            return _con_openai(image_url, clave)
        except Exception as exc:  # noqa: BLE001
            openai_error = str(exc)
    else:
        openai_error = ""

    # 2) cliente multimodal del proyecto
    res = _con_llm_proyecto(image_url)
    if res is not None:
        return res

    # 3) degradación honesta
    nota = "Sin proveedor de visión configurado; imagen registrada para revisión humana."
    if openai_error:
        nota = f"Fallo del proveedor OpenAI ({openai_error}); imagen registrada para revisión humana."
    return _normalizar({"estado": "desconocido", "confianza": 0.0, "observacion": nota}, "ninguno")
