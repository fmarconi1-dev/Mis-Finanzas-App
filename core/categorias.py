"""CRUD de categorías + helpers para el editor de Configuración.

Operaciones aisladas por user_id (multi-tenant). `core/categorizer.py` sigue
siendo lógica pura (DEFAULT_CATEGORIAS, efective_grupo).
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from core.current_user import require_current_user_id
from core.db import backup_db


GRUPOS_EDITABLES = (
    "Ingreso",
    "Gasto Fijo",
    "Gasto Variable",
    "Inversion",
    "Sin categorizar",
)

MOTIVOS_PROTEGIDOS = frozenset({"Caja"})


def _uid(user_id: Optional[int]) -> int:
    return user_id if user_id is not None else require_current_user_id()


def update_categoria(
    conn: sqlite3.Connection,
    motivo: str,
    grupo: str,
    subcategoria: Optional[str],
    user_id: Optional[int] = None,
) -> None:
    """Actualiza grupo y subcategoría de un motivo del usuario activo."""
    uid = _uid(user_id)
    if motivo in MOTIVOS_PROTEGIDOS:
        raise ValueError(f"El motivo '{motivo}' es protegido.")
    if grupo not in GRUPOS_EDITABLES:
        raise ValueError(
            f"Grupo '{grupo}' inválido. Permitidos: {', '.join(GRUPOS_EDITABLES)}"
        )

    cur = conn.execute(
        "UPDATE categorias SET grupo = ?, subcategoria = ? "
        "WHERE motivo = ? AND user_id = ?",
        (grupo, (subcategoria or None), motivo, uid),
    )
    if cur.rowcount == 0:
        raise LookupError(f"No existe categoría '{motivo}' para este usuario.")
    backup_db()


def delete_categoria(
    conn: sqlite3.Connection, motivo: str, user_id: Optional[int] = None
) -> None:
    """Borra categoría del usuario activo. Falla si hay transacciones usándola."""
    uid = _uid(user_id)
    if motivo in MOTIVOS_PROTEGIDOS:
        raise ValueError(f"El motivo '{motivo}' es protegido y no se borra.")

    en_uso = conn.execute(
        "SELECT 1 FROM transacciones WHERE motivo = ? AND user_id = ? LIMIT 1",
        (motivo, uid),
    ).fetchone()
    if en_uso:
        raise ValueError(
            f"El motivo '{motivo}' está en uso. Borrá o reasigná las transacciones primero."
        )

    cur = conn.execute(
        "DELETE FROM categorias WHERE motivo = ? AND user_id = ?", (motivo, uid),
    )
    if cur.rowcount == 0:
        raise LookupError(f"No existe categoría '{motivo}' para este usuario.")
    backup_db()


def insert_categoria(
    conn: sqlite3.Connection,
    motivo: str,
    grupo: str = "Sin categorizar",
    subcategoria: Optional[str] = None,
    user_id: Optional[int] = None,
) -> None:
    """Crea categoría nueva para el usuario activo."""
    uid = _uid(user_id)
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("El motivo no puede estar vacío.")
    if grupo not in GRUPOS_EDITABLES:
        raise ValueError(
            f"Grupo '{grupo}' inválido. Permitidos: {', '.join(GRUPOS_EDITABLES)}"
        )

    ya_existe = conn.execute(
        "SELECT 1 FROM categorias WHERE motivo = ? AND user_id = ? LIMIT 1",
        (motivo, uid),
    ).fetchone()
    if ya_existe:
        raise ValueError(f"Ya tenés una categoría con motivo '{motivo}'.")

    conn.execute(
        "INSERT INTO categorias (motivo, grupo, subcategoria, user_id) "
        "VALUES (?, ?, ?, ?)",
        (motivo, grupo, (subcategoria or None), uid),
    )
    backup_db()


def motivos_sin_uso(
    conn: sqlite3.Connection, user_id: Optional[int] = None
) -> list[str]:
    """Motivos del usuario activo sin transacciones asociadas (excluye protegidos)."""
    uid = _uid(user_id)
    rows = conn.execute(
        """
        SELECT c.motivo
        FROM categorias c
        WHERE c.user_id = ?
          AND NOT EXISTS (
            SELECT 1 FROM transacciones t
            WHERE t.motivo = c.motivo AND t.user_id = c.user_id
          )
        ORDER BY c.motivo
        """,
        (uid,),
    ).fetchall()
    return [r["motivo"] for r in rows if r["motivo"] not in MOTIVOS_PROTEGIDOS]
