"""Setea o resetea la contraseña de un usuario existente.

Uso:
    python -m scripts.setup_password

El script pide:
  - username (default 'local', que es la cuenta sembrada por la migración M1)
  - contraseña nueva (se ingresa dos veces para confirmar)

Útil para:
  - Setear la contraseña de tu cuenta la primera vez (cuando todavía no hay
    UI de signup en Round 1).
  - Recuperar acceso si te olvidaste la contraseña.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

# Soportar tanto `python scripts/setup_password.py` como `python -m scripts.setup_password`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.auth import set_password, get_user
from core.db import connect, init_db


def main() -> int:
    init_db()

    print("=== Setup de contraseña ===\n")
    default = "local"
    username = input(f"Username [{default}]: ").strip() or default

    with connect() as conn:
        user = get_user(conn, username)
        if not user:
            print(f"\nERROR: no existe usuario '{username}'.")
            print("Listá los usuarios con:")
            print('  python -c "from core.db import connect; '
                  '[print(dict(r)) for r in connect().execute(\'SELECT id, username, fullname FROM usuarios\')]"')
            return 1

        print(f"Encontrado: id={user['id']}, fullname={user.get('fullname')}")
        pw1 = getpass.getpass("Nueva contraseña: ")
        pw2 = getpass.getpass("Repetir contraseña: ")

        if pw1 != pw2:
            print("\nERROR: las contraseñas no coinciden.")
            return 2
        if len(pw1) < 6:
            print("\nERROR: la contraseña debe tener al menos 6 caracteres.")
            return 3

        set_password(conn, user["id"], pw1)

    print(f"\n✅ Contraseña actualizada para '{username}'.")
    print("Ahora podés iniciar sesión desde la app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
