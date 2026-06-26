"""Cálculo de KPIs anuales/mensuales y distribución %.

**Fase 2b — nueva fórmula limpia** (a partir de Mayo 2026):

  Los buckets ahora son DISJUNTOS:

    fijo + variable + inversion + resto = 100%

  Donde:
    fijo      = Gasto Fijo (Auto, Servicios, Impuestos, Expensas, Pago tarjeta)
    variable  = Gasto Variable (Compras, Salidas, Viajes, Transportes)
                — NO incluye Inversiones ni Compra Divisa
    inversion = Macro "Inversion" (Inversiones + Compra Divisa)
    resto     = lo que queda del ingreso sin asignar

  Adicionalmente, motivos "duales" (hoy sólo "Inversiones") se reclasifican
  según dirección del flujo:
    - "Inversiones" como egreso (pasivo) → Inversion/Activos financieros
    - "Inversiones" como ingreso         → Ingreso/Desahorro

  "Venta divisa" siempre es Ingreso/Desahorro (es liquidación de ahorro).

Comparación con el Excel original (Mensual.csv, taxonomía vieja):
    Excel viejo:    fijo 28.47%  |  variable 59.89%  |  inv 9.06%  |  resto 2.58%
    Fórmula nueva:  fijo 28.47%  |  variable 35.28%  |  inv 24.61% |  resto 11.64%
    Diferencia: Compra Divisa ($2.33M) se mueve de variable → inversion.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

import pandas as pd

from core.categorizer import (
    DEFAULT_CATEGORIAS,
    DEFAULT_GRUPOS,
    efective_grupo,
)
from core.current_user import require_current_user_id
from core.db import get_config


def _uid(user_id: Optional[int]) -> int:
    return user_id if user_id is not None else require_current_user_id()


def anios_con_datos(df: pd.DataFrame) -> list[int]:
    """Años calendario presentes en el DataFrame de transacciones."""
    if df.empty:
        return []
    return sorted(int(a) for a in df["fecha"].dt.year.unique())


def filtrar_anio(df: pd.DataFrame, anio: Optional[int]) -> pd.DataFrame:
    """Filtra transacciones a un año calendario (premortem #3, F3/R4).

    Los KPIs "anuales" deben calcularse sobre UN año: sin este filtro, a
    partir del segundo año calendario el dashboard suma toda la historia
    ("Ingreso anual" de 13+ meses, promedios diluidos, % sin sentido).
    """
    if df.empty or anio is None:
        return df
    return df[df["fecha"].dt.year == int(anio)].reset_index(drop=True)


def load_transactions(
    conn: sqlite3.Connection, user_id: Optional[int] = None
) -> pd.DataFrame:
    """Carga las transacciones del usuario activo, ordenadas por fecha, id."""
    uid = _uid(user_id)
    df = pd.read_sql_query(
        "SELECT id, fecha, pasivos, ingresos, motivo, comentario "
        "FROM transacciones WHERE user_id = ? ORDER BY fecha, id",
        conn, params=(uid,),
    )
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def load_categorias_map(
    conn: sqlite3.Connection, user_id: Optional[int] = None
) -> dict[str, str]:
    """Mapping {motivo: grupo} del usuario activo. Devuelve {} si no hay categorías."""
    uid = _uid(user_id)
    rows = conn.execute(
        "SELECT motivo, grupo FROM categorias WHERE user_id = ?", (uid,)
    ).fetchall()
    return {row["motivo"]: row["grupo"] for row in rows}


def load_categorias_full(
    conn: sqlite3.Connection, user_id: Optional[int] = None
) -> dict[str, tuple[str, Optional[str]]]:
    """Mapping {motivo: (grupo, subcategoria)} del usuario activo. {} si está vacío."""
    uid = _uid(user_id)
    rows = conn.execute(
        "SELECT motivo, grupo, subcategoria FROM categorias WHERE user_id = ?",
        (uid,),
    ).fetchall()
    return {r["motivo"]: (r["grupo"], r["subcategoria"]) for r in rows}


def saldo_inicial(conn: sqlite3.Connection, user_id: Optional[int] = None) -> float:
    return float(get_config(conn, "saldo_inicial_caja", "0", user_id=user_id) or 0.0)


def fondo_emergencia_usd(
    conn: sqlite3.Connection, user_id: Optional[int] = None
) -> float:
    return float(get_config(conn, "fondo_emergencia_usd", "0", user_id=user_id) or 0.0)


def saldo_cuenta_corriente(
    conn: sqlite3.Connection, user_id: Optional[int] = None
) -> float:
    """Caja actual del usuario = saldo_inicial + sum(ingresos - pasivos)."""
    uid = _uid(user_id)
    row = conn.execute(
        "SELECT COALESCE(SUM(ingresos - pasivos), 0) AS delta "
        "FROM transacciones WHERE user_id = ?",
        (uid,),
    ).fetchone()
    return saldo_inicial(conn, user_id=uid) + float(row["delta"])


def caja_historico(
    conn: sqlite3.Connection, user_id: Optional[int] = None
) -> pd.DataFrame:
    """Serie temporal del saldo del usuario activo."""
    uid = _uid(user_id)
    df = load_transactions(conn, user_id=uid)
    if df.empty:
        return pd.DataFrame(columns=["fecha", "caja"])
    df = df.copy()
    df["delta"] = df["ingresos"] - df["pasivos"]
    df["caja"] = saldo_inicial(conn, user_id=uid) + df["delta"].cumsum()
    return df[["fecha", "caja"]]


def caja_diaria_con_medias(
    conn: sqlite3.Connection,
    ventanas: tuple[int, ...] = (7, 14),
    user_id: Optional[int] = None,
) -> pd.DataFrame:
    """Saldo de Caja resampleado a frecuencia diaria + medias móviles.

    El saldo "real" (columna `caja`) usa forward-fill: si un día no hubo
    transacciones, queda con el último saldo conocido. Después se aplican
    rolling means para suavizar el patrón "serrucho" de cobrar a fin de mes
    y pagar todo junto.

    Cols devueltas: fecha (1 fila por día), caja, caja_ma{ventana} para cada
    ventana solicitada.
    """
    base = caja_historico(conn, user_id=user_id)
    if base.empty:
        return base

    # Si hubo múltiples movimientos en el mismo día, nos quedamos con el
    # último saldo del día.
    diario = (
        base.set_index("fecha")
        .resample("D")["caja"]
        .last()
        .ffill()
        .to_frame()
        .reset_index()
    )

    for v in ventanas:
        diario[f"caja_ma{v}"] = (
            diario["caja"].rolling(window=v, min_periods=1).mean()
        )
    return diario


def _aplicar_grupo_efectivo(
    df: pd.DataFrame, cats_full: dict[str, tuple[str, Optional[str]]]
) -> pd.DataFrame:
    """Agrega columnas `grupo` y `subcategoria` aplicando reglas duales fila a fila.

    Para motivos en MOTIVOS_DUAL_DESAHORRO (hoy: "Inversiones"), si la fila
    viene como ingreso (ingresos>0, pasivos==0), el grupo se reclasifica a
    Ingreso/Desahorro.
    """
    df = df.copy()
    grupos = []
    subs = []
    for _, row in df.iterrows():
        g, s = efective_grupo(
            row["motivo"], float(row["pasivos"]), float(row["ingresos"]), cats_full
        )
        grupos.append(g)
        subs.append(s)
    df["grupo"] = grupos
    df["subcategoria"] = subs
    return df


def compute_kpis(
    df: pd.DataFrame,
    categorias: dict,
    fondo_usd: float = 0.0,
    saldo_cc: Optional[float] = None,
) -> dict:
    """Calcula los KPIs del dashboard con la fórmula disjunta (Fase 2b).

    Args:
        df: DataFrame con columnas fecha, pasivos, ingresos, motivo.
        categorias: puede ser {motivo: grupo} (legacy) o {motivo: (grupo, subcat)}.
            Si es legacy, se conserva pero las subcategorías quedan en None.
        fondo_usd, saldo_cc: igual que antes.

    Returns:
        Dict con métricas. fijo + variable + inversion + resto = 100% (disjuntos).
    """
    if df.empty:
        return {
            "ingreso_anual": 0.0, "ingreso_mes": 0.0,
            "gasto_anual": 0.0, "gasto_mes": 0.0,
            "fijo_anual": 0.0, "fijo_mes": 0.0,
            "variable_anual": 0.0, "variable_mes": 0.0,
            "inversion_anual": 0.0, "inversion_mes": 0.0,
            "desahorro_anual": 0.0, "desahorro_mes": 0.0,
            "pct_fijo": 0.0, "pct_variable": 0.0,
            "pct_inversion": 0.0, "pct_resto": 0.0,
            "saldo_cc": saldo_cc or 0.0,
            "fondo_usd": fondo_usd,
            "meses_cubiertos": 1,
        }

    # Aceptar tanto legacy {motivo: grupo} como nuevo {motivo: (grupo, sub)}.
    sample = next(iter(categorias.values()), None)
    if isinstance(sample, tuple):
        cats_full = categorias
    else:
        cats_full = {m: (g, None) for m, g in categorias.items()}

    df = _aplicar_grupo_efectivo(df, cats_full)

    # Buckets DISJUNTOS: variable e inversion no se solapan.
    ingreso_anual = float(df.loc[df["grupo"] == "Ingreso", "ingresos"].sum())
    fijo_anual = float(df.loc[df["grupo"] == "Gasto Fijo", "pasivos"].sum())
    variable_anual = float(df.loc[df["grupo"] == "Gasto Variable", "pasivos"].sum())
    inversion_anual = float(df.loc[df["grupo"] == "Inversion", "pasivos"].sum())
    desahorro_anual = float(
        df.loc[df["subcategoria"] == "Desahorro", "ingresos"].sum()
    )
    gasto_anual = fijo_anual + variable_anual  # consumo puro, sin inversion

    meses_cubiertos = max(1, int(df["fecha"].dt.to_period("M").nunique()))

    # Porcentajes (fijo + variable + inversion + resto = 100%).
    if ingreso_anual > 0:
        pct_fijo = fijo_anual / ingreso_anual
        pct_variable = variable_anual / ingreso_anual
        pct_inversion = inversion_anual / ingreso_anual
        pct_resto = 1 - pct_fijo - pct_variable - pct_inversion
    else:
        pct_fijo = pct_variable = pct_inversion = pct_resto = 0.0

    return {
        "ingreso_anual": ingreso_anual,
        "ingreso_mes": ingreso_anual / meses_cubiertos,
        "gasto_anual": gasto_anual,
        "gasto_mes": gasto_anual / meses_cubiertos,
        "fijo_anual": fijo_anual,
        "fijo_mes": fijo_anual / meses_cubiertos,
        "variable_anual": variable_anual,
        "variable_mes": variable_anual / meses_cubiertos,
        "inversion_anual": inversion_anual,
        "inversion_mes": inversion_anual / meses_cubiertos,
        "desahorro_anual": desahorro_anual,
        "desahorro_mes": desahorro_anual / meses_cubiertos,
        "pct_fijo": pct_fijo,
        "pct_variable": pct_variable,
        "pct_inversion": pct_inversion,
        "pct_resto": pct_resto,
        "saldo_cc": saldo_cc if saldo_cc is not None else 0.0,
        "fondo_usd": fondo_usd,
        "meses_cubiertos": meses_cubiertos,
    }


def _normalize_cats(categorias: dict) -> dict[str, tuple[str, Optional[str]]]:
    """Acepta {motivo: grupo} legacy o {motivo: (grupo, sub)} nuevo. Devuelve el nuevo."""
    if not categorias:
        return {}
    sample = next(iter(categorias.values()))
    if isinstance(sample, tuple):
        return categorias
    return {m: (g, None) for m, g in categorias.items()}


def gasto_por_categoria(
    df: pd.DataFrame,
    categorias: dict,
    anio: Optional[int] = None,
    mes: Optional[int] = None,
) -> pd.DataFrame:
    """Suma de Pasivos por motivo y grupo, con reglas duales aplicadas.

    Devuelve cols: motivo, grupo, gasto.
    """
    if df.empty:
        return pd.DataFrame(columns=["motivo", "grupo", "gasto"])

    cats_full = _normalize_cats(categorias)
    df = _aplicar_grupo_efectivo(df, cats_full)

    if anio is not None:
        df = df[df["fecha"].dt.year == anio]
    if mes is not None:
        df = df[df["fecha"].dt.month == mes]

    df = df[df["grupo"] != "Ingreso"]
    if df.empty:
        return pd.DataFrame(columns=["motivo", "grupo", "gasto"])

    return (
        df.groupby(["motivo", "grupo"], as_index=False)["pasivos"]
        .sum()
        .rename(columns={"pasivos": "gasto"})
        .sort_values("gasto", ascending=False)
        .reset_index(drop=True)
    )


def ingresos_vs_gastos_mensual(
    df: pd.DataFrame, categorias: dict
) -> pd.DataFrame:
    """Totales de ingresos y gastos (consumo) por mes, con reglas duales.

    Cols: periodo (Timestamp), ingresos, gastos.
    Nota: "gastos" acá = fijo + variable. NO incluye Inversion (que es ahorro).
    """
    if df.empty:
        return pd.DataFrame(columns=["periodo", "ingresos", "gastos"])

    cats_full = _normalize_cats(categorias)
    df = _aplicar_grupo_efectivo(df, cats_full)
    df["periodo"] = df["fecha"].dt.to_period("M").dt.to_timestamp()

    ingresos = (
        df[df["grupo"] == "Ingreso"]
        .groupby("periodo", as_index=False)["ingresos"]
        .sum()
    )
    gastos = (
        df[df["grupo"].isin(["Gasto Fijo", "Gasto Variable"])]
        .groupby("periodo", as_index=False)["pasivos"]
        .sum()
        .rename(columns={"pasivos": "gastos"})
    )

    merged = pd.merge(ingresos, gastos, on="periodo", how="outer").fillna(0)
    return merged.sort_values("periodo").reset_index(drop=True)
