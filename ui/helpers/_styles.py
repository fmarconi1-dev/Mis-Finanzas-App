"""Design system: paleta "Cosmic Slate" portada del proyecto paralelo React.

Filosofía: alta legibilidad de datos, densidad eficiente, ruidos mínimos. Las
decisiones de color/tipografía vienen del CSS y los componentes de
`Mis-Finanzas-app-main` (Sidebar, Header, DashboardView).

Tokens principales:
    --cs-bg-0:    #09090B  fondo absoluto
    --cs-bg-1:    #18181B  cards / paneles
    --cs-bg-2:    #121214  paneles secundarios (header backdrop)
    --cs-border:  #27272A  bordes finos
    --cs-border-soft: #27272A66 (#27272A / 40 %)
    --cs-text:    #E4E4E7  texto base
    --cs-text-mid: #A1A1AA  texto secundario
    --cs-text-dim: #71717A  texto muted / metadata
    --cs-accent:  #8B5CF6  violeta — acentos IA / activo / focus
    --cs-accent-light: #A78BFA  hover
    --cs-positive: #10B981  esmeralda — ingresos / activos
    --cs-negative: #F43F5E  rosa/rojo — gastos / errores

Tipografías cargadas desde Google Fonts:
    Inter (UI), Space Grotesk (display / títulos), JetBrains Mono (números).

Selectores estables: `data-testid` (los usa Streamlit en sus propios tests).
"""

from __future__ import annotations

import streamlit as st

from ui.helpers._html import render_html


# ============================================================
#  Fonts: Google Fonts import + variables CSS
# ============================================================

_FONTS_IMPORT = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --cs-bg-0: #09090B;
    --cs-bg-1: #18181B;
    --cs-bg-2: #121214;
    --cs-border: #27272A;
    --cs-border-soft: rgba(39, 39, 42, 0.4);
    --cs-text: #E4E4E7;
    --cs-text-mid: #A1A1AA;
    --cs-text-dim: #71717A;
    --cs-accent: #8B5CF6;
    --cs-accent-light: #A78BFA;
    --cs-accent-bg: rgba(139, 92, 246, 0.10);
    --cs-positive: #10B981;
    --cs-negative: #F43F5E;
    --cs-info: #60A5FA;
    --cs-font-sans: 'Inter', ui-sans-serif, system-ui, sans-serif;
    --cs-font-display: 'Space Grotesk', 'Inter', sans-serif;
    --cs-font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
}

/* Body: fondo absoluto + tipografía Inter por default. */
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: var(--cs-bg-0) !important;
    color: var(--cs-text);
    font-family: var(--cs-font-sans);
}

