"""Trazabilidad: una línea JSON por paso de agente.

Permite responder "¿qué agente tomó cada decisión, con qué entrada y qué
herramientas llamó?" sin depender de Langfuse ni de servicios externos.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from config import TRACE_PATH, stable_hash


def new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:10]


def log_step(run_id: str, agent: str, step: str, input_obj: Any, output_obj: Any,
             tools: list[str] | None = None, latency_ms: float = 0.0, decision: str = "") -> None:
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id": run_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agent": agent,
        "step": step,
        "input_hash": stable_hash(json.dumps(input_obj, ensure_ascii=False, default=str)) if input_obj is not None else None,
        "output_summary": _summarize(output_obj),
        "tools": tools or [],
        "latency_ms": round(latency_ms, 1),
        "decision": decision,
    }
    with TRACE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _summarize(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj[:200]
    if isinstance(obj, dict):
        return {k: _summarize(v) for k, v in list(obj.items())[:12]}
    if isinstance(obj, list):
        return f"lista[{len(obj)}]"
    return str(obj)[:200]


def read_traces(limit: int = 200) -> list[dict]:
    if not TRACE_PATH.exists():
        return []
    lines = TRACE_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(out))
