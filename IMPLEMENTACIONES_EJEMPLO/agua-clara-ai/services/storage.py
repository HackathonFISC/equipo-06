"""Persistencia en SQLite + registro de auditoría encadenado por hash.

- `report`: reportes ciudadanos y su estado.
- `plan` / `plan_item`: planes propuestos.
- `decision`: aprobación / edición / rechazo humano.
- `delivery`: verificaciones de entrega (A6).
- `audit`: cadena de hashes; si alguien altera un evento, la cadena se rompe.
- `outbox`: avisos pendientes de envío (herramienta que actúa).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator, Optional

from config import DB_PATH, DATA_DIR, now_iso

_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS report (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    channel TEXT,
    raw_text TEXT,
    sector_id TEXT,
    incident_type TEXT,
    severity INTEGER,
    hours_without_water REAL,
    affected_people INTEGER,
    institution_type TEXT,
    confidence REAL,
    missing_fields TEXT,
    source_hash TEXT,
    injection_flag INTEGER DEFAULT 0,
    out_of_scope INTEGER DEFAULT 0,
    status TEXT,
    dup_of TEXT,
    meta TEXT
);
CREATE TABLE IF NOT EXISTS plan (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    method TEXT,
    status TEXT,
    metrics TEXT,
    explanation TEXT
);
CREATE TABLE IF NOT EXISTS plan_item (
    plan_id TEXT,
    sector_id TEXT,
    sector_name TEXT,
    tanker_id TEXT,
    liters INTEGER,
    stop_order INTEGER,
    eta_minutes INTEGER,
    reasons TEXT,
    constraints_ok INTEGER
);
CREATE TABLE IF NOT EXISTS decision (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT,
    created_at TEXT,
    operator TEXT,
    action TEXT,
    reason TEXT,
    changes TEXT
);
CREATE TABLE IF NOT EXISTS delivery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    plan_id TEXT,
    sector_id TEXT,
    tanker_id TEXT,
    status TEXT,
    checks TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT,
    action TEXT,
    payload TEXT,
    prev_hash TEXT,
    hash TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    channel TEXT,
    recipient TEXT,
    body TEXT,
    status TEXT
);
CREATE TABLE IF NOT EXISTS hydro_reading (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    phone TEXT,
    sector_id TEXT,
    barriada TEXT,
    tipo TEXT,              -- 'audio' | 'imagen'
    estado TEXT,            -- 'aire' | 'seco' | 'flujo_normal' | 'desconocido'
    confianza REAL,
    segundo INTEGER DEFAULT 0,
    meta TEXT
);
CREATE INDEX IF NOT EXISTS idx_hydro_sector ON hydro_reading(sector_id);
"""


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    with _LOCK:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    with db() as conn:
        conn.executescript(SCHEMA)
        # Migración ligera: añade columnas nuevas a bases de datos existentes.
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(report)").fetchall()}
        if "meta" not in cols:
            conn.execute("ALTER TABLE report ADD COLUMN meta TEXT")


# ----------------------------- Auditoría encadenada -----------------------------

def _last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    return row["hash"] if row else "GENESIS"


def audit(actor: str, action: str, payload: dict[str, Any]) -> str:
    with db() as conn:
        prev = _last_hash(conn)
        ts = now_iso()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        body = json.dumps({"ts": ts, "actor": actor, "action": action, "payload": payload},
                          ensure_ascii=False, sort_keys=True)
        h = hashlib.sha256((prev + body).encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO audit (ts, actor, action, payload, prev_hash, hash) VALUES (?,?,?,?,?,?)",
            (ts, actor, action, payload_json, prev, h),
        )
    return h


def audit_head() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT seq, ts, actor, action, payload, prev_hash, hash "
                            "FROM audit ORDER BY seq DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]


def audit_verify_chain() -> dict:
    """Recorre la cadena y confirma que nada fue alterado."""
    with db() as conn:
        rows = conn.execute("SELECT seq, ts, actor, action, payload, prev_hash, hash "
                            "FROM audit ORDER BY seq ASC").fetchall()
    prev = "GENESIS"
    for r in rows:
        payload = json.loads(r["payload"])
        body = json.dumps({"ts": r["ts"], "actor": r["actor"], "action": r["action"], "payload": payload},
                          ensure_ascii=False, sort_keys=True)
        expected = hashlib.sha256((prev + body).encode("utf-8")).hexdigest()
        if r["prev_hash"] != prev or r["hash"] != expected:
            return {"ok": False, "broken_at": r["seq"]}
        prev = r["hash"]
    return {"ok": True, "events": len(rows)}


# ----------------------------- Reportes -----------------------------

def insert_report(r: dict) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO report (id, created_at, channel, raw_text, sector_id, incident_type,
               severity, hours_without_water, affected_people, institution_type, confidence,
               missing_fields, source_hash, injection_flag, out_of_scope, status, dup_of, meta)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["id"], r["created_at"], r["channel"], r["raw_text"], r.get("sector_id"),
             r["incident_type"], r.get("severity"), r.get("hours_without_water"),
             r.get("affected_people"), r.get("institution_type"), r.get("confidence", 0.0),
             json.dumps(r.get("missing_fields", []), ensure_ascii=False),
             r.get("source_hash"), int(r.get("injection_flag", False)),
             int(r.get("out_of_scope", False)), r.get("status", "recibido"), r.get("dup_of"),
             json.dumps(r.get("meta", {}), ensure_ascii=False, default=str)),
        )


