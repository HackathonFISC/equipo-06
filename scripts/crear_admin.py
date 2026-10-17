"""
Crea (o restablece) una cuenta de HIDRO360 pidiendo la contraseña sin mostrarla. No existen cuentas predeterminadas.

    python -m scripts.crear_admin                 # administrador
    python -m scripts.crear_admin --rol usuario   # cuenta sin permisos administrativos

La contraseña nunca se guarda en texto plano (scrypt con sal) ni se acepta por argumento de línea de comandos
(quedaría en el historial del shell).
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import auth  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usuario", help="nombre de usuario (si se omite, se pregunta)")
    ap.add_argument("--rol", choices=[r.value for r in auth.Rol], default=auth.Rol.ADMIN.value)
    a = ap.parse_args()
    usuario = (a.usuario or input("Usuario: ")).strip()
    clave = getpass.getpass("Contraseña: ")
    if clave != getpass.getpass("Repita la contraseña: "):
        print("Las contraseñas no coinciden.")
        return 1
    try:
        auth.crear_usuario(usuario, clave, auth.Rol(a.rol))
    except ValueError as e:
        print(f"No se creó la cuenta: {e}")
        return 1
    print(f"Cuenta «{usuario.lower()}» creada con rol {a.rol}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
