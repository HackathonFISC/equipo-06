"""poseidon_core.store · persistencia de lecturas hidroacústicas.

Backend por defecto: la base SQLite del propio proyecto (sin dependencias extra).
Backend opcional: Supabase, activo solo si se configuran ``SUPABASE_URL`` y
``SUPABASE_KEY`` y el paquete ``supabase`` está instalado. En ese caso se usa la
tabla ``reportes_hidricos`` (crearla con el SQL de la documentación).

Cualquier fallo de Supabase cae de vuelta a SQLite: la lectura nunca se pierde.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def _cliente_supabase():  # pragma: no cover - depende de credenciales
    url = os.getenv("SUPABASE_URL", "")
    clave = os.getenv("SUPABASE_KEY", "")
    if not url or not clave:
        return None
    try:
        from supabase import create_client, Client  # type: ignore
        return create_client(url, clave)
    except Exception:
        return None


class AlmacenHidrico:
    """Adapter de persistencia de lecturas (Supabase si existe; si no, SQLite)."""

    TABLA_SUPABASE = "reportes_hidricos"

    def __init__(self) -> None:
        self._supabase = _cliente_supabase()

    @property
    def backend(self) -> str:
        return "supabase" if self._supabase is not None else "sqlite"

    # ---------------- escritura ----------------
    def guardar_lectura(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        registro = {
            "created_at": datos.get("created_at"),
            "phone": datos.get("phone"),
            "sector_id": datos.get("sector_id"),
            "barriada": datos.get("barriada"),
            "tipo": datos.get("tipo"),
            "estado": datos.get("estado"),
            "confianza": float(datos.get("confianza") or 0.0),
            "segundo": int(datos.get("segundo") or 0),
            "meta": dict(datos.get("meta") or {}),
        }
        if self._supabase is not None:
            try:
                fila = {k: v for k, v in registro.items() if v is not None and k != "created_at"}
                fila["created_at"] = registro["created_at"] or _now_iso()
                self._supabase.table(self.TABLA_SUPABASE).insert(fila).execute()
                registro["backend"] = "supabase"
                return registro
            except Exception:
                # si Supabase falla, persistimos igualmente en SQLite
                pass
        from services import storage  # import perezoso: evita ciclos
        registro["id"] = storage.insert_hydro_reading(registro)
        registro["backend"] = "sqlite"
        return registro

    # ---------------- lectura ----------------
    def lecturas_recientes(self, sector_id: Optional[str], minutos: int = 30) -> List[Dict[str, Any]]:
        if self._supabase is not None and sector_id:
            try:
                res = (self._supabase.table(self.TABLA_SUPABASE)
                       .select("*").eq("sector_id", sector_id)
                       .order("created_at", desc=True).limit(50).execute())
                filas = res.data or []
                corte = _now_iso_delta(-minutos)
                return [f for f in filas if (f.get("created_at") or "") >= corte]
            except Exception:
                pass
        from services import storage
        return storage.list_hydro_readings(sector_id=sector_id, minutes=minutos, limit=100)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _now_iso_delta(minutos: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(minutes=minutos)).isoformat()


# Instancia compartida por el router y el orquestador.
ALMACEN = AlmacenHidrico()