def update_report(report_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE report SET {cols} WHERE id = ?", (*fields.values(), report_id))


def _parse_report(row: sqlite3.Row) -> dict:
    d = dict(row)
    raw = d.get("meta")
    if raw:
        try:
            d["meta"] = json.loads(raw)
        except Exception:
            d["meta"] = {}
    else:
        d["meta"] = {}
    mf = d.get("missing_fields")
    if isinstance(mf, str):
        try:
            d["missing_fields"] = json.loads(mf)
        except Exception:
            d["missing_fields"] = []
    return d


def list_reports(limit: int = 200) -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM report ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_parse_report(r) for r in rows]


def get_report(report_id: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM report WHERE id = ?", (report_id,)).fetchone()
    return _parse_report(row) if row else None


def clear_reports() -> None:
    """Borra reportes (para reiniciar la demo sin tocar el resto)."""
    with db() as conn:
        conn.execute("DELETE FROM report")


# ----------------------------- Planes -----------------------------

def insert_plan(plan: dict) -> None:
    with db() as conn:
        conn.execute("INSERT INTO plan (id, created_at, method, status, metrics, explanation) VALUES (?,?,?,?,?,?)",
                     (plan["id"], plan["created_at"], plan["method"], plan.get("status", "propuesto"),
                      json.dumps(plan.get("metrics", {}), ensure_ascii=False), plan.get("explanation", "")))
        for a in plan.get("assignments", []):
            conn.execute(
                """INSERT INTO plan_item (plan_id, sector_id, sector_name, tanker_id, liters, stop_order,
                   eta_minutes, reasons, constraints_ok) VALUES (?,?,?,?,?,?,?,?,?)""",
                (plan["id"], a["sector_id"], a["sector_name"], a["tanker_id"], a["liters"], a["stop_order"],
                 a.get("eta_minutes"), json.dumps(a.get("reasons", []), ensure_ascii=False),
                 int(a.get("constraints_ok", True))),
            )


def get_plan(plan_id: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM plan WHERE id = ?", (plan_id,)).fetchone()
        if not row:
            return None
        items = conn.execute("SELECT * FROM plan_item WHERE plan_id = ? ORDER BY tanker_id, stop_order",
                             (plan_id,)).fetchall()
    plan = dict(row)
    plan["metrics"] = json.loads(plan["metrics"] or "{}")
    plan["assignments"] = [
        {**dict(i), "reasons": json.loads(i["reasons"] or "[]"), "constraints_ok": bool(i["constraints_ok"])}
        for i in items
    ]
    return plan


def latest_plan() -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT id FROM plan ORDER BY created_at DESC LIMIT 1").fetchone()
    return get_plan(row["id"]) if row else None


def set_plan_status(plan_id: str, status: str) -> None:
    with db() as conn:
        conn.execute("UPDATE plan SET status = ? WHERE id = ?", (status, plan_id))


# ----------------------------- Decisiones -----------------------------

def insert_decision(d: dict) -> None:
    with db() as conn:
        conn.execute("INSERT INTO decision (plan_id, created_at, operator, action, reason, changes) VALUES (?,?,?,?,?,?)",
                     (d["plan_id"], now_iso(), d["operator"], d["action"], d.get("reason", ""),
                      json.dumps(d.get("changes", []), ensure_ascii=False)))


# ----------------------------- Entregas -----------------------------

def insert_delivery(d: dict) -> None:
    with db() as conn:
        conn.execute("INSERT INTO delivery (created_at, plan_id, sector_id, tanker_id, status, checks) VALUES (?,?,?,?,?,?)",
                     (now_iso(), d.get("plan_id"), d["sector_id"], d["tanker_id"], d["status"],
                      json.dumps(d.get("checks", []), ensure_ascii=False)))


# ----------------------------- Outbox -----------------------------

def insert_outbox(channel: str, recipient: str, body: str, status: str = "pendiente") -> int:
    with db() as conn:
        cur = conn.execute("INSERT INTO outbox (created_at, channel, recipient, body, status) VALUES (?,?,?,?,?)",
                           (now_iso(), channel, recipient, body, status))
        return int(cur.lastrowid)


def list_outbox(limit: int = 50) -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM outbox ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# ----------------------------- Lecturas hidroacústicas (Proyecto Poseidón) -----------------------------

def insert_hydro_reading(r: dict) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO hydro_reading (created_at, phone, sector_id, barriada, tipo,
               estado, confianza, segundo, meta) VALUES (?,?,?,?,?,?,?,?,?)""",
            (r.get("created_at") or now_iso(), r.get("phone"), r.get("sector_id"),
             r.get("barriada"), r.get("tipo"), r.get("estado"),
             float(r.get("confianza") or 0.0), int(r.get("segundo") or 0),
             json.dumps(r.get("meta", {}), ensure_ascii=False, default=str)),
        )
        return int(cur.lastrowid)


def _parse_hydro(row: sqlite3.Row) -> dict:
    d = dict(row)
    raw = d.get("meta")
    if raw:
        try:
            d["meta"] = json.loads(raw)
        except Exception:
            d["meta"] = {}
    else:
        d["meta"] = {}
    return d


def list_hydro_readings(sector_id: str | None = None, minutes: int | None = None,
                        limit: int = 200) -> list[dict]:
    """Lecturas hidroacústicas, opcionalmente filtradas por sector y ventana temporal."""
    q = "SELECT * FROM hydro_reading"
    args: list[Any] = []
    where: list[str] = []
    if sector_id:
        where.append("sector_id = ?")
        args.append(sector_id)
    if minutes is not None:
        # El mismo formato y zona que config.now_iso() (local, "YYYY-MM-DDTHH:MM:SS"),
        # para que la comparación de cadenas sea cronológicamente correcta.
        cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")
        where.append("created_at >= ?")
        args.append(cutoff)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with db() as conn:
        rows = conn.execute(q, tuple(args)).fetchall()
    return [_parse_hydro(r) for r in rows]


def clear_hydro_readings() -> None:
    with db() as conn:
        conn.execute("DELETE FROM hydro_reading")
