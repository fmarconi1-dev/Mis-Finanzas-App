"""Ajustes responsive para mobile.

Streamlit por default usa layout horizontal con `st.columns`, lo que en
pantalla chica termina apretando 4 columnas en 375-414px y se vuelve
ilegible. Acá inyectamos CSS minimalista para:

  * Apilar columnas verticalmente cuando el viewport es ≤640px.
  * Reducir el padding lateral del contenedor principal en mobile para que
    el contenido use el ancho real.
  * Asegurar que dataframes y plotly hagan scroll horizontal si su contenido
    es más ancho que la pantalla.
  * Aumentar el target táctil de botones e inputs.

Usamos selectores `data-testid` (más estables entre versiones de Streamlit
que las clases CSS internas).
"""

from __future__ import annotations

import streamlit as st

from ui.helpers._html import render_html


_MOBILE_CSS = """
<style>
/* ----- Mobile (<= 640px) ----- */
@media (max-width: 640px) {

    /* Apilar columnas verticalmente. Cualquier st.columns(N) → 1 col. */
    [data-testid="column"],
    [data-testid="stColumn"] {
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
        margin-bottom: 0.5rem;
    }

    /* Padding del contenedor principal más chico para ganar espacio. */
    .block-container {
        padding-top: 1rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-bottom: 4rem !important;
    }

    /* Métricas con más respiro vertical (eran demasiado apretadas). */
    [data-testid="stMetric"] {
        padding: 0.5rem 0;
    }

    /* Inputs: target táctil de 44px+ (Apple HIG / Material recomiendan eso). */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stSelectbox"] [data-baseweb="select"] {
        min-height: 44px;
        font-size: 16px !important; /* iOS evita auto-zoom con ≥16px */
    }

    /* Botones más altos y con mejor tap. */
    [data-testid="stButton"] button,
    [data-testid="stFormSubmitButton"] button {
        min-height: 44px;
        font-size: 1rem;
    }

    /* Tabs: que el texto no se rompa en dos líneas en mobile (los iconos
       ya ocupan bastante). */
    [data-testid="stTabs"] button [data-testid="stMarkdownContainer"] p {
        font-size: 0.85rem;
        white-space: nowrap;
    }

    /* Dataframes: scroll horizontal nativo cuando el contenido excede. */
    [data-testid="stDataFrame"] {
        overflow-x: auto;
    }

    /* Toasts más visibles arriba en mobile. */
    [data-testid="stToast"] {
        font-size: 0.95rem;
    }
}

/* ----- Tablet (641-1024px) ----- */
@media (min-width: 641px) and (max-width: 1024px) {
    /* Columnas de 4 en tablet → 2 por fila usando flex-wrap. */
    [data-testid="column"],
    [data-testid="stColumn"] {
        min-width: 45%;
        flex: 1 1 45% !important;
    }
}
</style>
"""


def apply_responsive_css() -> None:
    """Inyectar el CSS responsive. Llamar UNA vez al inicio de app.py,
    después de st.set_page_config."""
    render_html(_MOBILE_CSS)
