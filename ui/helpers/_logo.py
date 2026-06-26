"""Helpers para mostrar el logo en HTML inline.

El logo es un SVG simple (círculos concéntricos con un barrido tipo radar) que
embebemos directamente para evitar problemas de paths/CDN en producción.

Nota: `st.html()` (Streamlit ≥1.33) sanitiza el HTML con DOMPurify y elimina
los `<svg>` inline. Por eso para mostrar el logo en hero blocks usamos
`render_logo()` que dibuja el SVG como st.image() nativo en una columna
centrada (esto sí funciona porque Streamlit sirve la imagen como recurso).
"""

from __future__ import annotations

import os

import streamlit as st


_LOGO_PATH = "assets/logo.svg"


_LOGO_SVG_BODY = """\
<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" style="display:inline-block; vertical-align: middle;">
  <circle cx="32" cy="32" r="30" fill="#0e1117"/>
  <circle cx="32" cy="32" r="26" fill="none" stroke="#6ee7b7" stroke-width="2.5" opacity="0.55"/>
  <circle cx="32" cy="32" r="17" fill="none" stroke="#6ee7b7" stroke-width="2" opacity="0.75"/>
  <circle cx="32" cy="32" r="6" fill="#6ee7b7"/>
  <line x1="32" y1="32" x2="55" y2="14"
        stroke="#6ee7b7" stroke-width="2" stroke-linecap="round" opacity="0.85"/>
</svg>"""


def inline_logo(size: int = 64) -> str:
    """Devuelve el SVG del logo como string HTML.

    OJO: `st.html()` sanitiza con DOMPurify y elimina `<svg>` inline. Esta
    función queda por compatibilidad pero NO debe usarse para renderizar el
    logo en hero blocks — usar `render_logo()` en su lugar.
    """
    return _LOGO_SVG_BODY.replace(
        '<svg viewBox',
        f'<svg width="{size}" height="{size}" viewBox',
    )


def render_logo(size: int = 64) -> None:
    """Dibuja el logo centrado usando st.image (resiste el sanitizer de st.html).

    Si por algún motivo no se encuentra el SVG, no rompe — solo no muestra
    el logo. Llamar dentro de un hero block, ANTES del título.
    """
    if not os.path.exists(_LOGO_PATH):
        return
    # Centrado con 3 columnas: la del medio aloja el logo.
    _, c, _ = st.columns([1, 1, 1])
    with c:
        try:
            st.image(_LOGO_PATH, width=size)
        except Exception:
            # Si Streamlit no puede renderizar el SVG (versiones viejas),
            # mostramos un emoji como fallback.
            st.markdown("### 🎯")


def try_set_logo() -> None:
    """Si la versión de Streamlit lo soporta (≥1.34), fija el logo arriba.

    Funciona aunque la sidebar esté colapsada — Streamlit lo muestra como
    icon-image en la esquina superior."""
    try:
        st.logo(
            image="assets/logo-horizontal.svg",
            icon_image="assets/logo.svg",
        )
    except Exception:
        # Streamlit <1.34 no tiene st.logo(). No es crítico — el favicon
        # (page_icon) y los hero inline siguen mostrando la identidad.
        pass
