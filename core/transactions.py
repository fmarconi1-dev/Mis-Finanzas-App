"""CRUD de transacciones + hook de backup automático.

Cada función pública dispara un backup_db() después de modificar la DB y
filtra por `user_id` (vía contextvar o parámetro explícito).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from core.current_user import require_current_user_id
from core.db import backup_db


def _uid(user_id: Optional[int]) -> int:
    return user_id if user_id is not None else require_current_user_id()


def insert_transaction(
    conn: sqlite3.Connection,
    fecha: date,
    motivo: str,
    pasivos: float = 0.0,
    ingresos: float = 0.0,
    comentario: Optional[str] = None,
    user_id: Optional[int] = None,
) -> int:
    """Inserta una transacción para el usuario activo. Devuelve el id."""
    uid = _uid(user_id)
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("El motivo no puede estar vacío")
    if pasivos < 0 and ingresos < 0:
        raise ValueError("No tiene sentido negativo en pasivos e ingresos a la vez")

    # Asegurar que el motivo exista en `categorias` para este usuario.
    conn.execute(
        "INSERT OR IGNORE INTO categorias (motivo, grupo, user_id) "
        "VALUES (?, 'Sin categorizar', ?)",
        (motivo, uid),
    )

    cur = conn.execute(
        "INSERT INTO transacciones (fecha, pasivos, ingresos, motivo, comentario, user_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (fecha.isoformat(), float(pasivos), float(ingresos), motivo, comentario, uid),
    )
    new_id = cur.lastrowid
    backup_db()
    return new_id


def update_transaction(
    conn: sqlite3.Connection,
    txn_id: int,
    fecha: date,
    motivo: str,
    pasivos: float = 0.0,
    ingresos: float = 0.0,
    comentario: Optional[str] = None,
    user_id: Optional[int] = None,
) -> None:
    """Edita una transacción existente del usuario activo."""
    uid = _uid(user_id)
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("El motivo no puede estar vacío")

    conn.execute(
        "INSERT OR IGNORE INTO categorias (motivo, grupo, user_id) "
        "VALUES (?, 'Sin categorizar', ?)",
        (motivo, uid),
    )

    cur = conn.execute(
        "UPDATE transacciones SET fecha = ?, motivo = ?, pasivos = ?, ingresos = ?, "
        "comentario = ? WHERE id = ? AND user_id = ?",
        (fecha.isoformat(), motivo, float(pasivos), float(ingresos), comentario, txn_id, uid),
    )
    if cur.rowcount == 0:
        raise LookupError(f"No existe transacción con id={txn_id} para este usuario")
    backup_db()


def delete_transaction(
    conn: sqlite3.Connection, txn_id: int, user_id: Optional[int] = None
) -> None:
    uid = _uid(user_id)
    cur = conn.execute(
        "DELETE FROM transacciones WHERE id = ? AND user_id = ?", (txn_id, uid),
    )
    if cur.rowcount == 0:
        raise LookupError(f"No existe transacción con id={txn_id} para este usuario")
    backup_db()


def get_transaction(
    conn: sqlite3.Connection, txn_id: int, user_id: Optional[int] = None
) -> Optional[dict]:
    uid = _uid(user_id)
    row = conn.execute(
        "SELECT id, fecha, pasivos, ingresos, motivo, comentario "
        "FROM transacciones WHERE id = ? AND user_id = ?",
        (txn_id, uid),
    ).fetchone()
    return dict(row) if row else None


def list_recent(
    conn: sqlite3.Connection, n: int = 20, user_id: Optional[int] = None
) -> list[dict]:
    """Últimas N transacciones del usuario activo."""
    uid = _uid(user_id)
    rows = conn.execute(
        "SELECT id, fecha, pasivos, ingresos, motivo, comentario "
        "FROM transacciones WHERE user_id = ? ORDER BY fecha DESC, id DESC LIMIT ?",
        (uid, n),
    ).fetchall()
    return [dict(r) for r in rows]


def all_motivos(conn: sqlite3.Connection, user_id: Optional[int] = None) -> list[str]:
    """Motivos del usuario en categorias + en transacciones (sin 'Caja')."""
    uid = _uid(user_id)
    rows = conn.execute(
        "SELECT motivo FROM categorias WHERE user_id = ? "
        "UNION "
        "SELECT DISTINCT motivo FROM transacciones WHERE user_id = ? "
        "ORDER BY motivo",
        (uid, uid),
    ).fetchall()
    return [r["motivo"] for r in rows if r["motivo"] and r["motivo"] != "Caja"]


def motivos_recientes(
    conn: sqlite3.Connection,
    n: int = 6,
    dias: int = 60,
    user_id: Optional[int] = None,
) -> list[str]:
    """Motivos más usados por el usuario en los últimos `dias` días.

    Ordenados por frecuencia desc, con desempate por uso más reciente.
    Pensado para los chips de "atajos" en alta rápida.
    """
    uid = _uid(user_id)
    rows = conn.execute(
        """
        SELECT motivo, COUNT(*) AS cnt, MAX(fecha) AS ultimo
        FROM transacciones
        WHERE user_id = ?
          AND date(fecha) >= date('now', ?)
          AND motivo != 'Caja'
        GROUP BY motivo
        ORDER BY cnt DESC, ultimo DESC
        LIMIT ?
        """,
        (uid, f"-{int(dias)} days", int(n)),
    ).fetchall()
    return [r["motivo"] for r in rows]


def montos_frecuentes_por_motivo(
    conn: sqlite3.Connection,
    motivo: Optional[str] = None,
    n: int = 4,
    dias: int = 90,
    user_id: Optional[int] = None,
) -> list[float]:
    """Montos más recurrentes en los últimos `dias` días.

    - Si `motivo` es None: agregado global (útil cuando todavía no se eligió motivo).
    - Si `motivo` es un motivo concreto: filtra por ese motivo.

    Cada transacción aporta `pasivos` (si > 0) o `ingresos` (si > 0). Se
    descartan los 0 y duplicados que sean idénticos al céntimo.
    """
    uid = _uid(user_id)
    params: list = [uid, f"-{int(dias)} days"]
    where_motivo = ""
    if motivo:
        where_motivo = "AND motivo = ?"
        params.append(motivo)
    params.append(int(n))

    rows = conn.execute(
        f"""
        SELECT monto, COUNT(*) AS cnt
        FROM (
            SELECT CASE
                       WHEN pasivos  > 0 THEN ROUND(pasivos, 2)
                       WHEN ingresos > 0 THEN ROUND(ingresos, 2)
                       ELSE NULL
                   END AS monto
            FROM transacciones
            WHERE user_id = ?
              AND date(fecha) >= date('now', ?)
              {where_motivo}
        )
        WHERE monto IS NOT NULL AND monto > 0
        GROUP BY monto
        ORDER BY cnt DESC, monto DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [float(r["monto"]) for r in rows]
