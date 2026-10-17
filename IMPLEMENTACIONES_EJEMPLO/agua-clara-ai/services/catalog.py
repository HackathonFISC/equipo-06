"""Carga del catálogo de sectores, cisternas y puntos de llenado (data/sectors.json)."""
from __future__ import annotations

import json
from functools import lru_cache

from config import DATA_DIR
from schemas import FillingPoint, Sector, Tanker

CATALOG_PATH = DATA_DIR / "sectors.json"
LANDMARKS_PATH = DATA_DIR / "landmarks.json"


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _raw_landmarks() -> dict:
    if not LANDMARKS_PATH.exists():
        return {"landmarks": []}
    return json.loads(LANDMARKS_PATH.read_text(encoding="utf-8"))


def sectors() -> list[Sector]:
    return [Sector(**s) for s in _raw()["sectors"]]


def sectors_by_id() -> dict[str, Sector]:
    return {s.id: s for s in sectors()}


def tankers() -> list[Tanker]:
    return [Tanker(**t) for t in _raw()["tankers"]]


def filling_points() -> list[FillingPoint]:
    return [FillingPoint(**f) for f in _raw()["filling_points"]]


def reload() -> None:
    _raw.cache_clear()
    _raw_landmarks.cache_clear()


def landmarks() -> list[dict]:
    """Referencias locales (\"detrás del hospital\", \"la cancha\"...) para
    resolver ubicaciones ambiguas aprendidas del lenguaje coloquial."""
    return list(_raw_landmarks().get("landmarks", []))
