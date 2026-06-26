"""Tests del parser de expresiones aritméticas para el campo Importe."""

from __future__ import annotations

import pytest

from core.parsers import parse_expression


# ---------- Casos válidos ----------

@pytest.mark.parametrize("entrada,esperado", [
    # Enteros
    ("10000", 10000.0),
    ("0", 0.0),
    # Formato argentino — miles con '.'
    ("10.000", 10000.0),
    ("1.234.567", 1234567.0),
    # Decimales con ','
    ("10000,50", 10000.5),
    ("0,25", 0.25),
    # Miles + decimales
    ("10.000,50", 10000.5),
    ("1.234.567,89", 1234567.89),
    # Suma
    ("10000 + 5000", 15000.0),
    ("8.500 + 3.200 + 1.250", 12950.0),
    # Resta
    ("10000 - 5000", 5000.0),
    ("10.000 - 5.000", 5000.0),
    # Mezcla y paréntesis
    ("(2500 + 1750) * 2", 8500.0),
    ("1000 + 500 - 200 + 50", 1350.0),
    # Decimales con operaciones
    ("10.000,50 + 200,25", 10200.75),
    # Multiplicación y división
    ("1000 * 3", 3000.0),
    ("1000 / 4", 250.0),
    # Unario
    ("-5000", -5000.0),
    ("+5000", 5000.0),
    # Espacios y vacíos
    ("   10000   ", 10000.0),
    ("", 0.0),
    ("    ", 0.0),
])
def test_parse_expression_valida(entrada, esperado):
    assert parse_expression(entrada) == pytest.approx(esperado, rel=1e-9, abs=1e-6)


def test_resultado_negativo_no_lanza():
    """Restas que dan negativo NO son error del parser — la UI decide qué hacer."""
    assert parse_expression("5000 - 10000") == -5000.0


# ---------- Casos inválidos ----------

@pytest.mark.parametrize("entrada", [
    "abc",                       # texto puro
    "10000 +",                   # sintaxis incompleta
    "5000 ** 2",                 # potencia (deliberadamente no permitida)
    "5000 % 3",                  # módulo (no permitido)
    "5000 ; print('hi')",        # múltiples statements
    "import os",                 # no es expresión
    "__import__('os')",          # intento de llamada
    "5000 + foo",                # variable no permitida
    "5000 << 2",                 # bit shift
    "True and 5000",             # booleanos no
])
def test_parse_expression_invalida(entrada):
    with pytest.raises(ValueError):
        parse_expression(entrada)


# ---------- Casos borde ----------

def test_acepta_none():
    assert parse_expression(None) == 0.0


def test_acepta_numero_directo():
    assert parse_expression(1500) == 1500.0
    assert parse_expression(1500.75) == 1500.75
