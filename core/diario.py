"""Libro Diario: movimientos individuales con saldo acumulado, filtrado por usuario."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

import pandas as pd

from core.categorizer import efective_grupo
from core.current_user import require_current_user_id
from core.metrics import (
    load_categorias_full,
    load_transactions,
    saldo_inicial,
)


def libro_diario(
    conn: sqlite3.Connection,
    dias: int = 7,
    user_id: Optional[int] = None,
) -> pd.DataFrame:
    """Movimientos de los últimos `dias` días del usuario activo, con saldo de Caja."""
    uid = user_id if user_id is not None else require_current_user_id()

    df_all = load_transactions(conn, user_id=uid)
    if df_all.empty:
        return pd.DataFrame(columns=[
            "id", "fecha", "motivo", "grupo", "subcategoria",
            "pasivos", "ingresos", "caja_despues", "comentario",
        ])

    df_all = df_all.sort_values(["fecha", "id"]).reset_index(drop=True)
    df_all["caja_despues"] = (
        saldo_inicial(conn, user_id=uid)
        + (df_all["ingresos"] - df_all["pasivos"]).cumsum()
    )

    cats_full = load_categorias_full(conn, user_id=uid)
    grupos, subs = [], []
    for _, row in df_all.iterrows():
        g, s = efective_grupo(
            row["motivo"], float(row["pasivos"]), float(row["ingresos"]), cats_full
        )
        grupos.append(g)
        subs.append(s)
    df_all["grupo"] = grupos
    df_all["subcategoria"] = subs

    hoy = pd.Timestamp(date.today())
    desde = hoy - pd.Timedelta(days=int(dias) - 1)
    df_filt = df_all[df_all["fecha"] >= desde].copy()

    return (
        df_filt.sort_values(["fecha", "id"], ascending=[False, False])
        .reset_index(drop=True)
    )
