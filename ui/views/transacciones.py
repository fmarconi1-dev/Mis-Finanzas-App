"""Vista Transacciones: alta rápida + edición + borrado.

Modo rápido (default en alta nueva): form mínimo (sólo Importe + Motivo).
Chips arriba con motivos frecuentes y montos recurrentes precargan el form
con un toque, así una carga típica se resuelve en 2 clics.

Modo detallado: form completo con Fecha, Tipo (Gasto/Ingreso) y Comentario.
Útil para casos no típicos (Ingreso manual, fecha pasada, motivo poco común,
comentario largo).

Edición: siempre en modo detallado (la edición pide todos los campos).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core.categorizer import efective_grupo
from core.db import connect
from core.metrics import load_categorias_full
from core.parsers import parse_expression
from core.transactions import (
    all_motivos,
    delete_transaction,
    get_transaction,
    insert_transaction,
    list_recent,
    montos_frecuentes_por_motivo,
    motivos_recientes,
    update_transaction,
)
from ui.helpers._format import fmt_ars
from ui.helpers._tour import render_tour_panel


_NUEVA_CAT = "➕ Nueva categoría..."


def _fmt_importe_for_input(value: float) -> str:
    """Float → string para precargar el text_input (formato argentino)."""
    if value is None or value == 0:
        return ""
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".replace(".", ",")


def _clear_form_state() -> None:
    """Limpia el estado del form para volver al estado inicial."""
    for k in (
        "form_motivo", "form_importe_text", "form_motivo_nuevo",
        "form_comentario", "form_fecha", "form_tipo",
        "editing_loaded_for",
    ):
        st.session_state.pop(k, None)


def _start_editing(txn_id: int) -> None:
    _clear_form_state()
    st.session_state.editing_id = int(txn_id)


def _cancel_editing() -> None:
    _clear_form_state()
    st.session_state.editing_id = None


def _load_editing_txn() -> dict | None:
    txn_id = st.session_state.get("editing_id")
    if not txn_id:
        return None
    with connect() as conn:
        return get_transaction(conn, int(txn_id))


def _render_chips_rapidos(motivos: list[str]) -> None:
    """Chips de motivos frecuentes + montos recurrentes para precargar el form."""
    with connect() as conn:
        recientes = motivos_recientes(conn, n=6, dias=60)

    if recientes:
        st.caption("**Motivos frecuentes** — tocá uno para precargarlo:")
        cols = st.columns(len(recientes))
        for i, mot in enumerate(recientes):
            if cols[i].button(mot, key=f"chip_mot_{i}", use_container_width=True):
                st.session_state["form_motivo"] = mot
                st.rerun()

    # Montos: si ya hay motivo elegido, filtra por él; sino, global.
    motivo_actual = st.session_state.get("form_motivo")
    if motivo_actual == _NUEVA_CAT:
        motivo_actual = None
    with connect() as conn:
        montos = montos_frecuentes_por_motivo(
            conn, motivo_actual, n=4, dias=90,
        )

    if montos:
        if motivo_actual:
            st.caption(
                f"**Montos frecuentes en «{motivo_actual}»** — tocá uno para precargar:"
            )
        else:
            st.caption("**Montos frecuentes** (global) — tocá uno para precargar:")
        cols = st.columns(len(montos))
        for i, m in enumerate(montos):
            if cols[i].button(fmt_ars(m), key=f"chip_mnt_{i}",
                              use_container_width=True):
                st.session_state["form_importe_text"] = _fmt_importe_for_input(m)
                st.rerun()


def _form_alta_edicion(motivos: list[str]) -> None:
    """Renderiza el form en modo rápido o detallado según session_state."""
    txn = _load_editing_txn()
    editing = txn is not None
    modo_rapido = st.session_state.get("modo_rapido", True) and not editing

    if editing:
        st.info(f"Editando transacción #{txn['id']} del {txn['fecha']}")
        if st.button("Cancelar edición", key="cancel_edit"):
            _cancel_editing()
            st.rerun()

    # Defaults para el form.
    if editing:
        fecha_default = date.fromisoformat(txn["fecha"])
        pasivos_default = float(txn["pasivos"])
        ingresos_default = float(txn["ingresos"])
        tipo_default = "Gasto" if pasivos_default > 0 else "Ingreso"
        importe_default = pasivos_default if tipo_default == "Gasto" else ingresos_default
        motivo_default = txn["motivo"]
        comentario_default = txn["comentario"] or ""
        # Pre-cargar session_state UNA vez al entrar en edición (sentinel
        # evita que se pise lo tipeado en cada rerun).
        if st.session_state.get("editing_loaded_for") != txn["id"]:
            st.session_state["form_motivo"] = motivo_default
            st.session_state["form_importe_text"] = _fmt_importe_for_input(importe_default)
            st.session_state["form_comentario"] = comentario_default
            st.session_state["editing_loaded_for"] = txn["id"]
    else:
        fecha_default = date.today()
        tipo_default = "Gasto"
        importe_default = 0.0
        motivo_default = st.session_state.get("form_motivo") or (
            motivos[0] if motivos else _NUEVA_CAT
        )
        comentario_default = ""

    opciones_motivo = motivos + [_NUEVA_CAT]
    try:
        motivo_idx = opciones_motivo.index(motivo_default)
    except ValueError:
        motivo_idx = 0

    with st.form("txn_form", clear_on_submit=not editing):
        if modo_rapido:
            # ----- MODO RÁPIDO: sólo Importe + Motivo -----
            c1, c2 = st.columns([1, 1])
            importe_str = c1.text_input(
                "Importe (ARS)",
                key="form_importe_text",
                placeholder="Ej: 5000  o  10000 + 5000 - 200",
                help="Aceptamos expresiones: + − × ÷ ( ). "
                     "Formato argentino: '.' miles, ',' decimales.",
            )
            motivo_sel = c2.selectbox(
                "Motivo", opciones_motivo, index=motivo_idx, key="form_motivo",
            )
            motivo_nuevo = ""
            if motivo_sel == _NUEVA_CAT:
                motivo_nuevo = st.text_input(
                    "Nombre de la nueva categoría",
                    value="", key="form_motivo_nuevo",
                    placeholder="Ej: Suscripciones, Regalos…",
                )
            # Valores fijos del modo rápido.
            fecha_val = date.today()
            tipo_val = "Gasto"
            comentario_val = ""
            btn_label = "💸 Agregar gasto"
        else:
            # ----- MODO DETALLADO: form completo -----
            c1, c2 = st.columns(2)
            fecha_val = c1.date_input(
                "Fecha", value=fecha_default, format="DD/MM/YYYY",
                key="form_fecha",
            )
            tipo_val = c2.radio(
                "Tipo", ["Gasto", "Ingreso"], horizontal=True,
                index=0 if tipo_default == "Gasto" else 1, key="form_tipo",
            )
            c1, c2 = st.columns(2)
            importe_str = c1.text_input(
                "Importe (ARS)",
                key="form_importe_text",
                placeholder="Ej: 5000  o  10000 + 5000 - 200",
                help="Aceptamos expresiones: + − × ÷ ( ).",
            )
            motivo_sel = c2.selectbox(
                "Motivo", opciones_motivo, index=motivo_idx, key="form_motivo",
            )
            motivo_nuevo = ""
            if motivo_sel == _NUEVA_CAT:
                motivo_nuevo = st.text_input(
                    "Nombre de la nueva categoría",
                    value="", key="form_motivo_nuevo",
                    placeholder="Ej: Suscripciones, Regalos…",
                )
            comentario_val = st.text_input(
                "Comentario (opcional)",
                value=comentario_default if not st.session_state.get("form_comentario") else st.session_state.get("form_comentario"),
                key="form_comentario",
            )
            btn_label = "Actualizar transacción" if editing else "Agregar transacción"

        submitted = st.form_submit_button(
            btn_label, type="primary", use_container_width=True,
        )

    if not submitted:
        return

    # Validación.
    motivo_final = motivo_nuevo.strip() if motivo_sel == _NUEVA_CAT else motivo_sel
    if not motivo_final:
        st.error("Seleccioná un motivo o escribí una categoría nueva.")
        return

    try:
        importe_val = parse_expression(importe_str)
    except ValueError as e:
        st.error(f"Importe inválido: {e}. Usá números o expresiones tipo '10000 + 500'.")
        return
    if importe_val <= 0:
        st.error(
            f"El cálculo da {fmt_ars(importe_val)}. El importe debe ser positivo — "
            "si querés registrar una devolución, usá 'Tipo = Ingreso' (modo detallado)."
        )
        return

    pasivos = importe_val if tipo_val == "Gasto" else 0.0
    ingresos = importe_val if tipo_val == "Ingreso" else 0.0
    expr_evaluada = ""
    if importe_str.strip() != _fmt_importe_for_input(importe_val):
        expr_evaluada = f" (calculado de `{importe_str.strip()}`)"

    with connect() as conn:
        if editing:
            update_transaction(
                conn, int(txn["id"]), fecha_val, motivo_final,
                pasivos=pasivos, ingresos=ingresos,
                comentario=comentario_val or None,
            )
            msg = f"✏️ Transacción #{txn['id']} actualizada: {fmt_ars(importe_val)}{expr_evaluada}"
        else:
            new_id = insert_transaction(
                conn, fecha_val, motivo_final,
                pasivos=pasivos, ingresos=ingresos,
                comentario=comentario_val or None,
            )
            msg = (f"✅ {tipo_val} de {fmt_ars(importe_val)} en «{motivo_final}»"
                   f"{expr_evaluada}")
            if motivo_sel == _NUEVA_CAT:
                msg += " · categoría nueva (asignale grupo en Configuración)"

    _clear_form_state()
    st.session_state.editing_id = None
    st.toast(msg, icon="💸")
    st.rerun()


def _tabla_recientes() -> None:
    with connect() as conn:
        recent = list_recent(conn, n=20)
        cats_full = load_categorias_full(conn)

    if not recent:
        st.info("No hay transacciones todavía. Agregá la primera arriba ↑")
        return

    df = pd.DataFrame(recent)

    # Enriquecer con grupo + subcategoría aplicando la regla dual fila a fila
    # (misma lógica que usa el libro Diario y el Dashboard).
    grupos, subs = [], []
    for _, row in df.iterrows():
        g, s = efective_grupo(
            row["motivo"], float(row["pasivos"]), float(row["ingresos"]), cats_full,
        )
        grupos.append(g)
        subs.append(s or "—")
    df["grupo"] = grupos
    df["subcategoria"] = subs

    df_disp = pd.DataFrame({
        "Fecha": pd.to_datetime(df["fecha"]).dt.strftime("%d/%m/%Y"),
        "Motivo": df["motivo"],
        "Subcategoría": df["subcategoria"],
        "Importe": [
            fmt_ars(r["ingresos"] if r["ingresos"] > 0 else -r["pasivos"])
            for _, r in df.iterrows()
        ],
        "Comentario": df["comentario"].fillna(""),
    })

    event = st.dataframe(
        df_disp, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="recent_table",
    )

    selected = event.selection.rows if hasattr(event, "selection") else []
    if not selected:
        st.caption("Seleccioná una fila para editarla o borrarla.")
        return

    sel_idx = selected[0]
    sel_id = int(df.iloc[sel_idx]["id"])
    sel_label = f"#{sel_id} · {df_disp.iloc[sel_idx]['Fecha']} · {df_disp.iloc[sel_idx]['Motivo']}"

    c1, c2 = st.columns(2)
    if c1.button(f"✏️ Editar {sel_label}", type="primary",
                 use_container_width=True, key="btn_edit"):
        _start_editing(sel_id)
        st.rerun()

    confirmar_key = f"confirm_delete_{sel_id}"
    if c2.button(f"🗑️ Borrar {sel_label}", type="secondary",
                 use_container_width=True, key="btn_delete"):
        st.session_state[confirmar_key] = True

    if st.session_state.get(confirmar_key):
        st.warning(f"¿Borrar definitivamente {sel_label}? Se hace backup antes.")
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button("Sí, borrar", type="primary", key="confirm_yes"):
            with connect() as conn:
                delete_transaction(conn, sel_id)
            st.session_state.pop(confirmar_key, None)
            st.toast(f"🗑️ Transacción {sel_label} borrada.", icon="🗑️")
            st.rerun()
        if c2.button("Cancelar", key="confirm_no"):
            st.session_state.pop(confirmar_key, None)
            st.rerun()


def render() -> None:
    render_tour_panel("transacciones")
    # Estado por defecto.
    if "editing_id" not in st.session_state:
        st.session_state.editing_id = None
    if "modo_rapido" not in st.session_state:
        st.session_state.modo_rapido = True

    with connect() as conn:
        motivos = all_motivos(conn)

    editing = st.session_state.editing_id is not None

    # Header con título y toggle Modo rápido (sólo en alta).
    c_title, c_toggle = st.columns([3, 1])
    c_title.subheader("Editar transacción" if editing else "Nueva transacción")
    if not editing:
        c_toggle.toggle(
            "⚡ Modo rápido",
            key="modo_rapido",
            help="Form minimalista: sólo Importe + Motivo (asume Gasto / hoy / "
                 "sin comentario). Apagalo para ver el form completo.",
        )

    # Chips de motivos + montos frecuentes (sólo en alta).
    if not editing:
        _render_chips_rapidos(motivos)

    _form_alta_edicion(motivos)

    st.divider()
    st.subheader("Últimos movimientos")
    _tabla_recientes()
