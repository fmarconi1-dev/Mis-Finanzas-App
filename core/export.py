"""Exportación a Excel: snapshot del estado actual de la app.

El workbook resultante tiene 4 hojas:
  - Diario:     todas las transacciones (fecha, motivo, grupo, sub, egreso, ingreso, caja, comentario)
  - Mensual:    previsión vs realidad por mes/motivo
  - Categorías: mapping motivo → grupo → subcategoría
  - Resumen:    KPIs principales (anuales, mensuales, %)

Útil para:
  - Backup manual en formato planilla
  - Compartir con contador / armar declaración de impuestos
  - Comparar vs el Excel original si querés sanity-check
"""

from __future__ import annotations

import io
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd

from core.current_user import require_current_user_id
from core.metrics import (
    compute_kpis,
    fondo_emergencia_usd,
    load_categorias_full,
    load_transactions,
    saldo_cuenta_corriente,
    saldo_inicial,
)


def export_xlsx(conn: sqlite3.Connection, user_id: Optional[int] = None) -> bytes:
    """Genera un .xlsx del usuario activo (o user_id explícito). Devuelve los bytes."""
    uid = user_id if user_id is not None else require_current_user_id()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _hoja_diario(conn, writer, uid)
        _hoja_mensual(conn, writer, uid)
        _hoja_categorias(conn, writer, uid)
        _hoja_resumen(conn, writer, uid)
    buf.seek(0)
    return buf.getvalue()


def _hoja_diario(conn: sqlite3.Connection, writer: pd.ExcelWriter, uid: int) -> None:
    df = load_transactions(conn, user_id=uid)
    if df.empty:
        pd.DataFrame(columns=["Fecha", "Motivo", "Pasivos", "Ingresos", "Caja", "Comentario"]).to_excel(
            writer, sheet_name="Diario", index=False
        )
        return

    df = df.sort_values(["fecha", "id"]).reset_index(drop=True)
    df["caja"] = saldo_inicial(conn, user_id=uid) + (df["ingresos"] - df["pasivos"]).cumsum()

    cats_full = load_categorias_full(conn, user_id=uid)
    df["grupo"] = df["motivo"].map(lambda m: cats_full.get(m, ("Sin categorizar", None))[0])
    df["subcategoria"] = df["motivo"].map(lambda m: cats_full.get(m, ("", None))[1] or "")

    out = pd.DataFrame({
        "Fecha": df["fecha"].dt.strftime("%d/%m/%Y"),
        "Motivo": df["motivo"],
        "Grupo": df["grupo"],
        "Subcategoría": df["subcategoria"],
        "Pasivos": df["pasivos"],
        "Ingresos": df["ingresos"],
        "Caja": df["caja"],
        "Comentario": df["comentario"].fillna(""),
    })
    out.to_excel(writer, sheet_name="Diario", index=False)


