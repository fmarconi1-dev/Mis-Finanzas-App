"""Lógica Previsión vs Realidad por mes, filtrada por user_id."""

from __future__ import annotations

import sqlite3
from typing import Optional

import pandas as pd

from core.categorizer import efective_grupo
from core.current_user import require_current_user_id
from core.db import backup_db
from core.metrics import load_categorias_full, load_categorias_map


def _uid(user_id: Optional[int]) -> int:
    return user_id if user_id is not None else require_current_user_id()


def previsiones_anuales(
    conn: sqlite3.Connection, anio: int, user_id: Optional[int] = None
) -> pd.DataFrame:
    uid = _uid(user_id)
    return pd.read_sql_query(
        "SELECT motivo, mes, monto_previsto FROM presupuesto "
        "WHERE anio = ? AND user_id = ? ORDER BY motivo, mes",
        conn, params=[anio, uid],
    )


def realidad_mensual(
    conn: sqlite3.Connection,
    anio: int,
    mes: int,
    user_id: Optional[int] = None,
) -> pd.DataFrame:
    uid = _uid(user_id)
    return pd.read_sql_query(
        """
        SELECT motivo,
               COALESCE(SUM(ingresos), 0) AS ingresos_mes,
               COALESCE(SUM(pasivos), 0)  AS pasivos_mes
        FROM transacciones
        WHERE strftime('%Y', fecha) = ?
          AND strftime('%m', fecha) = ?
          AND user_id = ?
        GROUP BY motivo
        """,
        conn, params=[str(anio), f"{mes:02d}", uid],
    )


def realidad_mensual_efectiva(
    conn: sqlite3.Connection,
    anio: int,
    mes: int,
    user_id: Optional[int] = None,
) -> pd.DataFrame:
    """Realidad del mes clasificada FILA A FILA con `efective_grupo` — el
    mismo motor que usan Dashboard y Diario (fix premortem #3, F6/R3).

    Antes, la comparativa usaba el mapping plano {motivo: grupo}: una venta
    de "Inversiones" (regla dual → Ingreso/Desahorro) quedaba en el grupo
    Inversion con monto_real = pasivos = 0, es decir, DESAPARECÍA del mes.

    Devuelve cols: motivo, grupo, monto_real. Un motivo dual puede aparecer
    en DOS filas (ej. "Inversiones" como Inversion por el lado pasivo y como
    Ingreso por el lado desahorro).
    """
    uid = _uid(user_id)
    cats_full = load_categorias_full(conn, user_id=uid)

    txns = pd.read_sql_query(
        "SELECT motivo, pasivos, ingresos FROM transacciones "
        "WHERE strftime('%Y', fecha) = ? AND strftime('%m', fecha) = ? "
        "  AND user_id = ?",
        conn, params=[str(anio), f"{mes:02d}", uid],
    )
    if txns.empty:
        return pd.DataFrame(columns=["motivo", "grupo", "monto_real"])

    registros: list[tuple[str, str, float]] = []
    for _, r in txns.iterrows():
        grupo, _sub = efective_grupo(
            r["motivo"], float(r["pasivos"]), float(r["ingresos"]), cats_full
        )
        monto = float(r["ingresos"]) if grupo == "Ingreso" else float(r["pasivos"])
        registros.append((r["motivo"], grupo, monto))

    real = pd.DataFrame(registros, columns=["motivo", "grupo", "monto_real"])
    return real.groupby(["motivo", "grupo"], as_index=False)["monto_real"].sum()


def comparativa_mes(
    conn: sqlite3.Connection,
    anio: int,
    mes: int,
    categorias: Optional[dict[str, str]] = None,
    user_id: Optional[int] = None,
) -> pd.DataFrame:
    uid = _uid(user_id)
    if categorias is None:
        categorias = load_categorias_map(conn, user_id=uid)

    prev = pd.read_sql_query(
        "SELECT motivo, monto_previsto FROM presupuesto "
        "WHERE anio = ? AND mes = ? AND user_id = ?",
        conn, params=[anio, mes, uid],
    )
    # La previsión se asocia al grupo "base" del motivo (la regla dual sólo
    # aplica a la realidad: se presupuesta el lado pasivo de "Inversiones").
    prev["grupo"] = prev["motivo"].map(categorias).fillna("Sin categorizar")

    real = realidad_mensual_efectiva(conn, anio, mes, user_id=uid)

    merged = pd.merge(prev, real, on=["motivo", "grupo"], how="outer")
    merged["monto_previsto"] = merged["monto_previsto"].fillna(0.0)
    merged["monto_real"] = merged["monto_real"].fillna(0.0)
    merged["desvio_abs"] = merged["monto_real"] - merged["monto_previsto"]
    merged["desvio_pct"] = merged.apply(
        lambda r: (r["desvio_abs"] / r["monto_previsto"]) if r["monto_previsto"] else float("nan"),
        axis=1,
    )

    grupo_order = {
        "Ingreso": 0, "Gasto Fijo": 1, "Gasto Variable": 2,
        "Inversion": 3, "Sin categorizar": 4,
    }
    merged["_orden"] = merged["grupo"].map(grupo_order).fillna(99)
    merged = (
        merged.sort_values(["_orden", "monto_real"], ascending=[True, False])
        .drop(columns=["_orden"])
        .reset_index(drop=True)
    )

    return merged[
        ["motivo", "grupo", "monto_previsto", "monto_real", "desvio_abs", "desvio_pct"]
    ]


