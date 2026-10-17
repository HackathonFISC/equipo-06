"""
Proveedor Gemini (SDK oficial `google-genai`). Único punto de contacto con el servicio externo.

Garantías:
  - Opcional: si falta GEMINI_API_KEY o el paquete, `generar_json` lanza ErrorIA y quien llama usa el modo local.
  - La clave sale solo de la variable de entorno; nunca se registra ni se devuelve.
  - Tiempo máximo por llamada (AI_TIMEOUT_SECONDS) y reintento prudente: como máximo AI_MAX_REINTENTOS,
    solo para errores transitorios (5xx, timeout, red). Cuota agotada (429) o credenciales inválidas NO
    se reintentan.
  - Corte de circuito: tras un 429 se suspenden las llamadas 60 s; tras un 401/403, 15 min; tras 3 fallos
    seguidos, 60 s. Así no se martilla al proveedor ni se gasta cuota.
  - Presupuesto de tiempo opcional (`presupuesto(segundos)`): un límite TOTAL para un conjunto de llamadas
    (p. ej. un análisis completo en una función serverless). Si queda menos de MINIMO_UTIL_S (10 s, mínimo que
    acepta la API) la llamada no se intenta (ErrorIA) y el llamador usa el modo local; el plazo de cada llamada
    se recorta al tiempo restante.
  - Cada llamada deja una traza (proveedor, modelo, versión del esquema de salida, estado, duración, tokens si
    el SDK los informa) SIN contenido del ciudadano, imágenes ni secretos.
  - Esta capa NO importa services.workflow ni escribe en la base: solo devuelve texto (ver docs/IA_GEMINI.md).
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, List, Optional, Tuple

import config
from services import tracing


class ErrorIA(Exception):
    """El proveedor de IA no está disponible o falló; el llamador debe usar el modo local."""


_suspendido_hasta = 0.0
_motivo_suspension = ""
_fallos_seguidos = 0

# Versión del esquema de salida que se le exige al modelo, por tarea (queda en la traza).
VERSION_ESQUEMA = {"interpretar": "SalidaIA/2", "recomendar": "SalidaRecomendacion/1",
                   "resumen": "resumen/1", "borrador": "texto/1", "contexto": "texto/1", "patrones": "texto/1"}
# La API de Gemini rechaza (HTTP 400, comprobado con el servicio real) plazos menores de 10 s: con menos tiempo
# restante que esto no se intenta ninguna llamada y el llamador usa el modo local.
MINIMO_UTIL_S = 10.0

_limite: ContextVar[Optional[float]] = ContextVar("ia_limite", default=None)


@contextmanager
def presupuesto(segundos: float) -> Iterator[None]:
    """Límite total de tiempo para las llamadas hechas dentro del bloque. Anidado, manda el más estricto."""
    nuevo = time.monotonic() + max(0.0, float(segundos))
    previo = _limite.get()
    token = _limite.set(nuevo if previo is None else min(previo, nuevo))
    try:
        yield
    finally:
        _limite.reset(token)


def tiempo_restante() -> Optional[float]:
    """Segundos que quedan del presupuesto activo, o None si no hay presupuesto."""
    lim = _limite.get()
    return None if lim is None else max(0.0, lim - time.monotonic())


def reiniciar_estado() -> None:
    """Solo para pruebas y para el botón «reintentar» de la interfaz."""
    global _suspendido_hasta, _motivo_suspension, _fallos_seguidos
    _suspendido_hasta, _motivo_suspension, _fallos_seguidos = 0.0, "", 0


def _suspender(segundos: float, motivo: str) -> None:
    global _suspendido_hasta, _motivo_suspension
    _suspendido_hasta = time.monotonic() + segundos
    _motivo_suspension = motivo


def estado() -> dict:
    """Estado seguro para mostrar (sin clave)."""
    restante = max(0.0, _suspendido_hasta - time.monotonic())
    return {"proveedor": config.ai_provider(), "modelo": config.GEMINI_MODEL(),
            "clave_configurada": bool(config.GEMINI_API_KEY()),
            "suspendido_s": round(restante), "motivo_suspension": _motivo_suspension if restante else ""}


def _cliente():
    clave = config.GEMINI_API_KEY()
    if not clave:
        raise ErrorIA("Falta GEMINI_API_KEY")
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:  # paquete no instalado
        raise ErrorIA("Paquete google-genai no instalado") from e
    opciones = types.HttpOptions(timeout=int(config.AI_TIMEOUT_SECONDS() * 1000))
    return genai.Client(api_key=clave, http_options=opciones), types


def _uso(r) -> dict:
    """Tokens que informa el SDK (solo enteros; nada del contenido). Vacío si no los da."""
    um = getattr(r, "usage_metadata", None)
    uso = {}
    for clave, attr in (("entrada", "prompt_token_count"), ("salida", "candidates_token_count"),
                        ("total", "total_token_count")):
        v = getattr(um, attr, None)
        if isinstance(v, int) and not isinstance(v, bool):
            uso[clave] = v
    return {"uso": uso} if uso else {}


def _clasificar(e: Exception) -> Tuple[Optional[int], bool]:
    """(código HTTP si lo hay, ¿transitorio?)."""
    codigo = getattr(e, "code", None)
    if isinstance(codigo, int):
        return codigo, codigo >= 500 or codigo == 408
    nombre = type(e).__name__.lower()
    return None, any(x in nombre for x in ("timeout", "connect", "network", "protocol", "read"))


def generar_json(sistema: str, usuario: str, tarea: str = "interpretar", temperatura: float = 0.0) -> str:
    """Devuelve el TEXTO JSON producido por el modelo (el llamador lo valida con Pydantic)."""
    global _fallos_seguidos
    if time.monotonic() < _suspendido_hasta:
        raise ErrorIA(f"Gemini suspendido temporalmente ({_motivo_suspension})")
    if (tiempo_restante() or MINIMO_UTIL_S) < MINIMO_UTIL_S:
        raise ErrorIA("presupuesto de tiempo del análisis agotado: se usa el modo local")
    cliente, types = _cliente()
    modelo = config.GEMINI_MODEL()
    intentos = 1 + max(0, config.AI_MAX_REINTENTOS())
    ultimo: Optional[Exception] = None
    with tracing.traza("ia", f"gemini.{tarea}", {"modelo": modelo, "caracteres_entrada": len(usuario)},
                       tools=["google-genai"]) as t:
        t["detalle"] = {"proveedor": "gemini", "modelo": modelo, "esquema_salida": VERSION_ESQUEMA.get(tarea, "json/1")}
        for n in range(1, intentos + 1):
            try:
                extra = {}
                resto = tiempo_restante()
                if resto is not None and resto < config.AI_TIMEOUT_SECONDS() and hasattr(types, "HttpOptions"):
                    extra["http_options"] = types.HttpOptions(timeout=int(max(MINIMO_UTIL_S, resto) * 1000))
                r = cliente.models.generate_content(
                    model=modelo, contents=usuario,
                    config=types.GenerateContentConfig(system_instruction=sistema, temperature=temperatura,
                                                       response_mime_type="application/json", **extra))
                texto = r.text
                if not texto or not texto.strip():
                    raise ErrorIA("Respuesta vacía (posible bloqueo de seguridad del proveedor)")
                _fallos_seguidos = 0
                t["output"] = {"caracteres_salida": len(texto), "intentos": n, **_uso(r)}
                return texto
            except ErrorIA:
                raise
            except Exception as e:  # SDK: ClientError/ServerError/timeouts de red
                ultimo = e
                codigo, transitorio = _clasificar(e)
                if codigo == 429:
                    _suspender(60, "cuota o límite de uso agotado (429)")
                    break
                if codigo in (401, 403):
                    _suspender(900, "credenciales rechazadas (401/403)")
                    break
                if transitorio and n < intentos:
                    pausa = 1.5 * n
                    if (tiempo_restante() is not None) and tiempo_restante() < pausa + MINIMO_UTIL_S:
                        break  # no queda tiempo para reintentar dentro del presupuesto
                    time.sleep(pausa)
                    continue
                break
        _fallos_seguidos += 1
        if _fallos_seguidos >= 3:
            _suspender(60, "3 fallos seguidos")
        codigo, _ = _clasificar(ultimo) if ultimo else (None, False)
        t["status"] = "error"
        t["output"] = {"error_tipo": type(ultimo).__name__, "http": codigo}
        raise ErrorIA(f"Gemini falló ({type(ultimo).__name__}{f' HTTP {codigo}' if codigo else ''})")


def listar_modelos() -> List[str]:
    """Para el comando de verificación: nombres de modelos que admiten generateContent."""
    cliente, _ = _cliente()
    salida = []
    for m in cliente.models.list():
        acciones = getattr(m, "supported_actions", None) or []
        if not acciones or "generateContent" in acciones:
            salida.append((getattr(m, "name", "") or "").replace("models/", ""))
    return sorted(salida)
