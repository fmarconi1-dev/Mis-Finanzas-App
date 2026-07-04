"""Vista Mensual: Previsión vs Realidad con totales y filtros."""

from __future__ import annotations

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from core.budget import (
    comparativa_mes,
    copiar_previsto_a_anio,
    delete_presupuesto,
    meses_con_datos,
    previsiones_editor,
    upsert_presupuesto,
)
from core.db import connect, get_db_path
from core.metrics import load_categorias_full, load_categorias_map
from ui.helpers._format import fmt_ars
from ui.helpers._theme import COLOR_DESAHORRO, COLOR_INGRESO
from ui.helpers._tour import render_tour_panel


_MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


_GRUPOS_GASTO = ("Gasto Fijo", "Gasto Variable")
_GRUPOS_INVERSION = ("Inversion",)


def _totales(df: pd.DataFrame) -> dict:
    """Calcula totales agrupados con la taxonomía de Fase 2b (disjuntos)."""
    ing_prev = df.loc[df["grupo"] == "Ingreso", "monto_previsto"].sum()
    ing_real = df.loc[df["grupo"] == "Ingreso", "monto_real"].sum()
    gas_prev = df.loc[df["grupo"].isin(_GRUPOS_GASTO), "monto_previsto"].sum()
    gas_real = df.loc[df["grupo"].isin(_GRUPOS_GASTO), "monto_real"].sum()
    inv_prev = df.loc[df["grupo"].isin(_GRUPOS_INVERSION), "monto_previsto"].sum()
    inv_real = df.loc[df["grupo"].isin(_GRUPOS_INVERSION), "monto_real"].sum()
    return {
        "ing_prev": float(ing_prev), "ing_real": float(ing_real),
        "gas_prev": float(gas_prev), "gas_real": float(gas_real),
        "inv_prev": float(inv_prev), "inv_real": float(inv_real),
        # Saldo mensual = entrada de cash - salida de cash (gasto + inversion).
        "saldo_prev": float(ing_prev - gas_prev - inv_prev),
        "saldo_real": float(ing_real - gas_real - inv_real),
    }


def _pct_consumido(real: float, prev: float) -> float | None:
    """% consumido = real/prev × 100. None si no hay previsión (división por 0)."""
    if not prev:
        return None
    return (real / prev) * 100


def _desvio_pct_100(real: float, prev: float) -> float | None:
    if not prev:
        return None
    return ((real - prev) / prev) * 100


