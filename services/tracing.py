"""
Trazas técnicas JSONL: explican CÓMO se ejecutó el sistema (módulo, entrada/salida resumidas,
duración, estado, uso de Gemini o fallback local). No son la auditoría de negocio (services/audit.py).

- Un evento JSON por línea en config.TRACE_PATH.
- Sin secretos ni texto completo del ciudadano: solo ids y resúmenes cortos.
- Integridad: cada línea lleva `hash` = sha256(hash_previo + contenido). Alterar o borrar una línea
  intermedia rompe la cadena y `verificar_integridad()` lo detecta (no impide modificar el archivo;
  lo hace detectable. Truncar el final no es detectable sin anclar el último hash fuera del archivo).
"""

import hashlib
import json
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import config

GENESIS = "0" * 64
_lock = threading.Lock()
_run_id: ContextVar[Optional[str]] = ContextVar("run_id", default=None)
_correlacion: ContextVar[Optional[str]] = ContextVar("correlacion", default=None)

CAMPOS_SENSIBLES = ("key", "token", "password", "secret", "clave")


def resumir(valor: Any, maximo: int = 160) -> Any:
    """Resumen seguro y corto: recorta textos y oculta campos con nombre sensible."""
    if isinstance(valor, dict):
        return {k: ("***" if any(c in k.lower() for c in CAMPOS_SENSIBLES) else resumir(v, maximo))
                for k, v in list(valor.items())[:20]}
    if isinstance(valor, (list, tuple)):
        return [resumir(v, maximo) for v in list(valor)[:10]] + (["…"] if len(valor) > 10 else [])
    if isinstance(valor, str):
        return valor if len(valor) <= maximo else valor[:maximo] + f"…(+{len(valor) - maximo} car.)"
    return valor


def nuevo_run_id() -> str:
    return uuid.uuid4().hex[:12]


@contextmanager
def ejecucion(correlation_id: Optional[str] = None) -> Iterator[str]:
    """Agrupa los eventos de una operación completa (p. ej. 'crear reporte')."""
    previo_run = _run_id.get()
    if previo_run:  # anidado: reutiliza el run_id exterior
        yield previo_run
        return
    rid = nuevo_run_id()
    t1 = _run_id.set(rid)
    t2 = _correlacion.set(correlation_id)
    try:
        yield rid
    finally:
        _run_id.reset(t1)
        _correlacion.reset(t2)


def correlacionar(correlation_id: Any) -> None:
    _correlacion.set(str(correlation_id))


def _ultimo_hash() -> str:
    ruta = config.TRACE_PATH
    if not ruta.exists():
        return GENESIS
    ultima = None
    with open(ruta, "rb") as f:
        for ultima in f:
            pass
    if not ultima or not ultima.strip():
        return GENESIS
    try:
        return json.loads(ultima)["hash"]
    except Exception:
        return GENESIS


def _hash(previo: str, cuerpo: Dict[str, Any]) -> str:
    return hashlib.sha256((previo + json.dumps(cuerpo, sort_keys=True, ensure_ascii=False, default=str)).encode()).hexdigest()


def emitir(agent: str, action: str, status: str = "ok", input_summary: Any = None,
           output_summary: Any = None, tools: Optional[List[str]] = None,
           duration_ms: Optional[float] = None, correlation_id: Optional[str] = None,
           detalle: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cuerpo = {
        "run_id": _run_id.get() or nuevo_run_id(),
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "agent": agent, "action": action, "status": status,
        "input_summary": resumir(input_summary), "output_summary": resumir(output_summary),
        "tools": tools or [], "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "correlation_id": correlation_id or _correlacion.get(),
        "detalle": resumir(detalle or {}),
    }
    with _lock:
        ruta = config.TRACE_PATH
        ruta.parent.mkdir(parents=True, exist_ok=True)
        previo = _ultimo_hash()
        evento = {**cuerpo, "hash_previo": previo, "hash": _hash(previo, cuerpo)}
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
    return evento


@contextmanager
def traza(agent: str, action: str, input_summary: Any = None, tools: Optional[List[str]] = None,
          correlation_id: Optional[str] = None) -> Iterator[Dict[str, Any]]:
    """Mide duración y registra éxito/error. Dentro del bloque: `t["output"] = ...` y
    `t["status"] = "fallback"` si corresponde."""
    t: Dict[str, Any] = {"output": None, "status": "ok", "detalle": {}}
    inicio = time.perf_counter()
    try:
        yield t
    except Exception as e:
        emitir(agent, action, "error", input_summary, {"error": f"{type(e).__name__}: {e}"}, tools,
               (time.perf_counter() - inicio) * 1000, correlation_id, t["detalle"])
        raise
    else:
        emitir(agent, action, t["status"], input_summary, t["output"], tools,
               (time.perf_counter() - inicio) * 1000, correlation_id, t["detalle"])


def leer(run_id: Optional[str] = None, agent: Optional[str] = None, status: Optional[str] = None,
         desde: Optional[str] = None, hasta: Optional[str] = None,
         correlation_id: Optional[str] = None) -> List[Dict[str, Any]]:
    ruta = config.TRACE_PATH
    if not ruta.exists():
        return []
    eventos = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            try:
                e = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if run_id and e.get("run_id") != run_id:
                continue
            if agent and e.get("agent") != agent:
                continue
            if status and e.get("status") != status:
                continue
            if correlation_id and e.get("correlation_id") != str(correlation_id):
                continue
            if desde and e.get("timestamp", "") < desde:
                continue
            if hasta and e.get("timestamp", "") > hasta:
                continue
            eventos.append(e)
    return eventos


def verificar_integridad() -> Dict[str, Any]:
    """Recorre la cadena. Devuelve {'integra': bool, 'eventos': n, 'linea_rota': n|None}."""
    ruta = config.TRACE_PATH
    if not ruta.exists():
        return {"integra": True, "eventos": 0, "linea_rota": None}
    previo, n = GENESIS, 0
    with open(ruta, encoding="utf-8") as f:
        for i, linea in enumerate(f, 1):
            if not linea.strip():
                continue
            try:
                e = json.loads(linea)
                cuerpo = {k: v for k, v in e.items() if k not in ("hash", "hash_previo")}
                if e["hash_previo"] != previo or e["hash"] != _hash(previo, cuerpo):
                    return {"integra": False, "eventos": n, "linea_rota": i}
                previo = e["hash"]
            except Exception:
                return {"integra": False, "eventos": n, "linea_rota": i}
            n += 1
    return {"integra": True, "eventos": n, "linea_rota": None}
