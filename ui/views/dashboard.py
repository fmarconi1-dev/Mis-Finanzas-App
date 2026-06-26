"""Vista Dashboard: KPIs + gráficos + editor inline de Fondo USD."""

from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from core.db import connect, get_db_path, set_config
from core.metrics import (
    anios_con_datos,
    caja_diaria_con_medias,
    compute_kpis,
    filtrar_anio,
    fondo_emergencia_usd,
    gasto_por_categoria,
    ingresos_vs_gastos_mensual,
    load_categorias_full,
    load_transactions,
    saldo_cuenta_corriente,
)
from ui.helpers._format import fmt_ars, fmt_ars_corto, fmt_pct, fmt_usd
from ui.helpers._theme import (
    COLOR_ACENTO,
    COLOR_ACENTO_BG,
    COLOR_GASTO,
    COLOR_INGRESO,
    COLOR_POR_GRUPO,
    COLORES_MA,
)
from ui.helpers._tour import render_tour_panel


def _save_fondo_usd_callback():
    """Callback que persiste el fondo USD cuando cambia el number_input.

    Los callbacks de Streamlit corren en un contexto separado del script, así
    que el contextvar `current_user_id` no se propaga. Leemos el user_id de
    `st.session_state` directamente y se lo pasamos a set_config.
    """
    user_id = st.session_state.get("current_user_id")
    if user_id is None:
        return
    nuevo = float(st.session_state.fondo_usd_input)
    with connect() as conn:
        set_config(conn, "fondo_emergencia_usd", f"{nuevo:.2f}", user_id=user_id)


