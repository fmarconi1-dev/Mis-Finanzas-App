"""Test de KPIs con la fórmula disjunta (Fase 2b).

Cambio respecto del Excel original: Compra Divisa pasa de Gasto Variable a
Inversion / Ahorro y Resguardo. Variable e Inversion ahora son disjuntos
(antes Variable incluía Inversion como sub-bucket).

Valores esperados (recalculados al 11/5/2026):

    Ingreso anual      = $15.014.431,00    (sin cambios)
    Ingreso/mes        = $ 3.002.886,20    (sin cambios)
    Gasto anual        = $ 9.572.366,33    (antes $13.266.630)
    Gasto/mes          = $ 1.914.473,27    (antes $ 2.653.326)
    Gasto fijo anual   = $ 4.275.075,71    (sin cambios)
    Gasto fijo/mes     = $   855.015,14    (sin cambios)
    Gasto var anual    = $ 5.297.290,62    (antes $ 8.991.555)
    Gasto var/mes      = $ 1.059.458,12    (antes $ 1.798.311)
    Inversión anual    = $ 3.694.264,31    (antes $ 1.360.000)
    Inversión/mes      = $   738.852,86    (antes $   272.000)
    Desahorro anual    = $ 1.349.431,00    (Venta divisa, ahora explicitado)
    % gasto fijo       = 28.47%            (sin cambios)
    % gasto variable   = 35.28%            (antes 59.89%)
    % inversión        = 24.61%            (antes  9.06%)
    % resto            = 11.64%            (antes  2.58%)
    Saldo CC           = $ 1.849.316,01    (sin cambios)

Tolerancia: ±$1 para montos absolutos, ±0.05 pp para porcentajes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.db import connect
from core.ingest import run_import
from core.metrics import (
    compute_kpis,
    load_categorias_full,
    load_transactions,
    saldo_cuenta_corriente,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DIARIO_CSV = REPO_ROOT / "Diario.csv"
MENSUAL_CSV = REPO_ROOT / "Mensual.csv"

# Valores esperados (fórmula disjunta, Fase 2b).
EXPECTED = {
    "ingreso_anual":    15_014_431.00,
    "ingreso_mes":       3_002_886.20,
    "gasto_anual":       9_572_366.33,
    "gasto_mes":         1_914_473.27,
    "fijo_anual":        4_275_075.71,
    "fijo_mes":            855_015.14,
    "variable_anual":    5_297_290.62,
    "variable_mes":      1_059_458.12,
    "inversion_anual":   3_694_264.31,
    "inversion_mes":       738_852.86,
    "desahorro_anual":   1_349_431.00,
    "desahorro_mes":       269_886.20,
    "pct_fijo":               0.2847,
    "pct_variable":           0.3528,
    "pct_inversion":          0.2461,
    "pct_resto":              0.1164,
    "saldo_cc":          1_849_316.01,
    "meses_cubiertos":       5,
}

TOL_MONTO = 1.0       # ±$1
TOL_PCT = 0.0005      # ±0.05 puntos porcentuales


@pytest.fixture
def kpis_db(tmp_path, monkeypatch):
    """Importa Diario+Mensual a una DB temporal y devuelve (conn_path, kpis)."""
    db_tmp = tmp_path / "finanzas_kpis.db"
    monkeypatch.setenv("DB_PATH", str(db_tmp))
    run_import(DIARIO_CSV, MENSUAL_CSV, anio=2026, force=False)

    with connect(db_tmp) as conn:
        df = load_transactions(conn, user_id=1)
        cats = load_categorias_full(conn, user_id=1)
        saldo = saldo_cuenta_corriente(conn, user_id=1)
        kpis = compute_kpis(df, cats, fondo_usd=864.0, saldo_cc=saldo)

    return db_tmp, kpis


def _aprox(actual: float, expected: float, tol: float) -> bool:
    return abs(actual - expected) <= tol


@pytest.mark.parametrize("key", [
    "ingreso_anual", "ingreso_mes",
    "gasto_anual", "gasto_mes",
    "fijo_anual", "fijo_mes",
    "variable_anual", "variable_mes",
    "inversion_anual", "inversion_mes",
    "desahorro_anual", "desahorro_mes",
    "saldo_cc",
])
def test_montos_absolutos(kpis_db, key):
    """Cada métrica de monto debe coincidir con el Excel ±$1."""
    _, kpis = kpis_db
    actual = kpis[key]
    expected = EXPECTED[key]
    assert _aprox(actual, expected, TOL_MONTO), (
        f"{key}: actual=${actual:,.2f} expected=${expected:,.2f} "
        f"diff=${abs(actual - expected):,.2f}"
    )


@pytest.mark.parametrize("key", ["pct_fijo", "pct_variable", "pct_inversion", "pct_resto"])
def test_porcentajes(kpis_db, key):
    """Cada % debe coincidir con el Excel ±0.05 pp."""
    _, kpis = kpis_db
    actual = kpis[key]
    expected = EXPECTED[key]
    assert _aprox(actual, expected, TOL_PCT), (
        f"{key}: actual={actual*100:.2f}% expected={expected*100:.2f}% "
        f"diff={abs(actual - expected)*100:.2f}pp"
    )


def test_meses_cubiertos(kpis_db):
    """Enero-Mayo 2026 = 5 meses con datos."""
    _, kpis = kpis_db
    assert kpis["meses_cubiertos"] == EXPECTED["meses_cubiertos"], (
        f"meses_cubiertos: actual={kpis['meses_cubiertos']} "
        f"expected={EXPECTED['meses_cubiertos']}"
    )


def test_porcentajes_suman_100(kpis_db):
    """Sanidad: %fijo + %variable + %inversión + %resto = 100% (±0.01)."""
    _, kpis = kpis_db
    total = (
        kpis["pct_fijo"]
        + kpis["pct_variable"]
        + kpis["pct_inversion"]
        + kpis["pct_resto"]
    )
    assert abs(total - 1.0) <= 0.0001, (
        f"Los porcentajes no suman 100%: {total*100:.2f}%"
    )
