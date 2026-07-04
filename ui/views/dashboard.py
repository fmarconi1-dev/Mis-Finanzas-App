"""Vista Dashboard: KPIs + gráficos + editor inline de Fondo USD."""

from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

import pandas as pd

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
from ui.helpers._format import fmt_ars, fmt_ars_corto, fmt_usd
from ui.helpers._html import render_html
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

    # ---------- Período (deploy estética 2) ----------
    #
    # El modelo mental de finanzas personales es mensual: "¿cómo vengo este
    # mes?". "Este mes" y "Últimos 3 meses" se anclan en la fecha de HOY;
    # "Año" mantiene el selector de siempre (fix premortem #3). Si el mes en
    # curso no tiene movimientos, el empty state lo explica (no ceros mudos).

    meses_es = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo",
        6: "junio", 7: "julio", 8: "agosto", 9: "septiembre",
        10: "octubre", 11: "noviembre", 12: "diciembre",
    }

    anios = anios_con_datos(df)
    anio_sel = anios[-1]
    c_per, c_anio = st.columns([3, 1])
    with c_per:
        periodo_sel = st.segmented_control(
            "Período",
            options=["Este mes", "Últimos 3 meses", "Año"],
            default="Este mes",
            key="dash_periodo",
            label_visibility="collapsed",
            help="Los KPIs, la distribución y el gasto por categoría se "
                 "calculan sobre este período. La evolución de Caja siempre "
                 "muestra la serie completa.",
        )
    if not periodo_sel:
        periodo_sel = "Este mes"  # segmented_control permite deseleccionar

    hoy = pd.Timestamp.today().normalize()
    if periodo_sel == "Este mes":
        ini, fin = hoy.replace(day=1), hoy
        prev_ini = ini - pd.offsets.MonthBegin(1)
        # Mismo tramo del mes anterior (día 1 al N): comparar mes parcial
        # contra mes completo inflaría el delta.
        prev_fin = min(prev_ini + (fin - ini), ini - pd.Timedelta(days=1))
        periodo_label = f"{meses_es[ini.month]} {ini.year}"
        prev_label = f"{meses_es[prev_ini.month]} (mismo tramo)"
    elif periodo_sel == "Últimos 3 meses":
        ini, fin = hoy - pd.offsets.MonthBegin(3), hoy
        prev_ini = ini - pd.offsets.MonthBegin(3)
        prev_fin = ini - pd.Timedelta(days=1)
        periodo_label = "los últimos 3 meses"
        prev_label = "los 3 meses previos"
    else:
        if len(anios) > 1:
            with c_anio:
                anio_sel = st.selectbox(
                    "Año", anios, index=len(anios) - 1, key="dash_anio",
                    label_visibility="collapsed",
                )
        ini, fin = pd.Timestamp(anio_sel, 1, 1), pd.Timestamp(anio_sel, 12, 31)
        prev_ini = pd.Timestamp(anio_sel - 1, 1, 1)
        prev_fin = pd.Timestamp(anio_sel - 1, 12, 31)
        periodo_label = str(anio_sel)
        prev_label = str(anio_sel - 1)

    df_periodo = df[(df["fecha"] >= ini) & (df["fecha"] <= fin)]
    df_prev = df[(df["fecha"] >= prev_ini) & (df["fecha"] <= prev_fin)]
    df_anio = filtrar_anio(df, anio_sel)

    kpis = compute_kpis(df_periodo, cats, fondo_usd=fondo, saldo_cc=saldo)
    kpis_prev = compute_kpis(df_prev, cats, fondo_usd=fondo, saldo_cc=saldo)
    hay_prev = not df_prev.empty
    sin_movs = df_periodo.empty
    df_iva_gtos = ingresos_vs_gastos_mensual(df_anio, cats)
    df_cat = gasto_por_categoria(df_periodo, cats)

    def _delta_pct(actual: float, previo: float) -> str | None:
        """Delta % contra el período anterior; None sin base de comparación."""
        if not hay_prev or previo == 0:
            return None
        return f"{(actual - previo) / previo * 100:+.1f}% vs {prev_label}"

    # ---------- Ancla de confianza ----------

    ultima = df["fecha"].max()
    st.caption(
        f"Última transacción cargada: **{ultima.strftime('%d/%m/%Y')}** "
        f"· **{len(df_periodo)}** movimientos en {periodo_label}"
    )

    # ---------- Hero: resultado del período + liquidez ----------

    with st.container(key="kpi_hero", border=True):
        resultado = kpis["ingreso_anual"] - kpis["gasto_anual"]
        res_prev = kpis_prev["ingreso_anual"] - kpis_prev["gasto_anual"]
        if hay_prev:
            diff = resultado - res_prev
            signo = "+" if diff >= 0 else ""
            delta_res = f"{signo}{fmt_ars_corto(diff)} vs {prev_label}"
        else:
            delta_res = None
        c1, c2, c3 = st.columns([1.5, 1, 1])
        c1.metric(
            f"Resultado — {periodo_label}",
            fmt_ars_corto(resultado),
            delta=delta_res,
            help=f"Ingreso − gasto de consumo (no descuenta inversión). "
                 f"Exacto: {fmt_ars(resultado)}.",
        )
        c2.metric(
            "Saldo cuenta corriente (ARS)", fmt_ars(kpis["saldo_cc"]),
            help="Caja acumulada total — no depende del período elegido.",
        )
        with c3:
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

    if sin_movs:
        st.info(
            f"Sin movimientos en {periodo_label}. Probá otro período — "
            f"la última transacción cargada es del {ultima.strftime('%d/%m/%Y')}."
        )

    # ---------- KPIs del período (con delta vs período anterior) ----------

    if not sin_movs:
        with st.container(border=True):
            st.subheader(f"KPIs — {periodo_label}")
            c1, c2, c3, c4 = st.columns(4)
            # Números cortos en las cards y el exacto en el help al hover.
            # delta_color="inverse" en gastos: subir es malo (rojo).
            c1.metric("Ingreso", fmt_ars_corto(kpis["ingreso_anual"]),
                      delta=_delta_pct(kpis["ingreso_anual"],
                                       kpis_prev["ingreso_anual"]),
                      help=f"Exacto: {fmt_ars(kpis['ingreso_anual'])}.")
            c2.metric("Gasto (consumo)", fmt_ars_corto(kpis["gasto_anual"]),
                      delta=_delta_pct(kpis["gasto_anual"],
                                       kpis_prev["gasto_anual"]),
                      delta_color="inverse",
                      help=f"Fijo + Variable, sin contar inversión. "
                           f"Exacto: {fmt_ars(kpis['gasto_anual'])}.")
            c3.metric("Gasto fijo", fmt_ars_corto(kpis["fijo_anual"]),
                      delta=_delta_pct(kpis["fijo_anual"],
                                       kpis_prev["fijo_anual"]),
                      delta_color="inverse",
                      help=f"Exacto: {fmt_ars(kpis['fijo_anual'])}.")
            c4.metric("Gasto variable", fmt_ars_corto(kpis["variable_anual"]),
                      delta=_delta_pct(kpis["variable_anual"],
                                       kpis_prev["variable_anual"]),
                      delta_color="inverse",
                      help=f"Compras, Salidas, Viajes, Transportes. "
                           f"Exacto: {fmt_ars(kpis['variable_anual'])}.")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Inversión / Ahorro", fmt_ars_corto(kpis["inversion_anual"]),
                      delta=_delta_pct(kpis["inversion_anual"],
                                       kpis_prev["inversion_anual"]),
                      help=f"Inversiones + Compra Divisa. "
                           f"Exacto: {fmt_ars(kpis['inversion_anual'])}.")
            c2.metric("Desahorro", fmt_ars_corto(kpis["desahorro_anual"]),
                      delta=_delta_pct(kpis["desahorro_anual"],
                                       kpis_prev["desahorro_anual"]),
                      delta_color="inverse",
                      help=f"Venta de divisa / liquidación de inversiones. "
                           f"Exacto: {fmt_ars(kpis['desahorro_anual'])}.")
            if kpis["meses_cubiertos"] > 1:
                c3.metric("Prom. ingreso/mes", fmt_ars_corto(kpis["ingreso_mes"]),
                          help=f"Exacto: {fmt_ars(kpis['ingreso_mes'])}/mes "
                               f"en {kpis['meses_cubiertos']} meses.")
                c4.metric("Prom. gasto/mes", fmt_ars_corto(kpis["gasto_mes"]),
                          help=f"Exacto: {fmt_ars(kpis['gasto_mes'])}/mes.")

        # ---------- Distribución del ingreso: barra apilada ----------
        # Una proporción se lee mejor como barra que como 4 números sueltos.

        if kpis["ingreso_anual"] > 0:
            with st.container(border=True):
                st.subheader(f"Distribución del ingreso — {periodo_label}")
                pf = kpis["pct_fijo"] * 100
                pv = kpis["pct_variable"] * 100
                pinv = kpis["pct_inversion"] * 100
                pr = kpis["pct_resto"] * 100
                # Si fijo+variable+inversión supera el ingreso (resto < 0),
                # la barra se escala a ese total y el resto pasa a alerta.
                escala = max(pf + pv + pinv + max(pr, 0), 100.0)
                segmentos = [
                    ("Fijo", pf, "#FB923C"),
                    ("Variable", pv, "#F43F5E"),
                    ("Inversión / Ahorro", pinv, "#10B981"),
                ]
                if pr > 0:
                    segmentos.append(("Resto", pr, "#3F3F46"))
                barra = "".join(
                    f'<div style="width:{max(p, 0) / escala * 100:.2f}%;'
                    f'background:{color};" title="{nombre}: {p:.1f}%"></div>'
                    for nombre, p, color in segmentos
                )
                chips = "".join(
                    f'<span style="color:var(--cs-text-mid);font-size:0.8rem;'
                    f'margin-right:1rem;white-space:nowrap;">'
                    f'<span style="display:inline-block;width:9px;height:9px;'
                    f'border-radius:2px;background:{color};'
                    f'margin-right:5px;"></span>'
                    f'{nombre} <span class="cs-mono">{p:.1f}%</span></span>'
                    for nombre, p, color in segmentos
                )
                alerta = ""
                if pr < 0:
                    alerta = (
                        f'<div style="color:var(--cs-negative);'
                        f'font-size:0.8rem;margin-top:0.4rem;">'
                        f'▼ Resto {pr:+.1f}% — en {periodo_label} salió más '
                        f'de lo que entró.</div>'
                    )
                render_html(
                    f'<div style="display:flex;height:14px;border-radius:7px;'
                    f'overflow:hidden;background:#121214;'
                    f'margin:0.2rem 0 0.6rem;">{barra}</div>'
                    f'<div>{chips}</div>{alerta}'
                )

    st.divider()

    # ---------- Gráfico 1: Evolución de Caja ----------

    with st.container(border=True):
        # El gráfico principal SIEMPRE visible (antes vivía en un expander:
        # jerarquía invertida). Ajustes avanzados en popover — progressive
        # disclosure: default 30d + 90d ya elegido, tocar solo si hace falta.
        c_tit, c_cfg = st.columns([5, 1])
        c_tit.subheader("Evolución del saldo de Caja")
        with c_cfg.popover("Ajustes", width="stretch"):
            ventanas_sel = st.multiselect(
                "Medias móviles (días)",
                options=[7, 14, 30, 60, 90, 180],
                default=[30, 90],
                key="ma_ventanas",
                help="Ventanas para suavizar el saldo. Más largo = tendencia "
                     "de fondo. El 30d filtra el ciclo de salario mensual; el "
                     "90d muestra la tendencia trimestral.",
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
            st.plotly_chart(fig_caja, width="stretch")

    # ---------- Gráfico 2: Ingresos vs Gastos mensual ----------

    with st.container(border=True):
        st.subheader(f"Ingresos vs Gastos por mes — {anio_sel}")
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
            st.plotly_chart(fig_bars, width="stretch")

    # ---------- Gráfico 3: Distribución por categoría ----------

    with st.container(border=True):
        st.subheader(f"Gasto por categoría — {periodo_label}")
        if df_cat.empty:
            st.info("Sin gastos registrados.")
        else:
            # Toggle: agrupar por motivo (detalle fino) o por subcategoría
            # (agregado más legible). Mapeo motivo → subcategoría desde
            # cats_full y reagrupo si el usuario elige subcategoría.
            agrupar_por = st.segmented_control(
                "Agrupar por",
                options=["Motivo", "Subcategoría"],
                default="Motivo",
                key="donut_agrupar_por",
                label_visibility="collapsed",
            ) or "Motivo"

            if agrupar_por == "Subcategoría":
                # mapping motivo → (grupo, subcat) ya está en `cats`
                df_pie = df_cat.copy()
                df_pie["subcategoria"] = df_pie["motivo"].map(
                    lambda m: (cats.get(m, ("", None))[1]) or "Sin subcategoría"
                )
                # reagrupar por grupo + subcategoría
                df_pie = (
                    df_pie.groupby(["subcategoria", "grupo"], as_index=False)["gasto"]
                    .sum()
                    .sort_values("gasto", ascending=False)
                )
                names_col = "subcategoria"
            else:
                df_pie = df_cat
                names_col = "motivo"

            fig_pie = px.pie(
                df_pie,
                values="gasto", names=names_col,
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
            st.plotly_chart(fig_pie, width="stretch")
