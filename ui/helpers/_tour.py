"""Tour guiado para usuarios nuevos.

Se activa al completar el onboarding y guía paso a paso por las 5 pestañas.
Se persiste en la tabla `configuracion` con la clave `tutorial_completado`.

Estados de `tutorial_completado` por usuario:
- None / no existe → usuario pre-tutorial (ej. Franco, que ya conocía la app).
  El tour NO se muestra.
- "0" → tour activo, se muestran los paneles.
- "1" → tour terminado (o saltado por el usuario). No se vuelve a mostrar.

session_state.tour_step (int) → posición actual:
0 = Dashboard, 1 = Transacciones, 2 = Diario, 3 = Mensual, 4 = Configuración.

Cada vista llama a `render_tour_panel(tab_name)` al inicio de su `render()`.
Si el tour está activo Y la pestaña es la del paso actual, se muestra el panel.
"""

from __future__ import annotations

import streamlit as st

from core.db import connect, get_config, set_config


_TOUR_KEY = "tutorial_completado"

# Mapping orden ↔ nombre canónico de pestaña.
_TABS_ORDER = ["dashboard", "transacciones", "diario", "mensual", "configuracion"]


# ---------- Estado ----------

def _user_id() -> int | None:
    return st.session_state.get("current_user_id")


def is_tour_active() -> bool:
    """¿El usuario actual está en medio del tour?"""
    uid = _user_id()
    if uid is None:
        return False
    with connect() as conn:
        val = get_config(conn, _TOUR_KEY, default=None, user_id=uid)
    return val == "0"


def start_tour() -> None:
    """Marca el tour como activo. Se llama al completar el onboarding."""
    uid = _user_id()
    if uid is None:
        return
    with connect() as conn:
        set_config(conn, _TOUR_KEY, "0", user_id=uid)
    st.session_state["tour_step"] = 0


def finish_tour(skipped: bool = False) -> None:
    """Marca el tour como completado (o saltado). No vuelve a mostrarse."""
    uid = _user_id()
    if uid is None:
        return
    with connect() as conn:
        set_config(conn, _TOUR_KEY, "1", user_id=uid)
    st.session_state.pop("tour_step", None)
    if not skipped:
        st.toast(
            "🎉 ¡Listo! Ya conocés tu app. Cargá tu primera transacción para empezar.",
            icon="🎉",
        )


def _current_step() -> int:
    return int(st.session_state.get("tour_step", 0))


def _advance() -> None:
    st.session_state["tour_step"] = _current_step() + 1


# ---------- Contenido de los paneles ----------

_PANELS = {
    "dashboard": {
        "titulo": "👀 Paso 1 de 5 · Dashboard",
        "body": (
            "Acá ves tus **KPIs en vivo**: Saldo de cuenta corriente, ingreso/gasto "
            "anual y mensual, y la distribución entre **fijos**, **variables**, "
            "**inversión** y **resto**. Los gráficos te muestran cómo evoluciona "
            "tu caja con medias móviles para ver la tendencia más allá del "
            "ruido del ciclo mensual. También editás el **Fondo de Emergencia "
            "(USD)** desde acá."
        ),
        "hint": "Próxima parada: pestaña **➕ Transacciones**.",
    },
    "transacciones": {
        "titulo": "💸 Paso 2 de 5 · Transacciones",
        "body": (
            "Tu lugar para **cargar gastos e ingresos**. Activá el **⚡ Modo "
            "rápido** (arriba a la derecha, ya viene encendido por default) "
            "para una carga ultra rápida: tocás un chip de motivo frecuente, "
            "un chip de monto recurrente, y listo en 2 toques. "
            "El campo Importe también acepta expresiones tipo "
            "`5000 + 3200 - 200` por si tenés que sumar varios ítems en una "
            "sola transacción."
        ),
        "hint": "Próxima parada: pestaña **📒 Diario**.",
    },
    "diario": {
        "titulo": "📒 Paso 3 de 5 · Diario",
        "body": (
            "Una vista cronológica de tus **últimos N días**, fila por fila, "
            "sin agregaciones. Útil para chequear que cargaste todo en una "
            "semana o detectar duplicados a primera vista. Cambiá la cantidad "
            "de días con el selector arriba a la derecha."
        ),
        "hint": "Próxima parada: pestaña **🎯 Mensual**.",
    },
    "mensual": {
        "titulo": "🎯 Paso 4 de 5 · Mensual",
        "body": (
            "Comparativa **Previsión vs Realidad** por categoría, para el mes "
            "que elijas. Las barras de **Consumido** te avisan visualmente "
            "cuánto del presupuesto te llevaste de cada motivo (>100% = te "
            "pasaste). Al final del todo, expandí **✏️ Editar previsiones** "
            "para modificar tus presupuestos del mes o copiarlos al año entero "
            "de un toque."
        ),
        "hint": "Última parada: pestaña **⚙️ Configuración**.",
    },
    "configuracion": {
        "titulo": "⚙️ Paso 5 de 5 · Configuración",
        "body": (
            "Acá manejás tus **categorías** (Motivo → Grupo → Subcategoría), "
            "creás nuevas, borrás las que no usés, editás el **saldo inicial "
            "de Caja**, y **exportás un snapshot en Excel** cuando quieras "
            "tener una copia o compartir con un contador."
        ),
        "hint": None,  # último paso
    },
}


# ---------- Render ----------

def render_tour_panel(tab_name: str) -> None:
    """Llamar al inicio del `render()` de cada vista.

    Si el tour está activo Y estamos en la pestaña del paso actual, muestra el
    panel con explicación + botones. Sino, no-op.
    """
    if not is_tour_active():
        return
    if tab_name not in _PANELS:
        return

    current_idx = _current_step()
    if current_idx >= len(_TABS_ORDER):
        # Pasamos por todas, cerrar.
        finish_tour()
        return

    tab_esperada = _TABS_ORDER[current_idx]
    if tab_name != tab_esperada:
        return

    panel = _PANELS[tab_name]
    es_ultimo = panel["hint"] is None

    with st.container(border=True):
        st.markdown(f"### {panel['titulo']}")
        st.markdown(panel["body"])
        if panel["hint"]:
            st.caption(panel["hint"])

        c1, c2, _ = st.columns([1, 1, 3])
        if es_ultimo:
            if c1.button("🎉 Terminé el tour", type="primary",
                         key=f"tour_finish_{tab_name}",
                         width="stretch"):
                finish_tour()
                st.rerun()
            if c2.button("Saltar", key=f"tour_skip_{tab_name}",
                         width="stretch"):
                finish_tour(skipped=True)
                st.rerun()
        else:
            if c1.button("Listo, siguiente →", type="primary",
                         key=f"tour_next_{tab_name}",
                         width="stretch"):
                _advance()
                st.toast(f"✅ {panel['hint'].replace('**', '')}", icon="👉")
                st.rerun()
            if c2.button("Saltar tutorial", key=f"tour_skip_{tab_name}",
                         width="stretch"):
                finish_tour(skipped=True)
                st.rerun()
