"""
Autenticación y roles (núcleo). Diseño mínimo y seguro:

- Roles: `administrador` (consola de administración) y `usuario` (cuenta registrada sin permisos administrativos).
  El ciudadano que reporta o consulta su reporte NO necesita cuenta (portal público, acceso por código de seguimiento).
- Contraseñas: scrypt con sal aleatoria por usuario (hashlib, sin dependencias); nunca en texto plano, nunca en el código.
  No existen usuarios ni contraseñas predeterminadas: el primer administrador se crea con
  `python -m scripts.crear_admin` (pide la contraseña sin mostrarla).
- Sesiones: token aleatorio de 256 bits entregado una sola vez; en memoria solo se guarda su SHA-256 y expiran
  (SESION_HORAS). Se pierden al reiniciar el proceso (limitación documentada).
- Fuerza bruta: bloqueo temporal por usuario tras varios fallos seguidos.
- Autorización: `requiere_admin` / `requiere_actor` comprueban el `Actor` del contexto de ejecución (ContextVar) en
  la lógica de negocio, no solo en la interfaz. Quien invoca (UI, API) establece el actor con `como(actor)`.
- Límites: sin recuperación de contraseña, sin MFA, sin HTTPS propio; el canal sin cifrar expone credenciales en la red.
"""

import functools
import hashlib
import hmac
import re
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from data import database as db
from services import tracing

SESION_HORAS = 8
MIN_CLAVE = 10
MAX_FALLOS = 5
BLOQUEO_SEGUNDOS = 300
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


class Rol(str, Enum):
    ADMIN = "administrador"
    USUARIO = "usuario"


@dataclass(frozen=True)
class Actor:
    usuario: str
    rol: Rol
    origen: str = "sesion"          # sesion | servicio (token de API configurado) | dispositivo


class ErrorAutenticacion(Exception):
    """Credenciales o sesión inválidas (→ 401)."""


class ErrorAutorizacion(Exception):
    """Autenticado pero sin permiso para la operación (→ 403)."""


actor_actual: ContextVar[Optional[Actor]] = ContextVar("actor_actual", default=None)
_sesiones: Dict[str, Tuple[Actor, float]] = {}
_fallos: Dict[str, List[float]] = {}


# ----------------------------------------------------------------------------- contraseñas
def _hash(clave: str, sal: bytes) -> str:
    return hashlib.scrypt(clave.encode("utf-8"), salt=sal, **_SCRYPT).hex()


def validar_clave(clave: str) -> None:
    if len(clave) < MIN_CLAVE:
        raise ValueError(f"La contraseña debe tener al menos {MIN_CLAVE} caracteres.")
    if clave.lower() == clave or clave.upper() == clave or not re.search(r"\d", clave):
        raise ValueError("La contraseña debe combinar mayúsculas, minúsculas y al menos un número.")


# ------------------------------------------------------------------------------- usuarios
def _doc(usuario: str) -> Optional[dict]:
    return db.obtener("usuarios", usuario.strip().lower())


def hay_administradores() -> bool:
    return any(d.get("rol") == Rol.ADMIN.value and d.get("activo", True) for d in db.listar("usuarios"))


def crear_usuario(usuario: str, clave: str, rol: Rol = Rol.USUARIO) -> None:
    """Crea o reemplaza una cuenta. Solo se invoca desde `scripts.crear_admin` o desde una sesión de administrador."""
    usuario = usuario.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", usuario):
        raise ValueError("Usuario: 3-40 caracteres (letras, números, punto, guion).")
    validar_clave(clave)
    sal = secrets.token_bytes(16)
    db.insertar("usuarios", {"usuario": usuario, "rol": Rol(rol).value, "sal": sal.hex(), "hash": _hash(clave, sal),
                             "kdf": "scrypt", "activo": True, "creado": datetime.now().isoformat(timespec="seconds")},
                clave=usuario)
    tracing.emitir("auth", "crear_usuario", "ok", {"usuario": usuario, "rol": Rol(rol).value})


def listar_usuarios() -> List[dict]:
    """Sin hash ni sal."""
    return [{"usuario": d["usuario"], "rol": d["rol"], "activo": d.get("activo", True), "creado": d.get("creado")}
            for d in db.listar("usuarios")]


# ------------------------------------------------------------------------------ autenticar
def _bloqueado(usuario: str) -> bool:
    ahora = time.monotonic()
    recientes = [t for t in _fallos.get(usuario, []) if ahora - t < BLOQUEO_SEGUNDOS]
    _fallos[usuario] = recientes
    return len(recientes) >= MAX_FALLOS


def autenticar(usuario: str, clave: str) -> Actor:
    """Verifica credenciales. Mensaje genérico (no revela si el usuario existe) y tiempo similar con usuario inexistente."""
    u = (usuario or "").strip().lower()
    if _bloqueado(u):
        tracing.emitir("auth", "login", "error", {"usuario": u}, {"motivo": "bloqueado"})
        raise ErrorAutenticacion("Demasiados intentos fallidos. Espere unos minutos.")
    d = _doc(u) if u else None
    sal = bytes.fromhex(d["sal"]) if d else b"\x00" * 16
    calculado = _hash(clave or "", sal)
    ok = bool(d) and d.get("activo", True) and hmac.compare_digest(calculado, d["hash"])
    if not ok:
        _fallos.setdefault(u, []).append(time.monotonic())
        tracing.emitir("auth", "login", "error", {"usuario": u}, {"motivo": "credenciales"})
        raise ErrorAutenticacion("Usuario o contraseña incorrectos.")
    _fallos.pop(u, None)
    tracing.emitir("auth", "login", "ok", {"usuario": u, "rol": d["rol"]})
    return Actor(usuario=u, rol=Rol(d["rol"]))


# -------------------------------------------------------------------------------- sesiones
def _huella(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def iniciar_sesion(usuario: str, clave: str) -> str:
    actor = autenticar(usuario, clave)
    token = secrets.token_urlsafe(32)
    _sesiones[_huella(token)] = (actor, time.monotonic() + SESION_HORAS * 3600)
    return token


def actor_de_token(token: Optional[str]) -> Optional[Actor]:
    if not token:
        return None
    h = _huella(token)
    par = _sesiones.get(h)
    if not par:
        return None
    if time.monotonic() > par[1]:
        _sesiones.pop(h, None)
        return None
    return par[0]


def cerrar_sesion(token: Optional[str]) -> None:
    if token:
        _sesiones.pop(_huella(token), None)


def reiniciar_estado() -> None:
    """Pruebas: borra sesiones y contadores de fallos."""
    _sesiones.clear()
    _fallos.clear()


# ----------------------------------------------------------------------------- autorización
@contextmanager
def como(actor: Optional[Actor]) -> Iterator[Optional[Actor]]:
    """Establece quién ejecuta la operación (UI o API) durante el bloque."""
    t = actor_actual.set(actor)
    try:
        yield actor
    finally:
        actor_actual.reset(t)


def actor() -> Optional[Actor]:
    return actor_actual.get()


def exigir_admin() -> Actor:
    a = actor_actual.get()
    if a is None:
        raise ErrorAutenticacion("Inicie sesión como administrador.")
    if a.rol != Rol.ADMIN:
        raise ErrorAutorizacion("Esta operación requiere permisos de administrador.")
    return a


def requiere_admin(fn: Callable) -> Callable:
    """Decorador de funciones de negocio administrativas: la comprobación ocurre en el backend, no en la interfaz."""
    @functools.wraps(fn)
    def envoltura(*a, **k):
        exigir_admin()
        return fn(*a, **k)
    return envoltura
