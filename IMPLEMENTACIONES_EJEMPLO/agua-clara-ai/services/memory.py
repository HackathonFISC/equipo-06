"""Memoria y aprendizaje continuo de los agentes.

No es un fine-tuning: es una MEMORIA operativa que crece con cada corrección
humana y con un corpus semilla. Guarda un JSONL append-only en data/memory.jsonl
y mantiene cachés en proceso para que los agentes resuelvan más rápido y mejor
con el uso.

Tipos de entrada:
  - correction: {"wrong": "bista alegre", "right": "vista alegre"}
  - alias:      {"sector_id": "S01", "hint": "detras del chino"}
  - slang:      {"term": "no hay ni gota", "intent": "sin_agua"}
  - resolution: {"hint": "...", "sector_id": "S04"}   (aprendido al confirmar)

Todo es auditable: cada línea lleva ts, tipo, origen y peso.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from config import DATA_DIR, now_iso

MEMORY_PATH: Path = DATA_DIR / "memory.jsonl"
SEED_CORPUS_PATH: Path = DATA_DIR / "seed_corpus.json"

_LOCK = threading.Lock()
_CORRECTIONS: dict[str, str] | None = None
_ALIASES: dict[str, set[str]] = {}
_SLANG: dict[str, str] = {}
_COUNT = 0


def reload() -> None:
    """Reconstruye las cachés desde el JSONL (llamar tras entrenar)."""
    global _CORRECTIONS, _ALIASES, _SLANG, _COUNT
    corrections: dict[str, str] = {}
    aliases: dict[str, set[str]] = {}
    slang: dict[str, str] = {}
    count = 0
    if MEMORY_PATH.exists():
        for line in MEMORY_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            count += 1
            kind = rec.get("type")
            if kind == "correction" and rec.get("wrong") and rec.get("right"):
                corrections[_norm(rec["wrong"])] = rec["right"]
            elif kind in ("alias", "resolution") and rec.get("sector_id") and rec.get("hint"):
                aliases.setdefault(rec["sector_id"], set()).add(_norm(rec["hint"]))
            elif kind == "slang" and rec.get("term") and rec.get("intent"):
                slang[_norm(rec["term"])] = rec["intent"]
    _CORRECTIONS, _ALIASES, _SLANG, _COUNT = corrections, aliases, slang, count


def _norm(text: str) -> str:
    import re
    text = (text or "").lower()
    text = re.sub(r"[^a-záéíóúñ0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ensure() -> None:
    if _CORRECTIONS is None:
        reload()


def _append(record: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": now_iso(), **record}
    with _LOCK:
        with MEMORY_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Escritura (aprendizaje)
# ---------------------------------------------------------------------------

def learn_correction(wrong: str, right: str, origin: str = "humano") -> None:
    _ensure()
    if not wrong or not right or _norm(wrong) == _norm(right):
        return
    if _CORRECTIONS.get(_norm(wrong)) == right:
        return  # ya conocido: no duplicar la entrada en el archivo
    _append({"type": "correction", "wrong": wrong, "right": right, "origin": origin})
    _CORRECTIONS[_norm(wrong)] = right


def learn_alias(sector_id: str, hint: str, origin: str = "humano") -> None:
    _ensure()
    if not sector_id or not hint:
        return
    if _norm(hint) in _ALIASES.get(sector_id, set()):
        return  # ya conocido: idempotente
    _append({"type": "alias", "sector_id": sector_id, "hint": hint, "origin": origin})
    _ALIASES.setdefault(sector_id, set()).add(_norm(hint))


def learn_resolution(hint: str, sector_id: str, origin: str = "confirmacion") -> None:
    _ensure()
    if not hint or not sector_id:
        return
    if _norm(hint) in _ALIASES.get(sector_id, set()):
        return  # ya conocido: idempotente
    _append({"type": "resolution", "hint": hint, "sector_id": sector_id, "origin": origin})
    _ALIASES.setdefault(sector_id, set()).add(_norm(hint))


def learn_slang(term: str, intent: str, origin: str = "humano") -> None:
    _ensure()
    if not term or not intent:
        return
    if _SLANG.get(_norm(term)) == intent:
        return  # ya conocido: idempotente
    _append({"type": "slang", "term": term, "intent": intent, "origin": origin})
    _SLANG[_norm(term)] = intent


# ---------------------------------------------------------------------------
# Lectura (los agentes consultan esto)
# ---------------------------------------------------------------------------

def corrections() -> dict[str, str]:
    _ensure()
    return dict(_CORRECTIONS)


def aliases_for(sector_id: str) -> set[str]:
    _ensure()
    return set(_ALIASES.get(sector_id, set()))


def all_aliases() -> dict[str, list[str]]:
    _ensure()
    return {k: sorted(v) for k, v in _ALIASES.items()}


def slang() -> dict[str, str]:
    _ensure()
    return dict(_SLANG)


def stats() -> dict:
    _ensure()
    return {
        "entradas_totales": _COUNT,
        "correcciones": len(_CORRECTIONS),
        "sectores_con_alias": len(_ALIASES),
        "alias_totales": sum(len(v) for v in _ALIASES.values()),
        "jerga": len(_SLANG),
        "archivo": str(MEMORY_PATH),
    }


def ensure_trained() -> dict:
    """Garantiza que la memoria esté cargada y entrenada (corpus semilla).

    Se usa al arrancar la app y antes de correr los evals, para que el sistema
    funcione igual en una máquina recién instalada.
    """
    _ensure()
    if _CORRECTIONS and _ALIASES and _SLANG:
        return {"ok": True, "ya_entrenado": True, "stats": stats()}
    out = train_from_corpus()
    if not out.get("ok"):
        return {"ok": False, **out, "stats": stats()}
    return out


def reset() -> None:
    """Vacía la memoria (útil para demos reproducibles)."""
    if MEMORY_PATH.exists():
        MEMORY_PATH.unlink()
    reload()


# ---------------------------------------------------------------------------
# Entrenamiento desde corpus semilla
# ---------------------------------------------------------------------------

def train_from_corpus(path: Path | None = None) -> dict:
    """'Entrena' el sistema cargando ejemplos panameños (correcciones, alias, jerga)."""
    path = path or SEED_CORPUS_PATH
    if not path.exists():
        return {"ok": False, "error": f"no existe {path}"}
    data = json.loads(path.read_text(encoding="utf-8"))
    n_corr = n_alias = n_slang = 0
    for item in data.get("corrections", []):
        learn_correction(item["wrong"], item["right"], origin="corpus")
        n_corr += 1
    for item in data.get("aliases", []):
        learn_alias(item["sector_id"], item["hint"], origin="corpus")
        n_alias += 1
    for item in data.get("slang", []):
        learn_slang(item["term"], item["intent"], origin="corpus")
        n_slang += 1
    reload()
    return {"ok": True, "correcciones": n_corr, "alias": n_alias, "jerga": n_slang,
            "stats": stats()}


reload()