def meses_con_datos(
    conn: sqlite3.Connection, user_id: Optional[int] = None
) -> list[tuple[int, int]]:
    """(anio, mes) que tienen al menos una transacción del usuario activo."""
    uid = _uid(user_id)
    rows = conn.execute(
        """
        SELECT DISTINCT
            CAST(strftime('%Y', fecha) AS INTEGER) AS anio,
            CAST(strftime('%m', fecha) AS INTEGER) AS mes
        FROM transacciones
        WHERE user_id = ?
        ORDER BY anio, mes
        """,
        (uid,),
    ).fetchall()
    return [(r["anio"], r["mes"]) for r in rows]


# ---------- CRUD de previsiones (presupuesto) ----------

# Grupos/motivos que no tiene sentido presupuestar (saldo de apertura, sentinelas).
_GRUPOS_NO_PRESUPUESTABLES = ("Saldo Inicial",)
_MOTIVOS_NO_PRESUPUESTABLES = ("Caja",)


def previsiones_editor(
    conn: sqlite3.Connection,
    anio: int,
    mes: int,
    user_id: Optional[int] = None,
) -> list[dict]:
    """Devuelve TODOS los motivos categorizados del usuario con su previsión
    actual para (anio, mes). Si no hay previsión, devuelve 0 — listo para el
    data_editor.
    """
    uid = _uid(user_id)
    grupos_excl = ",".join("?" for _ in _GRUPOS_NO_PRESUPUESTABLES)
    motivos_excl = ",".join("?" for _ in _MOTIVOS_NO_PRESUPUESTABLES)
    rows = conn.execute(
        f"""
        SELECT c.motivo, c.grupo,
               COALESCE(p.monto_previsto, 0.0) AS previsto
        FROM categorias c
        LEFT JOIN presupuesto p
          ON p.motivo  = c.motivo
         AND p.user_id = c.user_id
         AND p.anio    = ?
         AND p.mes     = ?
        WHERE c.user_id = ?
          AND c.grupo  NOT IN ({grupos_excl})
          AND c.motivo NOT IN ({motivos_excl})
        ORDER BY
          CASE c.grupo
            WHEN 'Ingreso'        THEN 0
            WHEN 'Gasto Fijo'     THEN 1
            WHEN 'Gasto Variable' THEN 2
            WHEN 'Inversion'      THEN 3
            ELSE 99
          END,
          c.motivo
        """,
        (anio, mes, uid, *_GRUPOS_NO_PRESUPUESTABLES, *_MOTIVOS_NO_PRESUPUESTABLES),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_presupuesto(
    conn: sqlite3.Connection,
    motivo: str,
    anio: int,
    mes: int,
    monto: float,
    user_id: Optional[int] = None,
) -> None:
    """Crea o actualiza la previsión del usuario para (motivo, anio, mes)."""
    uid = _uid(user_id)
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("El motivo no puede estar vacío.")
    if monto < 0:
        raise ValueError("El monto previsto no puede ser negativo.")
    if not (1 <= int(mes) <= 12):
        raise ValueError("El mes debe estar entre 1 y 12.")
    conn.execute(
        "INSERT INTO presupuesto (motivo, anio, mes, monto_previsto, user_id) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(motivo, anio, mes, user_id) DO UPDATE SET "
        "    monto_previsto = excluded.monto_previsto",
        (motivo, int(anio), int(mes), float(monto), uid),
    )
    backup_db()


def delete_presupuesto(
    conn: sqlite3.Connection,
    motivo: str,
    anio: int,
    mes: int,
    user_id: Optional[int] = None,
) -> None:
    """Borra la previsión del usuario para (motivo, anio, mes)."""
    uid = _uid(user_id)
    conn.execute(
        "DELETE FROM presupuesto "
        "WHERE motivo = ? AND anio = ? AND mes = ? AND user_id = ?",
        (motivo, int(anio), int(mes), uid),
    )
    backup_db()


def copiar_previsto_a_anio(
    conn: sqlite3.Connection,
    motivo: str,
    anio: int,
    monto: float,
    user_id: Optional[int] = None,
) -> int:
    """Setea el mismo monto previsto en los 12 meses del año para el motivo.

    Sobrescribe previsiones existentes. Devuelve cuántos meses afectó (siempre 12).
    Hace un único backup al final (no 12).
    """
    uid = _uid(user_id)
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("El motivo no puede estar vacío.")
    if monto < 0:
        raise ValueError("El monto previsto no puede ser negativo.")
    for mes in range(1, 13):
        conn.execute(
            "INSERT INTO presupuesto (motivo, anio, mes, monto_previsto, user_id) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(motivo, anio, mes, user_id) DO UPDATE SET "
            "    monto_previsto = excluded.monto_previsto",
            (motivo, int(anio), mes, float(monto), uid),
        )
    backup_db()
    return 12
