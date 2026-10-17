"""Métricas de equidad y deprivación (código determinista, nunca el LLM).

- `deprivation`: costo social estilo Holguín-Veras (crece más rápido que lineal).
- `gini`: desigualdad de las horas sin agua entre sectores, ponderada por población.
- `coverage`: litros por persona frente al mínimo de Sphere (15 L/persona/día).
"""
from __future__ import annotations

from typing import Iterable

SPHERE_MIN_LITERS_PER_PERSON = 15.0
BETA = 0.08  # supuesto de demo: cada hora de privación pesa más que la anterior


def deprivation(hours_without_water: float, population: int, vulnerability: float,
                weight: float = 1.0) -> float:
    import math
    return population * vulnerability * weight * (math.exp(BETA * hours_without_water) - 1.0)


def gini(values: Iterable[float], weights: Iterable[float] | None = None) -> float:
    """Gini ponderado. 0 = perfectamente igual; 1 = máxima desigualdad."""
    vals = list(values)
    wts = list(weights) if weights is not None else [1.0] * len(vals)
    pairs = [(v, w) for v, w in zip(vals, wts) if w > 0]
    if len(pairs) < 2:
        return 0.0
    total_w = sum(w for _, w in pairs)
    mean = sum(v * w for v, w in pairs) / total_w
    if mean <= 0:
        return 0.0
    diff = 0.0
    for v1, w1 in pairs:
        for v2, w2 in pairs:
            diff += w1 * w2 * abs(v1 - v2)
    return diff / (2 * total_w * total_w * mean)


def coverage_ok(liters: int, population: int) -> bool:
    return population > 0 and (liters / population) >= SPHERE_MIN_LITERS_PER_PERSON
