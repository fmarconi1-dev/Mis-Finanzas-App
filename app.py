"""Entry point Streamlit.

Levantar localmente:
    streamlit run app.py

Flow:
  1. init_db + migraciones (idempotente).
  2. Sin sesión → login.
  3. Con sesión → setear current_user_id en contextvar.
  4. Sin categorías para este usuario → onboarding.
  5. Resto del tiempo → tabs.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core.auth import get_user_by_id
from core.current_user import set_current_user_id
from core.db import connect, get_config, init_db
from core.session_tokens import QUERY_PARAM, verify_token
from ui.auth import login
from ui.views import configuracion, dashboard, diario, mensual, onboarding, transacciones
from ui.helpers._responsive import apply_responsive_css
from ui.helpers._styles import apply_design_system_css


st.set_page_config(
    page_title="Radar Financiero",
    page_icon="🎯",  # emoji en vez de assets/logo.svg para evitar el
                     # TypeError "'text/html' is not a valid JavaScript MIME type"
                     # que aparecía cuando Streamlit servía el SVG con MIME
                     # incorrecto en producción.
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS responsive (apila columnas en mobile, mejora touch targets, etc.).
apply_responsive_css()
# Design system: pulido de métricas, botones primarios, containers, etc.
apply_design_system_css()
# Nota: ya no llamamos a try_set_logo(): st.logo() con SVG estaba causando
# el TypeError de MIME en producción. El logo igual aparece embebido como
# SVG inline en login y onboarding vía inline_logo().


def _user_completo_onboarding(user_id: int) -> bool:
    """¿El usuario ya completó la pantalla de bienvenida?

    Para usuarios pre-existentes (ej. Franco, que ya tenía datos antes de
    R2), si tienen categorías ya cargadas se considera onboarding completo.
    Para usuarios nuevos post-R2, miramos el flag explícito en configuracion.
    """
    with connect() as conn:
        flag = get_config(conn, "onboarding_completado", "0", user_id=user_id)
        if flag == "1":
            return True
        # Fallback para usuarios pre-R2 con categorías ya cargadas.
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM categorias WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["n"] > 0


def _try_restore_session_from_token() -> None:
    """Si hay un token de sesión válido en la URL, restaura la sesión.

    Cualquier token inválido/expirado se ignora y se limpia de la URL
    (el usuario simplemente ve el login).
    """
    token = st.query_params.get(QUERY_PARAM)
    if not token:
        return
    uid = verify_token(token)
    if uid is None:
        del st.query_params[QUERY_PARAM]
        return
    with connect() as conn:
        user = get_user_by_id(conn, uid)
    if user is None:
        del st.query_params[QUERY_PARAM]
        return
    st.session_state["logged_in"] = True
    st.session_state["current_user_id"] = user["id"]
    st.session_state["current_username"] = user["username"]
    st.session_state["current_user_fullname"] = user["fullname"]


def main() -> None:
    init_db()

    # Restaurar sesión desde token firmado en la URL (si SESSION_SECRET está
    # configurado). Evita el re-login en cada refresh (premortem #3, F2/R9).
    if not st.session_state.get("logged_in"):
        _try_restore_session_from_token()

    # Auth gate.
    if not st.session_state.get("logged_in"):
        login.render()
        return

    user_id = st.session_state["current_user_id"]
    set_current_user_id(user_id)
    login.render_logout_button()

    # Onboarding: si todavía no hay categorías para este usuario.
    if not _user_completo_onboarding(user_id):
        onboarding.render(
            user_id=user_id,
            fullname=st.session_state.get("current_user_fullname") or "",
        )
        return

    # App principal.
    st.title("💰 Radar Financiero")

    tab_dash, tab_txn, tab_diario, tab_mensual, tab_cfg = st.tabs(
        ["📊 Dashboard", "➕ Transacciones", "📒 Diario", "🎯 Mensual", "⚙️ Configuración"]
    )

    with tab_dash:
        dashboard.render()
    with tab_txn:
        transacciones.render()
    with tab_diario:
        diario.render()
    with tab_mensual:
        mensual.render()
    with tab_cfg:
        configuracion.render()


if __name__ == "__main__":
    main()