def render() -> None:
    render_tour_panel("dashboard")
    db_path = get_db_path()

    # Saludo personalizado (sutil): usar el primer nombre del fullname si existe.
    # Nota: usamos markdown nativo (sin HTML inline) porque Streamlit ≥1.41
    # ignora unsafe_allow_html para contenido inline y lo renderiza como texto.
    fullname = st.session_state.get("current_user_fullname") or ""
    if fullname:
        primer_nombre = fullname.split()[0]
        st.markdown(f"👋 Hola, **{primer_nombre}**")

    with connect(db_path) as conn:
        df = load_transactions(conn)
        cats = load_categorias_full(conn)
        saldo = saldo_cuenta_corriente(conn)
        fondo = fondo_emergencia_usd(conn)

    # ---------- Empty state amable para usuarios nuevos ----------

    if df.empty:
        nombre_full = st.session_state.get("current_user_fullname") or ""
        nombre = nombre_full.split()[0] if nombre_full else "vos"
        with st.container(border=True):
            st.markdown(f"### 👋 Hola, {nombre}")
            st.markdown(
                "Tu radar está esperando datos. **Cargá tu primera transacción** "
                "desde la pestaña `➕ Transacciones` y los KPIs van a aparecer acá."
            )
            st.caption(
                "💡 **Tip:** podés usar expresiones aritméticas en el importe — "
                "tipo `8500 + 3200 - 500` para sumar varios ítems en una sola fila."
            )
        return

    # ---------- Selector de año (fix premortem #3: KPIs realmente anuales) ----------

    anios = anios_con_datos(df)
    if len(anios) > 1:
        c_anio, c_resto = st.columns([1, 5])
        anio_sel = c_anio.selectbox(
            "Año", anios, index=len(anios) - 1, key="dash_anio",
            help="Los KPIs, los gastos por categoría y el gráfico de "
                 "Ingresos vs Gastos se calculan sobre este año. "
                 "La evolución de Caja siempre muestra la serie completa.",
        )
    else:
        anio_sel = anios[0]

    df_anio = filtrar_anio(df, anio_sel)
    kpis = compute_kpis(df_anio, cats, fondo_usd=fondo, saldo_cc=saldo)
    df_iva_gtos = ingresos_vs_gastos_mensual(df_anio, cats)
    df_cat = gasto_por_categoria(df_anio, cats)

    # ---------- Ancla de confianza ----------

    ultima = df["fecha"].max()
    st.caption(
        f"Última transacción cargada: **{ultima.strftime('%d/%m/%Y')}** "
        f"· **{len(df_anio)}** movimientos en {kpis['meses_cubiertos']} meses "
        f"de {anio_sel}"
    )

    # ---------- Liquidez y resguardo ----------

    with st.container(border=True):
        st.subheader("Liquidez y resguardo")
        c1, c2 = st.columns(2)
        c1.metric("Saldo cuenta corriente (ARS)", fmt_ars(kpis["saldo_cc"]))
        with c2:
            st.metric("Fondo de emergencia (USD)", fmt_usd(kpis["fondo_usd"]))
            with st.expander("Editar fondo USD"):
                st.number_input(
                    "Nuevo monto USD",
                    min_value=0.0,
                    value=float(kpis["fondo_usd"]),
                    step=100.0,
                    format="%.2f",
                    key="fondo_usd_input",
                    on_change=_save_fondo_usd_callback,
                    help="Se guarda automáticamente al cambiar. Sólo informativo, "
                         "no se convierte a ARS.",
                )

    # ---------- KPIs anuales/mensuales ----------

    with st.container(border=True):
        st.subheader("KPIs anuales y mensuales")
        c1, c2, c3, c4 = st.columns(4)
        # Números cortos en las cards ($15,0M) y el exacto en el help al hover.
        c1.metric("Ingreso anual", fmt_ars_corto(kpis["ingreso_anual"]),
                  help=f"Exacto: {fmt_ars(kpis['ingreso_anual'])}. "
                       f"Promedio: {fmt_ars(kpis['ingreso_mes'])}/mes "
                       f"en {kpis['meses_cubiertos']} meses.")
        c2.metric("Gasto anual (consumo)", fmt_ars_corto(kpis["gasto_anual"]),
                  help=f"Exacto: {fmt_ars(kpis['gasto_anual'])}. "
                       f"Fijo + Variable, sin contar inversión. "
                       f"Promedio: {fmt_ars(kpis['gasto_mes'])}/mes.")
        c3.metric("Gasto fijo anual", fmt_ars_corto(kpis["fijo_anual"]),
                  help=f"Exacto: {fmt_ars(kpis['fijo_anual'])}. "
                       f"Promedio: {fmt_ars(kpis['fijo_mes'])}/mes.")
        c4.metric("Gasto variable anual", fmt_ars_corto(kpis["variable_anual"]),
                  help=f"Exacto: {fmt_ars(kpis['variable_anual'])}. "
                       f"Compras, Salidas, Viajes, Transportes. "
                       f"Promedio: {fmt_ars(kpis['variable_mes'])}/mes.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Inversión / Ahorro anual", fmt_ars_corto(kpis["inversion_anual"]),
                  help=f"Exacto: {fmt_ars(kpis['inversion_anual'])}. "
                       f"Inversiones + Compra Divisa. "
                       f"Promedio: {fmt_ars(kpis['inversion_mes'])}/mes.")
        c2.metric("Desahorro anual", fmt_ars_corto(kpis["desahorro_anual"]),
                  help=f"Exacto: {fmt_ars(kpis['desahorro_anual'])}. "
                       f"Venta de divisa / liquidación de inversiones. "
                       f"Promedio: {fmt_ars(kpis['desahorro_mes'])}/mes.")
        c3.metric("Ingreso/mes", fmt_ars_corto(kpis["ingreso_mes"]),
                  help=f"Exacto: {fmt_ars(kpis['ingreso_mes'])}.")
        delta_neto = kpis["ingreso_mes"] - kpis["gasto_mes"]
        # Delta con signo explícito (+/-) para que Streamlit lo coloree (verde/rojo).
        pct_resultado = (delta_neto / kpis["ingreso_mes"] * 100) if kpis["ingreso_mes"] else 0
        c4.metric(
            "Resultado mensual", fmt_ars_corto(delta_neto),
            delta=f"{pct_resultado:+.1f}% del ingreso" if kpis["ingreso_mes"] else None,
            help=f"Exacto: {fmt_ars(delta_neto)}. "
                 "Ingreso − Gasto de consumo (no descuenta inversión).",
        )

    # ---------- Distribución del dinero ----------

    with st.container(border=True):
        st.subheader("Distribución del dinero (sobre Ingreso)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("% gasto fijo", fmt_pct(kpis["pct_fijo"]))
        c2.metric("% gasto variable", fmt_pct(kpis["pct_variable"]))
        c3.metric("% inversión", fmt_pct(kpis["pct_inversion"]))
        c4.metric("% resto", fmt_pct(kpis["pct_resto"]))

    st.divider()

    # ---------- Gráfico 1: Evolución de Caja ----------

    with st.expander("📈 Evolución del saldo de Caja", expanded=True):
        # Selector de medias móviles. Default = 30d (suaviza el ciclo de salario)
        # y 90d (tendencia de fondo). Para ver tendencia más fina, sumar 14d.
        ventanas_disponibles = [7, 14, 30, 60, 90, 180]
        ventanas_sel = st.multiselect(
            "Medias móviles (días)",
            options=ventanas_disponibles,
            default=[30, 90],
            key="ma_ventanas",
            help="Ventanas para suavizar el saldo. Más largo = tendencia de fondo. "
                 "El 30d filtra el ciclo de salario mensual; el 90d muestra si tu "
                 "capital realmente crece o cae trimestre a trimestre.",
        )

        with connect(db_path) as conn:
            df_caja = caja_diaria_con_medias(
                conn, ventanas=tuple(ventanas_sel) if ventanas_sel else ()
            )

        if df_caja.empty:
            st.info("No hay datos para graficar todavía.")
        else:
            fig_caja = go.Figure()
            fig_caja.add_trace(go.Scatter(
                x=df_caja["fecha"], y=df_caja["caja"],
                mode="lines", name="Saldo diario",
                line=dict(color=COLOR_ACENTO, width=1.2),
                fill="tozeroy", fillcolor=COLOR_ACENTO_BG,
            ))
            for i, v in enumerate(ventanas_sel):
                col_name = f"caja_ma{v}"
                if col_name not in df_caja.columns:
                    continue
                fig_caja.add_trace(go.Scatter(
                    x=df_caja["fecha"], y=df_caja[col_name],
                    mode="lines", name=f"Media móvil {v}d",
                    line=dict(
                        color=COLORES_MA[i % len(COLORES_MA)],
                        width=2.2,
                        dash="dash" if v >= 60 else "solid",
                    ),
                ))
            fig_caja.update_layout(
                height=380,
                margin=dict(l=20, r=20, t=10, b=20),
                xaxis_title=None,
                yaxis_title="ARS",
                hovermode="x unified",
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(fig_caja, use_container_width=True)

    # ---------- Gráfico 2: Ingresos vs Gastos mensual ----------

    with st.expander("📊 Ingresos vs Gastos por mes", expanded=True):
        if df_iva_gtos.empty:
            st.info("No hay datos suficientes.")
        else:
            df_plot = df_iva_gtos.copy()
            df_plot["mes_label"] = df_plot["periodo"].dt.strftime("%b %Y")
            fig_bars = go.Figure()
            fig_bars.add_trace(go.Bar(
                x=df_plot["mes_label"], y=df_plot["ingresos"],
                name="Ingresos", marker_color=COLOR_INGRESO,
            ))
            fig_bars.add_trace(go.Bar(
                x=df_plot["mes_label"], y=df_plot["gastos"],
                name="Gastos", marker_color=COLOR_GASTO,
            ))
            fig_bars.update_layout(
                barmode="group", height=340,
                margin=dict(l=20, r=40, t=10, b=20),
                yaxis_title="ARS",
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_bars, use_container_width=True)

    # ---------- Gráfico 3: Distribución por categoría ----------

    with st.expander(f"🍩 Gasto por categoría ({anio_sel})", expanded=True):
        if df_cat.empty:
            st.info("Sin gastos registrados.")
        else:
            fig_pie = px.pie(
                df_cat,
                values="gasto", names="motivo",
                color="grupo",
                color_discrete_map=COLOR_POR_GRUPO,
                hole=0.5,
            )
            # En mobile las etiquetas "outside" se solapan. Las metemos
            # adentro de la rebanada y dejamos solo el % (el nombre va en la
            # leyenda). uniformtext oculta las rebanadas muy chicas.
            fig_pie.update_traces(
                textposition="inside",
                textinfo="percent",
                insidetextorientation="radial",
                hovertemplate="<b>%{label}</b><br>%{value:,.0f} ARS<br>%{percent}<extra></extra>",
            )
            fig_pie.update_layout(
                height=460,
                margin=dict(l=10, r=10, t=10, b=20),
                legend=dict(
                    orientation="h",
                    y=-0.05,
                    x=0.5,
                    xanchor="center",
                    font=dict(size=11),
                ),
                uniformtext_minsize=11,
                uniformtext_mode="hide",
            )
            st.plotly_chart(fig_pie, use_container_width=True)
