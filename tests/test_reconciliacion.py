"""EL test crítico del MVP.

Garantiza que el parser + la lógica de Caja reproduzcan EXACTAMENTE la columna
Caja del Diario.csv, fila por fila. Si este test no pasa, no hay dashboard:
significa que internamente la app tiene un saldo distinto al que ves en tu Excel.

Hay dos niveles de test:

  1. `test_caja_parser_solo` — recorre el CSV con los parsers puros y verifica
     fila por fila. Falla rápido si hay un bug en parse_currency o en la lógica
     básica de acumulación. NO toca la DB.

  2. `test_caja_via_db` — corre el pipeline completo de ingest a SQLite, luego
     consulta la DB y reconstruye el histórico de Caja, y verifica que la última
     fila iguale al valor de cierre que tenemos en Mensual.csv ($1.849.316,01).
     Detecta bugs de import (off-by-one, filas perdidas, etc.).
"""

from __future__ import annotations

import csv
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.parsers import (
    CSV_ENCODING,
    CSV_SEPARATOR,
    is_valid_transaction_row,
    normalize_motivo,
    parse_currency,
    parse_date,
)
from core.db import init_db, connect, get_config
from core.ingest import run_import


REPO_ROOT = Path(__file__).resolve().parent.parent
DIARIO_CSV = REPO_ROOT / "Diario.csv"
MENSUAL_CSV = REPO_ROOT / "Mensual.csv"

# Saldo final esperado al cierre del Diario (11/5/2026). Coincide con el valor
# "Saldo cuenta corriente" del Mensual.csv → es nuestro número-ancla.
SALDO_FINAL_ESPERADO = 1_849_316.01

# Tolerancia: ±$0.01 (un centavo, para absorber redondeo de float64).
TOL = 0.01


def _iter_csv_rows():
    """Generator de filas (fecha_raw, pasivos_raw, ingresos_raw, motivo_raw, caja_raw)."""
    with open(DIARIO_CSV, encoding=CSV_ENCODING, newline="") as f:
        reader = csv.reader(f, delimiter=CSV_SEPARATOR)
        next(reader)  # skip header
        for line_no, raw in enumerate(reader, start=2):
            row = (raw + [""] * 5)[:5]
            yield line_no, row


def test_csv_existe():
    """Pre-flight: el CSV de origen tiene que estar al lado del paquete."""
    assert DIARIO_CSV.exists(), f"No encuentro {DIARIO_CSV}"
    assert MENSUAL_CSV.exists(), f"No encuentro {MENSUAL_CSV}"


def test_caja_parser_solo():
    """Recorre el CSV con los parsers y verifica Caja calculada == Caja del CSV
    en cada fila (±$0.01).

    Si esto falla, hay un bug en:
      - parse_currency (no maneja algún formato de moneda)
      - parse_date (filtra filas que no debería)
      - la asunción de que la primera fila 'Caja' es saldo inicial
    """
    caja_calculada: float | None = None
    errores: list[str] = []
    filas_procesadas = 0
    saldo_inicial_visto = None

    for line_no, row in _iter_csv_rows():
        fecha_raw, pasivos_raw, ingresos_raw, motivo_raw, caja_raw = row
        fecha = parse_date(fecha_raw)
        motivo = normalize_motivo(motivo_raw)

        # Primera fila Caja = saldo de apertura.
        if motivo == "Caja" and caja_calculada is None:
            caja_calculada = parse_currency(caja_raw)
            saldo_inicial_visto = caja_calculada
            continue

        if not is_valid_transaction_row(fecha, motivo):
            continue

        pasivos = parse_currency(pasivos_raw)
        ingresos = parse_currency(ingresos_raw)
        caja_calculada = (caja_calculada or 0.0) + ingresos - pasivos
        caja_csv = parse_currency(caja_raw)

        diff = abs(caja_calculada - caja_csv)
        if diff > TOL:
            errores.append(
                f"  Línea {line_no}: motivo={motivo!r} fecha={fecha} "
                f"calculado=${caja_calculada:,.2f} csv=${caja_csv:,.2f} "
                f"diff=${diff:,.2f}"
            )
        filas_procesadas += 1

    assert saldo_inicial_visto is not None, "No detecté la fila de saldo inicial 'Caja'."
    assert filas_procesadas > 100, (
        f"Sólo procesé {filas_procesadas} filas; algo está filtrando demasiado."
    )
    assert not errores, (
        f"Reconciliación fallida en {len(errores)} filas:\n" + "\n".join(errores)
    )

    # Adicionalmente, el saldo final calculado debe igualar el valor de cierre.
    assert caja_calculada is not None
    assert abs(caja_calculada - SALDO_FINAL_ESPERADO) <= TOL, (
        f"Saldo final calculado ${caja_calculada:,.2f} != esperado "
        f"${SALDO_FINAL_ESPERADO:,.2f}"
    )


def test_caja_via_db(tmp_path, monkeypatch):
    """Pipeline completo: import a SQLite → reconstrucción de Caja → reconciliación
    contra el saldo final esperado.

    Usa una DB temporal (tmp_path) para no tocar la real del usuario.
    """
    db_tmp = tmp_path / "finanzas_test.db"
    monkeypatch.setenv("DB_PATH", str(db_tmp))

    result = run_import(DIARIO_CSV, MENSUAL_CSV, anio=2026, force=False)

    assert result.transacciones_insertadas > 100, (
        f"Sólo importé {result.transacciones_insertadas} transacciones."
    )
    assert result.saldo_inicial > 0, "El saldo inicial no fue detectado."

    # Reconstruir Caja desde la DB y comparar al cierre.
    with connect(db_tmp) as conn:
        saldo_inicial = float(get_config(conn, "saldo_inicial_caja", "0", user_id=1))
        row = conn.execute(
            "SELECT COALESCE(SUM(ingresos - pasivos), 0) AS delta "
            "FROM transacciones WHERE user_id = ?",
            (1,),
        ).fetchone()
        saldo_final = saldo_inicial + float(row["delta"])

    assert abs(saldo_final - SALDO_FINAL_ESPERADO) <= TOL, (
        f"Saldo final reconstruido desde DB ${saldo_final:,.2f} != "
        f"esperado ${SALDO_FINAL_ESPERADO:,.2f}"
    )


def test_motivos_normalizados_sin_espacios_trailing(tmp_path, monkeypatch):
    """Garantiza que 'Pago tarjeta ' (con espacio final) y 'Pago tarjeta' no
    aparezcan como motivos distintos en la DB."""
    db_tmp = tmp_path / "finanzas_test.db"
    monkeypatch.setenv("DB_PATH", str(db_tmp))
    run_import(DIARIO_CSV, MENSUAL_CSV, anio=2026, force=False)

    with connect(db_tmp) as conn:
        motivos = [
            r["motivo"]
            for r in conn.execute(
                "SELECT DISTINCT motivo FROM transacciones WHERE user_id = ?", (1,)
            )
        ]

    motivos_con_espacios = [m for m in motivos if m != m.strip()]
    assert not motivos_con_espacios, (
        f"Motivos con espacios trailing/leading: {motivos_con_espacios}"
    )
