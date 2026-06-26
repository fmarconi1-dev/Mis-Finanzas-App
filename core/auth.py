"""Autenticación: bcrypt + helpers contra la tabla `usuarios`.

API mínima:
  - hash_password / verify_password
  - authenticate(conn, username, password) → dict | None
  - create_user(conn, username, password, fullname) → user_id
  - get_user(conn, username) → dict | None
  - set_password(conn, user_id, new_password)

Sesión en Streamlit (st.session_state):
  - logged_in: bool
  - current_user_id: int
  - current_username: str
  - current_user_fullname: str | None

`current_user.py` expone un contextvar con el user_id activo para que las
queries internas filtren por ahí en Round 2.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Optional

import bcrypt


# ---------- Rate limiting de login (premortem #3, F4/R5) ----------
#
# Estado en memoria del proceso (Streamlit corre en un único proceso).
# Tras LOCKOUT_THRESHOLD intentos fallidos dentro de LOCKOUT_WINDOW segundos,
# el username queda bloqueado LOCKOUT_SECONDS desde el último intento.
# Suficiente para frenar brute force online; se resetea al reiniciar la app.

LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW = 15 * 60      # ventana en la que se cuentan los fallos
LOCKOUT_SECONDS = 5 * 60      # duración del bloqueo

_failed_logins: dict[str, list[float]] = {}


def register_failed_login(username: str, now: Optional[float] = None) -> None:
    """Registra un intento fallido para el username (case-insensitive)."""
    t = now if now is not None else time.time()
    key = username.strip().lower()
    intentos = [x for x in _failed_logins.get(key, []) if t - x < LOCKOUT_WINDOW]
    intentos.append(t)
    _failed_logins[key] = intentos


def seconds_until_unlock(username: str, now: Optional[float] = None) -> int:
    """Devuelve cuántos segundos faltan para poder reintentar. 0 = libre."""
    t = now if now is not None else time.time()
    key = username.strip().lower()
    intentos = [x for x in _failed_logins.get(key, []) if t - x < LOCKOUT_WINDOW]
    if len(intentos) < LOCKOUT_THRESHOLD:
        return 0
    restante = LOCKOUT_SECONDS - (t - max(intentos))
    return max(0, int(restante) + 1) if restante > 0 else 0


def clear_failed_logins(username: str) -> None:
    """Limpia el historial de fallos (tras un login exitoso)."""
    _failed_logins.pop(username.strip().lower(), None)


# ---------- Hashing ----------

def hash_password(plain: str) -> str:
    """Hashea con bcrypt + salt aleatorio. Devuelve string ASCII para guardar en TEXT."""
    if not plain:
        raise ValueError("La contraseña no puede estar vacía.")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica contraseña contra el hash. Devuelve False si el hash está vacío."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- Usuarios ----------

def get_user(conn: sqlite3.Connection, username: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, username, password_hash, fullname, creado_en "
        "FROM usuarios WHERE username = ?",
        (username,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, username, fullname, creado_en FROM usuarios WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def authenticate(
    conn: sqlite3.Connection, username: str, password: str
) -> Optional[dict]:
    """Si las credenciales son válidas, devuelve dict del user (sin password). Sino None."""
    user = get_user(conn, username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"] or ""):
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "fullname": user["fullname"],
    }


def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    fullname: Optional[str] = None,
) -> int:
    """Crea un usuario nuevo. Lanza ValueError si el username ya existe."""
    username = username.strip()
    if not username:
        raise ValueError("El usuario no puede estar vacío.")
    if len(password) < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")
    if get_user(conn, username):
        raise ValueError(f"El usuario '{username}' ya existe.")

    cur = conn.execute(
        "INSERT INTO usuarios (username, password_hash, fullname) VALUES (?, ?, ?)",
        (username, hash_password(password), fullname),
    )
    return cur.lastrowid


def set_password(conn: sqlite3.Connection, user_id: int, new_password: str) -> None:
    """Resetea la contraseña de un usuario existente."""
    if len(new_password) < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")
    cur = conn.execute(
        "UPDATE usuarios SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    if cur.rowcount == 0:
        raise LookupError(f"No existe usuario con id={user_id}")
