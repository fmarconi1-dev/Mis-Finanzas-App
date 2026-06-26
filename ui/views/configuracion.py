"""Vista Configuración: editor de categorías (grupo + subcategoría) + settings.

El editor usa `st.data_editor` inline: cambiás grupo o subcategoría por fila y
hacés clic en "Guardar cambios". Cada guardado dispara backup automático.

Sección adicional al final: motivos huérfanos (sin transacciones asociadas)
con botón para borrar.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from datetime import datetime

from core.categorias import (
    GRUPOS_EDITABLES,
    MOTIVOS_PROTEGIDOS,
    delete_categoria,
    insert_categoria,
    motivos_sin_uso,
    update_categoria,
)
from core.db import backup_db, connect, get_db_path, get_config, set_config
from core.export import export_xlsx
from core.metrics import load_categorias_full
from ui.helpers._format import fmt_ars, fmt_usd
from ui.helpers._tour import render_tour_panel


# Orden lógico para visualizar las categorías agrupadas.
_GRUPO_ORDER = {
    "Ingreso": 0,
    "Gasto Fijo": 1,
    "Gasto Variable": 2,
    "Inversion": 3,
    "Sin categorizar": 4,
    "Saldo Inicial": 5,
    "Flujo Capital": 6,
}


def _editor_categorias(db_path) -> None:
    """Renderiza la tabla editable de categorías y persiste cambios."""
    with connect(db_path) as conn:
        cats_full = load_categorias_full(conn)

    rows = [
        {
            "Motivo": m,
            "Grupo": g,
            "Subcategoría": s or "",
        }
        for m, (g, s) in cats_full.items()
        if m not in MOTIVOS_PROTEGIDOS and g != "Saldo Inicial"
    ]
    rows.sort(key=lambda r: (_GRUPO_ORDER.get(r["Grupo"], 99), r["Motivo"]))
    df_original = pd.DataFrame(rows)

    if df_original.empty:
        st.info(
            "Todavía no tenés categorías. Tenés dos formas de crearlas:\n\n"
            "1. **Desde acá**, con el form *Crear categoría nueva* (abajo).\n"
            "2. **Sobre la marcha** al cargar una transacción en la pestaña "
            "*Transacciones*: cuando elijas motivo, hacé clic en `➕ Nueva "
            "categoría...` y la categoría se crea automáticamente "
            "(grupo *Sin categorizar*, lista para que la asignes desde acá)."
        )
        return

    altura = min(700, 38 * (len(df_original) + 1))

    edited = st.data_editor(
        df_original,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        height=altura,
        column_config={
            "Motivo": st.column_config.TextColumn(
                "Motivo", disabled=True, width="medium",
                help="El nombre del motivo no se edita acá. Para renombrar, "
                     "borralo y creá uno nuevo desde Transacciones.",
            ),
            "Grupo": st.column_config.SelectboxColumn(
                "Grupo",
                options=list(GRUPOS_EDITABLES),
                required=True,
                width="medium",
            ),
            "Subcategoría": st.column_config.TextColumn(
                "Subcategoría",
                width="medium",
                help="Texto libre. Ej: Sueldo, Hogar, Ahorro y Resguardo, Desahorro.",
            ),
        },
        key="cat_editor",
    )

    # Detectar cambios contra el original cargado.
    cambios: list[tuple[str, str, str]] = []
    for i in range(len(df_original)):
        o = df_original.iloc[i]
        e = edited.iloc[i]
        if o["Grupo"] != e["Grupo"] or (o["Subcategoría"] or "") != (e["Subcategoría"] or ""):
            cambios.append((e["Motivo"], e["Grupo"], e["Subcategoría"] or ""))

    if cambios:
        c1, c2 = st.columns([1, 4])
        if c1.button(f"💾 Guardar {len(cambios)} cambio(s)", type="primary"):
            with connect(db_path) as conn:
                aplicados = []
                fallidos = []
                for motivo, grupo, subcat in cambios:
                    try:
                        update_categoria(conn, motivo, grupo, subcat or None)
                        aplicados.append(motivo)
                    except (LookupError, ValueError) as e:
                        fallidos.append((motivo, str(e)))
            if aplicados:
                st.toast(f"✅ Guardados: {', '.join(aplicados)}", icon="💾")
            for motivo, err in fallidos:
                st.error(f"{motivo}: {err}")
            st.rerun()
        c2.info(
            f"Tenés {len(cambios)} cambio(s) pendiente(s). "
            "Hacé clic en Guardar para persistir."
        )


def _alta_categoria(db_path) -> None:
    """Form chico para crear una categoría desde cero (sin pasar por una alta de transacción)."""
    with st.expander("Crear categoría nueva"):
        c1, c2, c3, c_btn = st.columns([2, 2, 2, 1])
        nuevo_motivo = c1.text_input("Motivo", key="nueva_cat_motivo",
                                      placeholder="Ej: Bonos, Regalos…")
        nuevo_grupo = c2.selectbox(
            "Grupo", list(GRUPOS_EDITABLES), key="nueva_cat_grupo",
        )
        nueva_sub = c3.text_input("Subcategoría (opcional)", key="nueva_cat_sub")

        if c_btn.button("Crear", type="primary", use_container_width=True):
            try:
                with connect(db_path) as conn:
                    insert_categoria(conn, nuevo_motivo, nuevo_grupo, nueva_sub or None)
                st.toast(f"✨ Categoría «{nuevo_motivo}» creada.", icon="✨")
                # Limpiar inputs reseteando session_state.
                for k in ("nueva_cat_motivo", "nueva_cat_sub"):
                    st.session_state.pop(k, None)
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def _borrar_sin_uso(db_path) -> None:
    """Lista de motivos huérfanos con botón de borrado por cada uno."""
    with connect(db_path) as conn:
        huerfanos = motivos_sin_uso(conn)

    if not huerfanos:
        st.caption("No hay motivos huérfanos (todos están en uso por al menos una transacción).")
        return

    st.caption(
        f"Estos {len(huerfanos)} motivo(s) están en la tabla pero ninguna "
        "transacción los usa. Podés borrarlos si no los vas a usar."
    )
    for motivo in huerfanos:
        c1, c2 = st.columns([4, 1])
        c1.write(f"• **{motivo}**")
        if c2.button("🗑 Borrar", key=f"del_{motivo}", use_container_width=True):
            try:
                with connect(db_path) as conn:
                    delete_categoria(conn, motivo)
                st.toast(f"🗑️ Categoría «{motivo}» borrada.", icon="🗑️")
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def render() -> None:
    render_tour_panel("configuracion")
    db_path = get_db_path()

    # ---------- Editor principal ----------

    st.subheader("Editor de categorías")
    st.caption(
        "Editá grupo y subcategoría por fila. Los cambios persisten al hacer "
        "clic en Guardar (con backup automático). El Dashboard y la pestaña "
        "Mensual se recalculan solos."
    )
    _editor_categorias(db_path)

    st.divider()

    # ---------- Crear nueva categoría ----------

    _alta_categoria(db_path)

    st.divider()

    # ---------- Borrar motivos sin uso ----------

    st.subheader("Motivos sin uso")
    _borrar_sin_uso(db_path)

    st.divider()

    # ---------- Categorías protegidas (read-only) ----------

    with connect(db_path) as conn:
        cats_full = load_categorias_full(conn)
        saldo_inicial_raw = get_config(conn, "saldo_inicial_caja", "0") or "0"
        fondo_usd_raw = get_config(conn, "fondo_emergencia_usd", "0") or "0"

    protegidas = [
        (m, g, s) for m, (g, s) in cats_full.items()
        if m in MOTIVOS_PROTEGIDOS or g == "Saldo Inicial"
    ]
    if protegidas:
        with st.expander("Categorías especiales (no editables)"):
            df_p = pd.DataFrame(
                [{"Motivo": m, "Grupo": g, "Subcategoría": s or "—"} for m, g, s in protegidas]
            )
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            st.caption(
                "‘Caja’ es la fila de saldo inicial que se importa del CSV. "
                "No se edita desde acá para preservar la lógica de Caja."
            )

    # ---------- Valores de configuración ----------

    st.subheader("Valores de configuración")
    c1, c2 = st.columns(2)

    with c1:
        st.metric("Saldo inicial de Caja (ARS)", fmt_ars(float(saldo_inicial_raw)))
        with st.expander("Editar saldo inicial"):
            nuevo_saldo = st.number_input(
                "Nuevo saldo inicial (ARS)",
                value=float(saldo_inicial_raw),
                step=1000.0,
                format="%.2f",
                key="saldo_inicial_input",
                help="Cambiarlo afecta TODA la serie histórica de Caja "
                     "(suma/resta el delta a cada saldo acumulado).",
            )
            if abs(nuevo_saldo - float(saldo_inicial_raw)) > 0.01:
                st.warning(
                    f"Vas a cambiar el saldo inicial de "
                    f"{fmt_ars(float(saldo_inicial_raw))} a {fmt_ars(nuevo_saldo)}. "
                    f"Esto afecta retroactivamente el saldo de Caja en TODAS las "
                    f"vistas."
                )
                if st.button("Confirmar cambio", type="primary", key="confirm_saldo"):
                    with connect(db_path) as conn:
                        set_config(conn, "saldo_inicial_caja", f"{nuevo_saldo:.2f}")
                    backup_db()
                    st.toast("💰 Saldo inicial actualizado.", icon="💰")
                    st.rerun()

    with c2:
        st.metric("Fondo de emergencia (USD)", fmt_usd(float(fondo_usd_raw)))
        st.caption("Editable desde el Dashboard.")

    st.divider()

    # ---------- Exportar a Excel ----------

    st.subheader("Exportar a Excel")
    st.caption(
        "Genera un .xlsx con tu snapshot completo (Diario, Mensual, "
        "Categorías y Resumen). Útil para backup manual, compartir con "
        "contador o comparar con tu Excel original."
    )
    with connect(db_path) as conn:
        xlsx_bytes = export_xlsx(conn)
    st.download_button(
        label="📥 Descargar snapshot Excel",
        data=xlsx_bytes,
        file_name=f"mis-finanzas-{datetime.now():%Y%m%d-%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
