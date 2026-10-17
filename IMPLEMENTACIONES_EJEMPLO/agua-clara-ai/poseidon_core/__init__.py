"""Proyecto Poseidón · núcleo de percepción hidráulica pasiva.

Módulo autocontenido que se integra a Agua Clara AI (FastAPI + SQLite) sin
romper la arquitectura existente. Cada submódulo degrada con elegancia si falta
una dependencia opcional:

- ``audio``   : analiza el sonido de un grifo/tubería (aire vs. agua vs. seco).
- ``vision``  : analiza fotos de tuberías, uniones y medidores.
- ``agents``  : enjambre de agentes que valida alertas colectivas por sector.
- ``store``   : persiste las lecturas (Supabase si está configurado; si no, SQLite).
- ``route``   : router de FastAPI listo para ``app.include_router``.

Filosofía: 100% determinista donde se puede (DSP) y LLM solo donde aporta.
Ninguna alerta sale hacia el ciudadano sin quedar registrada y auditable.
"""
from __future__ import annotations

__all__ = ["audio", "vision", "agents", "store", "route"]
__version__ = "1.0.0"
