"""Vista Libro Diario: movimientos individuales de los últimos N días."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.db import connect, get_db_path
from core.diario import libro_diario
from ui.helpers._format import fmt_ars
from ui.helpers._tour import render_tour_panel


def render() -> None:
    render_tour_panel("diario")
    db_path = get_db_path()

    c_title, c_dias = st.columns([3, 1])
    with c_title:
        st.subheader("Libro Diario")
        st.caption(
            "Movimientos fila por fila de los últimos N días, con el saldo de "
            "Caja después de cada uno. Para detectar cargas faltantes o "
            "duplicadas a primera vista."
        )
    with c_dias:
        dias = st.number_input(
            "Últimos N días", min_value=1, max_value=180, value=7, step=1,
            key="diario_dias",
        )

    with connect(db_path) as conn:
        df = libro_diario(conn, dias=int(dias))

    if df.empty:
        with st.container(border=True):
            st.markdown(f"### 🗓️ Nada en los últimos {dias} días")
            st.markdown(
                "Probá ampliar la ventana arriba (subí los días), o si "
                "olvidaste cargar algo, andá a `➕ Transacciones`."
            )
        return

    # ---------- Resumen del período ----------

    total_ing = float(df["ingresos"].sum())
    total_egr = float(df["pasivos"].sum())
    saldo_neto = total_ing - total_egr

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Movimientos", f"{len(df)}")
    c2.metric("Ingresos del período", fmt_ars(total_ing))
    c3.metric("Egresos del período", fmt_ars(total_egr))
    c4.metric(
        "Resultado neto", fmt_ars(saldo_neto),
        delta=f"{(saldo_neto / total_ing * 100):.1f}% de los ingresos"
        if total_ing > 0 else None,
    )

    st.divider()

    # ---------- Tabla fila por fila ----------

    df_disp = pd.DataFrame({
        "Fecha": df["fecha"].dt.strftime("%d/%m/%Y"),
        "Motivo": df["motivo"],
        "Grupo": df["grupo"],
        "Subcategoría": df["subcategoria"].fillna("—"),
        "Egreso": df["pasivos"].apply(lambda v: fmt_ars(v) if v > 0 else ""),
        "Ingreso": df["ingresos"].apply(lambda v: fmt_ars(v) if v > 0 else ""),
        "Saldo después": df["caja_despues"].apply(fmt_ars),
        "Comentario": df["comentario"].fillna(""),
    })

    st.dataframe(
        df_disp, width="stretch", hide_index=True,
        height=min(700, 38 * (len(df_disp) + 1)),
    )

    # ---------- Resumen por grupo ----------

    st.subheader("Resumen del período por grupo")
    resumen = (
        df.groupby("grupo", as_index=False)
        .agg(
            ingresos=("ingresos", "sum"),
            egresos=("pasivos", "sum"),
            movimientos=("id", "count"),
        )
        .sort_values("egresos", ascending=False)
    )
    resumen_disp = pd.DataFrame({
        "Grupo": resumen["grupo"],
        "Movimientos": resumen["movimientos"],
        "Ingresos": resumen["ingresos"].apply(fmt_ars),
        "Egresos": resumen["egresos"].apply(fmt_ars),
        "Neto": (resumen["ingresos"] - resumen["egresos"]).apply(fmt_ars),
    })
    st.dataframe(resumen_disp, width="stretch", hide_index=True)