def _build_display_df(
    df: pd.DataFrame, subcats_por_motivo: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Construye la tabla con columnas mixtas: strings (montos con $1.234,56) y
    números (para que `column_config.ProgressColumn` y `NumberColumn` rendericen
    barras y formato de porcentaje correctamente)."""
    base = df.copy()
    base["_pct_real_prev"] = base.apply(
        lambda r: _pct_consumido(r["monto_real"], r["monto_previsto"]), axis=1
    )

    subs_map = subcats_por_motivo or {}
    subs_col = base["motivo"].map(lambda m: subs_map.get(m, "") or "—")

    rows = pd.DataFrame({
        "Motivo": base["motivo"],
        "Subcategoría": subs_col,
        "Grupo": base["grupo"],
        "Previsión": base["monto_previsto"].map(fmt_ars),
        "Realidad": base["monto_real"].map(fmt_ars),
        "Desvío": base["desvio_abs"].map(fmt_ars),
        "Desvío %": base["desvio_pct"] * 100,           # numérico para NumberColumn
        "Consumido": base["_pct_real_prev"],            # numérico para ProgressColumn
    })

    # Totales (preservan numeric en las dos últimas columnas).
    t = _totales(df)
    totales = pd.DataFrame([
        {"Motivo": "TOTAL INGRESOS", "Subcategoría": "", "Grupo": "",
         "Previsión": fmt_ars(t["ing_prev"]),
         "Realidad": fmt_ars(t["ing_real"]),
         "Desvío": fmt_ars(t["ing_real"] - t["ing_prev"]),
         "Desvío %": _desvio_pct_100(t["ing_real"], t["ing_prev"]),
         "Consumido": _pct_consumido(t["ing_real"], t["ing_prev"])},
        {"Motivo": "TOTAL GASTOS (consumo)", "Subcategoría": "", "Grupo": "",
         "Previsión": fmt_ars(t["gas_prev"]),
         "Realidad": fmt_ars(t["gas_real"]),
         "Desvío": fmt_ars(t["gas_real"] - t["gas_prev"]),
         "Desvío %": _desvio_pct_100(t["gas_real"], t["gas_prev"]),
         "Consumido": _pct_consumido(t["gas_real"], t["gas_prev"])},
        {"Motivo": "TOTAL INVERSIÓN / AHORRO", "Subcategoría": "", "Grupo": "",
         "Previsión": fmt_ars(t["inv_prev"]),
         "Realidad": fmt_ars(t["inv_real"]),
         "Desvío": fmt_ars(t["inv_real"] - t["inv_prev"]),
         "Desvío %": _desvio_pct_100(t["inv_real"], t["inv_prev"]),
         "Consumido": _pct_consumido(t["inv_real"], t["inv_prev"])},
        {"Motivo": "SALDO MENSUAL", "Subcategoría": "", "Grupo": "",
         "Previsión": fmt_ars(t["saldo_prev"]),
         "Realidad": fmt_ars(t["saldo_real"]),
         "Desvío": fmt_ars(t["saldo_real"] - t["saldo_prev"]),
         "Desvío %": None,
         "Consumido": None},
    ])
    return pd.concat([rows, totales], ignore_index=True)


def render() -> None:
    render_tour_panel("mensual")
    db_path = get_db_path()

    with connect(db_path) as conn:
        meses_disponibles = meses_con_datos(conn)

    if not meses_disponibles:
        st.info("No hay transacciones cargadas. Corré la ingesta primero.")
        return

    # ---------- Filtros ----------

    anios = sorted({a for (a, _) in meses_disponibles})
    col1, col2 = st.columns([1, 1])
    anio = col1.selectbox("Año", anios, index=len(anios) - 1)
    meses = sorted({m for (a, m) in meses_disponibles if a == anio})
    mes = col2.selectbox(
        "Mes", meses,
        index=len(meses) - 1,
        format_func=lambda m: _MESES_ES[m],
    )

    with connect(db_path) as conn:
        cats = load_categorias_map(conn)
        cats_full = load_categorias_full(conn)
        df = comparativa_mes(conn, anio, mes, categorias=cats)

    # Mapping motivo → subcategoria para enriquecer la tabla de display.
    subcats_por_motivo = {m: (s or "—") for m, (_, s) in cats_full.items()}

    if df.empty:
        with st.container(border=True):
            st.markdown(f"### 📭 Sin movimientos en {_MESES_ES[mes]} {anio}")
            st.markdown(
                "No hay ni transacciones cargadas ni presupuesto definido para "
                "este mes. Probá:"
            )
            st.markdown(
                "- Elegir otro mes en el selector de arriba.\n"
                "- Ir a `➕ Transacciones` y cargar la primera del mes."
            )
        return

    # ---------- Tabla con totales y barras de progreso ----------

    st.subheader(f"Previsión vs Realidad — {_MESES_ES[mes]} {anio}")
    df_disp = _build_display_df(df, subcats_por_motivo=subcats_por_motivo)
    st.dataframe(
        df_disp, width="stretch", hide_index=True,
        height=min(600, 38 * (len(df_disp) + 1)),
        column_config={
            "Desvío %": st.column_config.NumberColumn(
                "Desvío %",
                help="Diferencia % entre realidad y previsión. "
                     "Positivo = real arriba de lo previsto.",
                format="%+.1f%%",
            ),
            "Consumido": st.column_config.ProgressColumn(
                "Consumido",
                help="Realidad como % de la previsión. Si supera 100%, te "
                     "pasaste del presupuesto (en gastos) o lo superaste "
                     "(en ingresos / inversión).",
                min_value=0.0,
                max_value=150.0,
                format="%.0f%%",
            ),
        },
    )

    # ---------- Gráfico barras agrupadas ----------

    st.subheader("Comparativa por categoría")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["motivo"], y=df["monto_previsto"],
        name="Previsión", marker_color=COLOR_INGRESO,
    ))
    fig.add_trace(go.Bar(
        x=df["motivo"], y=df["monto_real"],
        name="Realidad", marker_color=COLOR_DESAHORRO,
    ))
    fig.update_layout(
        barmode="group", height=420,
        margin=dict(l=20, r=20, t=10, b=20),
        yaxis_title="ARS",
        xaxis_tickangle=-30,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, width="stretch")

    # ---------- Resumen del mes ----------

    t = _totales(df)

    st.subheader("Resumen del mes")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Ingresos previstos", fmt_ars(t["ing_prev"]))
        st.metric("Ingresos reales", fmt_ars(t["ing_real"]),
                  delta=fmt_ars(t["ing_real"] - t["ing_prev"]))
    with c2:
        st.metric("Gastos previstos (consumo)", fmt_ars(t["gas_prev"]))
        # delta inverso: gastar más es malo → rojo.
        st.metric("Gastos reales (consumo)", fmt_ars(t["gas_real"]),
                  delta=fmt_ars(t["gas_real"] - t["gas_prev"]),
                  delta_color="inverse")
    with c3:
        st.metric("Inversión / Ahorro previsto", fmt_ars(t["inv_prev"]))
        # delta normal: invertir más que lo previsto es bueno → verde.
        st.metric("Inversión / Ahorro real", fmt_ars(t["inv_real"]),
                  delta=fmt_ars(t["inv_real"] - t["inv_prev"]))

    # Línea final: saldo del mes (cash neto).
    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("Saldo mensual previsto", fmt_ars(t["saldo_prev"]),
              help="Ingresos − Gastos − Inversión. Cuánto cash neto te queda al final del mes.")
    c2.metric("Saldo mensual real", fmt_ars(t["saldo_real"]),
              delta=fmt_ars(t["saldo_real"] - t["saldo_prev"]))

    # ---------- Editor de previsiones ----------

    st.divider()
    _render_editor_previsiones(db_path, anio, mes)


def _render_editor_previsiones(db_path, anio: int, mes: int) -> None:
    """Editor inline de la tabla `presupuesto` para el mes seleccionado.

    Permite cambiar el monto previsto por motivo (incluso de motivos sin
    previsión hasta ahora), borrar previsiones (poniendo 0), y aplicar un
    monto a los 12 meses del año de un solo gesto.
    """
    with st.expander(f"✏️ Editar previsiones de {_MESES_ES[mes]} {anio}", expanded=False):
        with connect(db_path) as conn:
            datos = previsiones_editor(conn, anio, mes)
            cats_full = load_categorias_full(conn)

        if not datos:
            st.info(
                "Todavía no tenés categorías cargadas. Andá a `⚙️ Configuración` "
                "para crear las primeras."
            )
            return

        df_edit = pd.DataFrame(datos)
        # Agregar columna subcategoría (read-only) para desambiguar el motivo.
        df_edit["subcategoria"] = df_edit["motivo"].map(
            lambda m: (cats_full.get(m, ("", None))[1]) or "—"
        )
        df_edit = df_edit.rename(columns={
            "motivo": "Motivo", "grupo": "Grupo",
            "subcategoria": "Subcategoría", "previsto": "Previsto",
        })

        st.caption(
            "Modificá el **Previsto** por fila. Cambios con `Guardar` los persiste "
            "(con backup automático). Para borrar una previsión existente, ponela en 0."
        )

        edited = st.data_editor(
            df_edit,
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            height=min(500, 38 * (len(df_edit) + 1)),
            column_config={
                "Motivo": st.column_config.TextColumn("Motivo", disabled=True),
                "Subcategoría": st.column_config.TextColumn("Subcategoría", disabled=True),
                "Grupo": st.column_config.TextColumn("Grupo", disabled=True),
                "Previsto": st.column_config.NumberColumn(
                    "Previsto (ARS)",
                    min_value=0.0,
                    step=1000.0,
                    format="$ %.0f",
                    help="0 = sin previsión (se borra la fila si existía).",
                ),
            },
            key=f"presup_editor_{anio}_{mes}",
        )

        # Diff vs original.
        cambios = []
        for i in range(len(df_edit)):
            old_val = float(df_edit.iloc[i]["Previsto"] or 0)
            new_val = float(edited.iloc[i]["Previsto"] or 0)
            if abs(old_val - new_val) > 0.01:
                cambios.append((edited.iloc[i]["Motivo"], new_val))

        if cambios:
            c1, c2 = st.columns([1, 4])
            if c1.button(f"💾 Guardar {len(cambios)} cambio(s)",
                         type="primary", key=f"save_presup_{anio}_{mes}"):
                with connect(db_path) as conn:
                    for motivo, nuevo in cambios:
                        if nuevo <= 0:
                            delete_presupuesto(conn, motivo, anio, mes)
                        else:
                            upsert_presupuesto(conn, motivo, anio, mes, nuevo)
                st.toast(f"✅ {len(cambios)} previsión(es) actualizadas",
                         icon="💾")
                st.rerun()
            c2.info(
                f"Tenés **{len(cambios)} cambio(s) pendiente(s)**. "
                "Hacé clic en Guardar para persistir."
            )

        # ---------- Bulk: copiar al año entero ----------

        st.divider()
        st.markdown(f"**Copiar previsión a los 12 meses de {anio}**")
        st.caption(
            "Útil para gastos fijos que son iguales todo el año (ej. Expensas, "
            "Servicios). Sobrescribe las previsiones existentes para ese motivo."
        )
        cb1, cb2, cb3 = st.columns([2, 2, 1])
        motivos_disponibles = [d["motivo"] for d in datos]
        bulk_motivo = cb1.selectbox(
            "Motivo", motivos_disponibles, key=f"bulk_motivo_{anio}",
        )
        bulk_monto = cb2.number_input(
            "Monto mensual",
            min_value=0.0, step=1000.0, format="%.2f",
            key=f"bulk_monto_{anio}",
        )
        if cb3.button("Aplicar al año", width="stretch",
                      key=f"bulk_apply_{anio}"):
            if bulk_monto <= 0:
                st.error("El monto debe ser mayor a 0.")
            else:
                with connect(db_path) as conn:
                    copiar_previsto_a_anio(conn, bulk_motivo, anio, bulk_monto)
                st.toast(
                    f"📅 «{bulk_motivo}» seteado a {fmt_ars(bulk_monto)}/mes "
                    f"durante todo {anio}", icon="📅",
                )
                st.rerun()
