"""
Persistencia local con SQLite (stdlib). Sin ORM: tablas simples y contratos Pydantic.

Cada función abre una conexión corta; la base es un solo archivo (config.DB_PATH),
fácil de copiar a una Raspberry Pi.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sectores (
    nombre TEXT PRIMARY KEY, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cisternas (
    id TEXT PRIMARY KEY, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reportes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS planes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisiones_duplicado (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usuarios (
    id TEXT PRIMARY KEY, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fotos (
    id TEXT PRIMARY KEY, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dispositivos (
    id TEXT PRIMARY KEY, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS misiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS eventos_mision (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recomendaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datos TEXT NOT NULL);
"""

# `usuarios`, `dispositivos` y `fotos` NO están aquí: reiniciar la demo no debe borrar cuentas, identidades
# de terminales ni archivos subidos. Misiones/eventos/recomendaciones sí se reinician con los datos de ejemplo.
TABLAS = ["sectores", "cisternas", "reportes", "planes", "decisiones_duplicado", "auditoria",
          "misiones", "eventos_mision", "recomendaciones"]


_local = threading.local()


def _abrir() -> sqlite3.Connection:
    con = sqlite3.connect(str(config.DB_PATH), timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


@contextmanager
def transaccion() -> Iterator[sqlite3.Connection]:
    """Agrupa varias operaciones (cambio de negocio + auditoría) en UNA transacción atómica.
    BEGIN IMMEDIATE serializa escritores; si algo falla se revierte todo. Es reentrante."""
    if getattr(_local, "con", None) is not None:
        yield _local.con
        return
    con = _abrir()
    _local.con = con
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        _local.con = None
        con.close()


@contextmanager
def conexion() -> Iterator[sqlite3.Connection]:
    activa = getattr(_local, "con", None)
    if activa is not None:  # dentro de transaccion(): la confirma el contexto externo
        yield activa
        return
    con = _abrir()
    try:
        con.execute("BEGIN")
        yield con
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def _dump(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, default=str)


def insertar(tabla: str, datos: Dict[str, Any], clave: Optional[str] = None) -> Any:
    """Inserta un documento. Si la tabla usa clave de texto, `clave` es obligatoria.
    Devuelve el id (autoincremental o la clave)."""
    with conexion() as con:
        if clave is not None:
            col = "nombre" if tabla == "sectores" else "id"
            con.execute(f"INSERT OR REPLACE INTO {tabla} ({col}, datos) VALUES (?, ?)", (clave, _dump(datos)))
            return clave
        cur = con.execute(f"INSERT INTO {tabla} (datos) VALUES (?)", ("{}",))
        nuevo_id = cur.lastrowid
        datos = {**datos, "id": nuevo_id}
        con.execute(f"UPDATE {tabla} SET datos = ? WHERE id = ?", (_dump(datos), nuevo_id))
        return nuevo_id


def actualizar(tabla: str, clave: Any, datos: Dict[str, Any]) -> None:
    col = "nombre" if tabla == "sectores" else "id"
    with conexion() as con:
        con.execute(f"UPDATE {tabla} SET datos = ? WHERE {col} = ?", (_dump(datos), clave))


def obtener(tabla: str, clave: Any) -> Optional[Dict[str, Any]]:
    col = "nombre" if tabla == "sectores" else "id"
    with conexion() as con:
        fila = con.execute(f"SELECT datos FROM {tabla} WHERE {col} = ?", (clave,)).fetchone()
    return json.loads(fila["datos"]) if fila else None


def listar(tabla: str) -> List[Dict[str, Any]]:
    orden = "nombre" if tabla == "sectores" else "id"
    with conexion() as con:
        filas = con.execute(f"SELECT datos FROM {tabla} ORDER BY {orden}").fetchall()
    return [json.loads(f["datos"]) for f in filas]


def vaciar(tablas: Optional[List[str]] = None) -> None:
    with conexion() as con:
        for t in tablas or TABLAS:
            con.execute(f"DELETE FROM {t}")
            con.execute("DELETE FROM sqlite_sequence WHERE name = ?", (t,))


def ultimo(tabla: str) -> Optional[Dict[str, Any]]:
    with conexion() as con:
        fila = con.execute(f"SELECT datos FROM {tabla} ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(fila["datos"]) if fila else None
