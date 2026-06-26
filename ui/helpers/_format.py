"""Formateadores compartidos por las vistas Streamlit.

Centralizar acá evita que el formato de pesos diverja entre Dashboard,
Mensual y Configuración (que fue el bug del primer round de screenshots).
"""

from __future__ import annotations

import math


def _is_nan(v) -> bool:
    return isinstance(v, float) and math.isnan(v)


def fmt_ars(value: float | None) -> str:
    """Pesos al estilo argentino con signo ANTES del símbolo: $1.234,56 / -$789,01.

    El signo va antes del $ para que st.metric lo interprete como delta negativo.
    """
    if value is None or _is_nan(value):
        return "—"
    neg = value < 0
    s = f"{abs(value):,.2f}"
    # 1,234,567.89 → 1.234.567,89
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-${s}" if neg else f"${s}"


def fmt_ars_corto(value: float | None) -> str:
    """Versión compacta para cards de KPIs: $15,0M / $850K / $1.234 / -$789.

    Pensado para que números grandes se escaneen de un vistazo. El número
    exacto se puede mantener en el `help` del st.metric.
    """
    if value is None or _is_nan(value):
        return "—"
    neg = value < 0
    abs_v = abs(value)
    signo = "-" if neg else ""
    if abs_v >= 1_000_000:
        formatted = f"{abs_v / 1_000_000:.1f}".replace(".", ",")
        return f"{signo}${formatted}M"
    if abs_v >= 10_000:
        # 850K, 1.234K para valores muy grandes — pero hasta 9.999 mostramos exacto.
        formatted = f"{abs_v / 1_000:.0f}"
        return f"{signo}${formatted}K"
    return fmt_ars(value)


def fmt_usd(value: float | None) -> str:
    if value is None or _is_nan(value):
        return "—"
    return f"USD {value:,.2f}"


def fmt_pct(value: float | None) -> str:
    if value is None or _is_nan(value):
        return "—"
    return f"{value * 100:.2f}%"


def fmt_pct_signed(value: float | None) -> str:
    if value is None or _is_nan(value):
        return "—"
    return f"{value * 100:+.1f}%"
