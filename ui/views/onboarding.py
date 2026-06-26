"""Pantalla de bienvenida para usuarios nuevos.

Después del signup, cualquier usuario nuevo aterriza acá. Le presentamos lo
que la app ofrece (3 highlights), le pedimos su punto de partida (saldo
inicial + fondo USD opcional), y lo enviamos al Dashboard con el tour guiado
activado.

NO siembra categorías: el usuario las crea desde cero en Configuración o al
cargar su primera transacción.
"""

from __future__ import annotations

import streamlit as st

from core.db import connect, set_config
from core.metrics import fondo_emergencia_usd, saldo_inicial
from ui.helpers._html import render_html
from ui.helpers._logo import render_logo
from ui.helpers._tour import start_tour


def _render_feature_card(icon: str, title: str, body: str) -> None:
    """Tarjeta destacando una capacidad de la app."""
    with st.container(border=True):
        st.markdown(f"### {icon} {title}")
        st.caption(body)


def render(user_id: int, fullname: str = "") -> None:
    nombre = fullname.split(" ")[0] if fullname else "vos"

    _, c, _ = st.columns([1, 4, 1])
    with c:
        # ----- Hero -----
        render_logo(80)
        render_html(
            f"""
            <div style="text-align:center; padding: 0.25rem 0 1rem 0;">
                <h1 style="margin: 0.25rem 0 0.25rem; font-size: 2rem;
                           font-weight: 700; letter-spacing: -0.02em;">
                    ¡Hola, {nombre}!
                </h1>
                <p style="color: #9aa3b8; font-size: 1.05rem; margin: 0;">
                    Tu radar financiero personal. Cargá gastos en segundos,
                    presupuestá por categoría, y mirá cómo evoluciona tu plata.
                </p>
            </div>
            """
        )

        # ----- Highlights -----
        st.markdown("### Lo que vas a poder hacer")
        c1, c2, c3 = st.columns(3)
        with c1:
            _render_feature_card(
                "📊", "Dashboard en vivo",
                "Saldo, KPIs anuales/mensuales, distribución de tu plata y "
                "evolución de tu caja con medias móviles."
            )
        with c2:
            _render_feature_card(
                "💸", "Carga ultra rápida",
                "Chips de motivos frecuentes, montos recurrentes y un campo "
                "Importe que acepta expresiones como `5000 + 3200 - 200`."
            )
        with c3:
            _render_feature_card(
                "🎯", "Presupuesto vivo",
                "Comparativa Previsión vs Realidad con barras que te avisan "
                "cuándo te estás pasando del límite por categoría."
            )

        st.markdown("")  # respiro

        # ----- Form de configuración inicial -----
        with connect() as conn:
            saldo_actual = saldo_inicial(conn, user_id=user_id)
            fondo_actual = fondo_emergencia_usd(conn, user_id=user_id)

        with st.container(border=True):
            st.subheader("🚀 Tu punto de partida")
            st.caption(
                "Estos dos valores los podés cambiar cuando quieras desde "
                "**⚙️ Configuración**. Ahora sólo nos sirven para arrancar."
            )

            with st.form("onboarding"):
                saldo = st.number_input(
                    "💵 Saldo inicial en tu cuenta corriente (ARS)",
                    value=float(saldo_actual),
                    step=1000.0, format="%.2f",
                    help="Cuánto tenés hoy en tu cuenta. Si arrancás desde "
                         "cero o no sabés todavía, dejá 0.",
                )
                fondo = st.number_input(
                    "🛟 Fondo de emergencia (USD, opcional)",
                    value=float(fondo_actual),
                    min_value=0.0, step=100.0, format="%.2f",
                    help="Tu colchón en dólares. Sólo informativo: aparece "
                         "en el Dashboard como referencia.",
                )

                st.caption(
                    "💡 **Tu mapping de categorías arranca vacío**. Las vas "
                    "creando vos al cargar tus primeras transacciones o desde "
                    "Configuración. Así la taxonomía es 100% tuya."
                )

                submitted = st.form_submit_button(
                    "Entrar al Dashboard →", type="primary",
                    use_container_width=True,
                )

        # ----- Footer: qué pasa después -----
        st.caption(
            "Después de entrar te voy a guiar con un mini-tour por las 5 "
            "pestañas. Lo podés saltar en cualquier momento."
        )

        if submitted:
            with connect() as conn:
                set_config(conn, "saldo_inicial_caja", f"{saldo:.2f}", user_id=user_id)
                set_config(conn, "fondo_emergencia_usd", f"{fondo:.2f}", user_id=user_id)
                set_config(conn, "onboarding_completado", "1", user_id=user_id)
            # Iniciar el tour guiado: el usuario verá un panel en cada pestaña.
            start_tour()
            st.toast("¡Configurado! Arrancamos por el Dashboard.", icon="🎉")
            st.balloons()
            st.rerun()