def _hoja_mensual(conn: sqlite3.Connection, writer: pd.ExcelWriter, uid: int) -> None:
    """Tabla pivot tipo Excel: motivo en filas, meses en columnas (PREVISIÓN | REALIDAD)."""
    prev = pd.read_sql_query(
        "SELECT motivo, anio, mes, monto_previsto FROM presupuesto WHERE user_id = ?",
        conn, params=(uid,),
    )
    if prev.empty:
        pd.DataFrame(columns=["Motivo"]).to_excel(writer, sheet_name="Mensual", index=False)
        return

    real = pd.read_sql_query(
        """
        SELECT motivo,
               CAST(strftime('%Y', fecha) AS INTEGER) AS anio,
               CAST(strftime('%m', fecha) AS INTEGER) AS mes,
               SUM(pasivos)  AS pasivos,
               SUM(ingresos) AS ingresos
        FROM transacciones
        WHERE user_id = ?
        GROUP BY motivo, anio, mes
        """,
        conn, params=(uid,),
    )

    cats_full = load_categorias_full(conn, user_id=uid)

    def _real_value(row):
        g = cats_full.get(row["motivo"], ("Sin categorizar", None))[0]
        return row["ingresos"] if g == "Ingreso" else row["pasivos"]

    if not real.empty:
        real["realidad"] = real.apply(_real_value, axis=1)

    # Pivot: motivo × (mes, columna).
    pivot_prev = prev.pivot_table(
        index="motivo", columns=["anio", "mes"], values="monto_previsto", aggfunc="sum"
    ).fillna(0)
    pivot_real = real.pivot_table(
        index="motivo", columns=["anio", "mes"], values="realidad", aggfunc="sum"
    ).fillna(0) if not real.empty else pd.DataFrame(index=pivot_prev.index)

    # Combinar: para cada (anio, mes), pares (PREVISIÓN, REALIDAD).
    columnas_meses = sorted(set(pivot_prev.columns) | set(pivot_real.columns))
    rows_out = []
    for motivo in sorted(set(pivot_prev.index) | set(pivot_real.index)):
        row = {"Motivo": motivo}
        for anio, mes in columnas_meses:
            row[f"{mes:02d}/{anio} PREVISIÓN"] = pivot_prev.loc[motivo, (anio, mes)] if (anio, mes) in pivot_prev.columns and motivo in pivot_prev.index else 0
            row[f"{mes:02d}/{anio} REALIDAD"] = pivot_real.loc[motivo, (anio, mes)] if (anio, mes) in pivot_real.columns and motivo in pivot_real.index else 0
        rows_out.append(row)

    pd.DataFrame(rows_out).to_excel(writer, sheet_name="Mensual", index=False)


def _hoja_categorias(conn: sqlite3.Connection, writer: pd.ExcelWriter, uid: int) -> None:
    cats_full = load_categorias_full(conn, user_id=uid)
    df = pd.DataFrame(
        sorted(
            [{"Motivo": m, "Grupo": g, "Subcategoría": s or ""} for m, (g, s) in cats_full.items()],
            key=lambda r: (r["Grupo"], r["Motivo"]),
        )
    )
    df.to_excel(writer, sheet_name="Categorías", index=False)


def _hoja_resumen(conn: sqlite3.Connection, writer: pd.ExcelWriter, uid: int) -> None:
    df = load_transactions(conn, user_id=uid)
    cats = load_categorias_full(conn, user_id=uid)
    saldo = saldo_cuenta_corriente(conn, user_id=uid)
    fondo = fondo_emergencia_usd(conn, user_id=uid)
    kpis = compute_kpis(df, cats, fondo_usd=fondo, saldo_cc=saldo)

    rows = [
        ("Snapshot generado", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Meses cubiertos", kpis["meses_cubiertos"]),
        ("Ingreso anual", kpis["ingreso_anual"]),
        ("Ingreso/mes", kpis["ingreso_mes"]),
        ("Gasto anual (consumo)", kpis["gasto_anual"]),
        ("Gasto/mes (consumo)", kpis["gasto_mes"]),
        ("Gasto fijo anual", kpis["fijo_anual"]),
        ("Gasto fijo/mes", kpis["fijo_mes"]),
        ("Gasto variable anual", kpis["variable_anual"]),
        ("Gasto variable/mes", kpis["variable_mes"]),
        ("Inversión / Ahorro anual", kpis["inversion_anual"]),
        ("Inversión / Ahorro mes", kpis["inversion_mes"]),
        ("Desahorro anual", kpis["desahorro_anual"]),
        ("Desahorro/mes", kpis["desahorro_mes"]),
        ("% gasto fijo", f"{kpis['pct_fijo'] * 100:.2f}%"),
        ("% gasto variable", f"{kpis['pct_variable'] * 100:.2f}%"),
        ("% inversión", f"{kpis['pct_inversion'] * 100:.2f}%"),
        ("% resto", f"{kpis['pct_resto'] * 100:.2f}%"),
        ("Saldo cuenta corriente (ARS)", kpis["saldo_cc"]),
        ("Fondo emergencia (USD)", kpis["fondo_usd"]),
    ]
    pd.DataFrame(rows, columns=["Métrica", "Valor"]).to_excel(
        writer, sheet_name="Resumen", index=False
    )
