"""Pantalla de login + signup.

Premortem #3 (F4/R5): el signup ya no es público. Se habilita SOLO si la
variable de entorno SIGNUP_CODE está definida, y el usuario nuevo tiene que
escribir ese código de invitación. Sin SIGNUP_CODE → solo login.
El login tiene rate-limit en memoria (5 fallos en 15 min → 5 min de bloqueo).

Premortem #3 (F2/R9): si SESSION_SECRET está definido, el login exitoso emite
un token firmado en la URL para que un refresh no obligue a re-loguear.
"""

from __future__ import annotations

import os

import streamlit as st

from core.auth import (
    authenticate,
    clear_failed_logins,
    create_user,
    register_failed_login,
    seconds_until_unlock,
)
from core.db import connect
from core.session_tokens import QUERY_PARAM, issue_token, tokens_enabled
from ui.helpers._html import render_html
from ui.helpers._logo import render_logo


def signup_habilitado() -> bool:
    return bool(os.environ.get("SIGNUP_CODE"))


def _set_session(user_id: int, username: str, fullname: str | None) -> None:
    st.session_state["logged_in"] = True
    st.session_state["current_user_id"] = user_id
    st.session_state["current_username"] = username
    st.session_state["current_user_fullname"] = fullname
    if tokens_enabled():
        token = issue_token(user_id)
        if token:
            st.query_params[QUERY_PARAM] = token


def _render_login_form() -> None:
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input(
            "Usuario", autocomplete="username", key="login_username"
        )
        password = st.text_input(
            "Contraseña", type="password", autocomplete="current-password",
            key="login_password",
        )
        submitted = st.form_submit_button(
            "Entrar", type="primary", width="stretch",
        )

    if submitted:
        if not username or not password:
            st.error("Completá usuario y contraseña.")
            return
        username = username.strip()

        # Rate limit: si el usuario acumuló demasiados fallos, ni intentamos.
        espera = seconds_until_unlock(username)
        if espera > 0:
            st.error(
                f"Demasiados intentos fallidos. Probá de nuevo en "
                f"{max(1, espera // 60)} minuto(s)."
            )
            return

        with connect() as conn:
            user = authenticate(conn, username, password)
        if not user:
            register_failed_login(username)
            st.error("Usuario o contraseña incorrectos.")
            return
        clear_failed_logins(username)
        _set_session(user["id"], user["username"], user["fullname"])
        st.rerun()


def _render_signup_form() -> None:
    with st.form("signup_form", clear_on_submit=False):
        fullname = st.text_input("Nombre y apellido", key="signup_fullname")
        username = st.text_input(
            "Elegí un usuario", autocomplete="username", key="signup_username",
            help="Sin espacios. Lo vas a usar para iniciar sesión.",
        )
        password = st.text_input(
            "Contraseña (mínimo 6 caracteres)", type="password",
            autocomplete="new-password", key="signup_password",
        )
        password2 = st.text_input(
            "Repetir contraseña", type="password",
            autocomplete="new-password", key="signup_password2",
        )
        invitacion = st.text_input(
            "Código de invitación", key="signup_code",
            help="Pedíselo a quien administra la app.",
        )
        submitted = st.form_submit_button(
            "Crear cuenta", type="primary", width="stretch",
        )

    if submitted:
        if not username or not password:
            st.error("Completá usuario y contraseña.")
            return
        if password != password2:
            st.error("Las contraseñas no coinciden.")
            return
        if (invitacion or "").strip() != os.environ.get("SIGNUP_CODE", ""):
            st.error("Código de invitación incorrecto.")
            return
        try:
            with connect() as conn:
                new_id = create_user(
                    conn, username.strip(), password, fullname.strip() or None,
                )
            # Auto-login después de crear cuenta.
            _set_session(new_id, username.strip(), fullname.strip() or None)
            st.success(f"Cuenta creada. ¡Hola, {fullname or username}!")
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def render() -> None:
    """Pantalla de login + signup en tabs. Si el login es exitoso, hace rerun."""
    _, c, _ = st.columns([1, 2, 1])
    with c:
        # Hero: logo (st.image, sobrevive al sanitizer) + título + tagline.
        render_logo(72)
        render_html(
            """
            <div style="text-align:center; padding: 0.25rem 0 0.5rem 0;">
                <h1 style="margin: 0.25rem 0 0.25rem; font-size: 2rem;
                           font-weight: 700; letter-spacing: -0.02em;">
                    Radar Financiero
                </h1>
                <p style="color: #9aa3b8; font-size: 1rem; margin: 0;">
                    Llevá el control de tus gastos en serio.
                </p>
            </div>
            """
        )

        if signup_habilitado():
            tab_login, tab_signup = st.tabs(["Iniciar sesión", "Crear cuenta"])
            with tab_login:
                _render_login_form()
            with tab_signup:
                _render_signup_form()
        else:
            _render_login_form()
            st.caption("El registro de cuentas nuevas está deshabilitado.")


def render_logout_button() -> None:
    user = st.session_state.get("current_username", "")
    fullname = st.session_state.get("current_user_fullname") or user
    with st.sidebar:
        st.markdown(f"👤 **{fullname}**")
        if st.button("Cerrar sesión", width="stretch"):
            for k in (
                "logged_in", "current_user_id",
                "current_username", "current_user_fullname",
            ):
                st.session_state.pop(k, None)
            # Invalida el token de sesión de la URL (si lo había).
            if QUERY_PARAM in st.query_params:
                del st.query_params[QUERY_PARAM]
            st.rerun()
