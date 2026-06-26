"""Paleta semántica de la app + template Plotly unificado.

Importar desde acá en lugar de hardcodear hex en las vistas. El ojo aprende
que el azul siempre es ingreso, el rojo gasto, el verde inversión, etc.

Al importar este módulo se registra y activa el template "radar" en Plotly,
así todos los gráficos de la app comparten paleta y estilo de fondo/grilla
sin tener que tocar cada `update_layout` individualmente.
"""

import plotly.graph_objects as go
import plotly.io as pio

# ---------- Colores por concepto financiero ----------

COLOR_INGRESO    = "#60a5fa"   # azul claro (sky-400)
COLOR_GASTO      = "#f43f5e"   # rosa/rojo Cosmic Slate (rose-500)
COLOR_FIJO       = "#fb923c"   # naranja (sub-grupo Gasto Fijo)
COLOR_VARIABLE   = "#f43f5e"   # mismo rojo (sub-grupo Gasto Variable)
COLOR_INVERSION  = "#10b981"   # esmeralda Cosmic Slate (emerald-500)
COLOR_DESAHORRO  = "#fbbf24"   # ámbar
COLOR_NEUTRO     = "#A1A1AA"   # zinc-400
COLOR_ACENTO     = "#8b5cf6"   # violeta Cosmic Slate (primaryColor del tema)

# Fondo translúcido para áreas bajo curva, hovers, etc.
COLOR_ACENTO_BG  = "rgba(139, 92, 246, 0.10)"

# Mapping grupo → color para gráficos que agrupan por grupo (donut, barras).
COLOR_POR_GRUPO = {
    "Ingreso":        COLOR_INGRESO,
    "Gasto Fijo":     COLOR_FIJO,
    "Gasto Variable": COLOR_VARIABLE,
    "Inversion":      COLOR_INVERSION,
    "Sin categorizar": COLOR_NEUTRO,
}

# Paleta cíclica para series múltiples (ej. medias móviles). Tonos Cosmic Slate.
COLORES_MA = [
    "#fbbf24",  # ámbar
    "#f43f5e",  # rosa (rose-500)
    "#a78bfa",  # violeta claro (violet-400)
    "#60a5fa",  # azul (sky-400)
    "#10b981",  # esmeralda (emerald-500)
    "#fb923c",  # naranja
]


# ---------- Template Plotly: aplicar al importar ----------

_RADAR_TEMPLATE = go.layout.Template(
    layout=dict(
        paper_bgcolor="rgba(0,0,0,0)",   # transparente: hereda el fondo del tema Streamlit
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E4E4E7", family="Inter, sans-serif", size=12),
        title=dict(font=dict(size=14, family="Space Grotesk, sans-serif")),
        xaxis=dict(
            gridcolor="#27272A",   # zinc-800 (Cosmic Slate)
            zerolinecolor="#27272A",
            linecolor="#3F3F46",   # zinc-700
        ),
        yaxis=dict(
            gridcolor="#27272A",
            zerolinecolor="#27272A",
            linecolor="#3F3F46",
        ),
        # Colores cíclicos: si un gráfico no especifica color, usa éstos en orden.
        colorway=[
            COLOR_INGRESO, COLOR_GASTO, COLOR_INVERSION,
            COLOR_DESAHORRO, COLOR_FIJO, COLOR_NEUTRO,
        ],
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(font_size=12, font_family="JetBrains Mono, monospace"),
    )
)

pio.templates["radar"] = _RADAR_TEMPLATE
pio.templates.default = "radar"