/* Scrollbar Cosmic Slate */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--cs-bg-0); }
::-webkit-scrollbar-thumb {
    background: var(--cs-border);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: #3F3F46; }
</style>
"""


_DESIGN_SYSTEM_CSS = """
<style>
/* ============================================================
   1. Typography: Inter + Space Grotesk + JetBrains Mono
   ============================================================ */

html, body, [data-testid="stApp"],
[data-testid="stMarkdownContainer"],
[data-testid="stText"] {
    font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
    color: #E4E4E7;
}

h1, h2, h3, h4 {
    font-family: 'Space Grotesk', 'Inter', sans-serif;
    letter-spacing: -0.02em;
    color: #FFFFFF;
}
h1 { font-weight: 700; }
h2 { font-weight: 600; }
h3 { font-weight: 600; color: #E4E4E7; }

/* Números: monospace */
[data-testid="stMetricValue"],
[data-testid="stMetricDelta"],
.cs-mono, code {
    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    letter-spacing: -0.01em;
}

/* ============================================================
   2. Métricas (st.metric): tarjetas Cosmic Slate
   ============================================================ */

[data-testid="stMetric"] {
    background: #18181B;
    border: 1px solid #27272A;
    border-radius: 12px;
    padding: 0.9rem 1.1rem;
    transition: border-color 0.2s ease, background 0.2s ease;
}

[data-testid="stMetric"]:hover {
    border-color: rgba(139, 92, 246, 0.35);
    background: #1C1C20;
}

[data-testid="stMetricValue"] {
    font-size: 1.65rem !important;
    font-weight: 600;
    line-height: 1.2;
    color: #FFFFFF;
}

[data-testid="stMetricLabel"] {
    color: #71717A;
    font-size: 0.72rem !important;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-family: 'JetBrains Mono', monospace;
}

[data-testid="stMetricDelta"] {
    font-weight: 500;
    font-size: 0.8rem !important;
}

/* ============================================================
   3. Botones primarios: gradient violet (Cosmic Slate IA accent)
   ============================================================ */

[data-testid="stButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: linear-gradient(135deg, #8B5CF6 0%, #6366F1 100%);
    color: #FFFFFF !important;
    font-weight: 600;
    border: none;
    box-shadow: 0 0 0 0 rgba(139, 92, 246, 0);
    transition: box-shadow 0.2s ease, transform 0.15s ease;
    border-radius: 8px;
}

[data-testid="stButton"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
    background: linear-gradient(135deg, #A78BFA 0%, #818CF8 100%);
    color: #FFFFFF !important;
    box-shadow: 0 0 20px 0 rgba(139, 92, 246, 0.35);
    transform: translateY(-1px);
}

[data-testid="stButton"] button[kind="primary"]:active,
[data-testid="stFormSubmitButton"] button[kind="primary"]:active {
    transform: translateY(0);
}

/* Botones secundarios: outline zinc */
[data-testid="stButton"] button:not([kind="primary"]),
[data-testid="stFormSubmitButton"] button:not([kind="primary"]) {
    background: #18181B;
    color: #E4E4E7;
    border: 1px solid #27272A;
    border-radius: 8px;
    transition: border-color 0.2s ease, background 0.2s ease;
}

[data-testid="stButton"] button:not([kind="primary"]):hover,
[data-testid="stFormSubmitButton"] button:not([kind="primary"]):hover {
    border-color: rgba(139, 92, 246, 0.5);
    background: #1C1C20;
    color: #FFFFFF;
}

/* ============================================================
   4. Containers (st.container(border=True)) Cosmic Slate
   ============================================================ */

[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px;
    border: 1px solid #27272A !important;
    background: #18181B;
}

/* Expanders: el mismo look */
[data-testid="stExpander"] {
    border: 1px solid #27272A !important;
    border-radius: 12px !important;
    background: #18181B;
}
[data-testid="stExpander"] summary {
    color: #E4E4E7;
}
[data-testid="stExpander"] summary:hover {
    color: #FFFFFF;
}

/* ============================================================
   5. Inputs: borde acento violeta al focus
   ============================================================ */

[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stDateInput"] input {
    background: #09090B !important;
    color: #E4E4E7 !important;
    border: 1px solid #27272A !important;
    border-radius: 8px;
}

[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-testid="stDateInput"] input:focus {
    border-color: #8B5CF6 !important;
    box-shadow: 0 0 0 1px rgba(139, 92, 246, 0.5) !important;
    outline: none !important;
}

[data-baseweb="select"] > div {
    background: #09090B !important;
    border-color: #27272A !important;
    border-radius: 8px !important;
}
[data-baseweb="select"]:focus-within > div {
    border-color: #8B5CF6 !important;
    box-shadow: 0 0 0 1px rgba(139, 92, 246, 0.5) !important;
}

/* ============================================================
   6. Dividers más finos
   ============================================================ */

hr {
    opacity: 0.6;
    border-color: #27272A !important;
    margin: 1.5rem 0 !important;
}

/* ============================================================
   7. Tabs: indicador violeta al activo
   ============================================================ */

[data-testid="stTabs"] [data-baseweb="tab-list"] {
    border-bottom: 1px solid #27272A;
    gap: 0.5rem;
}

[data-testid="stTabs"] button[aria-selected="true"] {
    color: #A78BFA !important;
    font-weight: 600;
    border-bottom-color: #8B5CF6 !important;
}

[data-testid="stTabs"] button {
    color: #A1A1AA;
    font-family: 'Inter', sans-serif;
}

[data-testid="stTabs"] button:hover {
    color: #E4E4E7;
}

/* ============================================================
   8. Toasts: borde violeta a la izquierda
   ============================================================ */

[data-testid="stToast"] {
    border-left: 3px solid #8B5CF6;
    background: #18181B;
    color: #E4E4E7;
    border-radius: 8px;
}

/* ============================================================
   9. Captions: zinc-500
   ============================================================ */

[data-testid="stCaptionContainer"],
[data-testid="stCaption"] {
    color: #A1A1AA;
    font-size: 0.85rem;
}

/* ============================================================
   10. Sidebar: Cosmic Slate
   ============================================================ */

section[data-testid="stSidebar"] {
    background: #0A0A0C !important;
    border-right: 1px solid #27272A;
}

section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
    color: #E4E4E7;
}

/* ============================================================
   11. Tables / dataframes
   ============================================================ */

[data-testid="stDataFrame"] {
    border: 1px solid #27272A;
    border-radius: 8px;
    overflow: hidden;
}

/* ============================================================
   12. Status badges (info/success/warning/error)
   ============================================================ */

[data-testid="stAlert"] {
    border-radius: 10px;
    border: 1px solid #27272A;
    background: #18181B;
}

/* ============================================================
   13. Code blocks: mono + sutiles
   ============================================================ */

code, [data-testid="stCode"] {
    background: #121214 !important;
    color: #A78BFA !important;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace !important;
}

</style>
"""


def apply_design_system_css() -> None:
    """Inyectar fonts + design system Cosmic Slate. Llamar UNA vez al inicio
    de app.py, después de set_page_config y de apply_responsive_css."""
    render_html(_FONTS_IMPORT)
    render_html(_DESIGN_SYSTEM_CSS)
