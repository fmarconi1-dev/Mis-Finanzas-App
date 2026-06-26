"""Helper para inyectar HTML/CSS de forma compatible.

Streamlit ≥1.33 introdujo `st.html()` y deprecó `st.markdown(..., unsafe_allow_html=True)`
para contenido inline. En versiones recientes (1.41+), el `unsafe_allow_html` se
ignora silenciosamente y el HTML aparece como texto plano.

Esta función prefiere `st.html()` cuando está disponible y cae al markdown como
último recurso.
"""

from __future__ import annotations

import streamlit as st


def render_html(html: str) -> None:
    """Inyectar HTML/CSS arbitrario. Usa st.html si está, sino st.markdown."""
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)
