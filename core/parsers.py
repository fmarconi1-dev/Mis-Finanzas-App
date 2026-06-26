"""Parsers puros para normalizar el CSV original.

El CSV `Diario.csv` viene de Excel en español y tiene varios "quirks" que
detectamos al inspeccionarlo:

  * Encoding latin-1 (Windows-1252) — los acentos vienen como bytes 0xE1/0xF1.
  * Separador `;` y formato de número en español (miles con `.`, decimales con `,`).
  * `$-   ` con espacios = cero pesos.
  * `-$32.520,00` = valor negativo (devolución).
  * Strings vacíos en algunas celdas en lugar de `$0`.
  * `Pago tarjeta ` (con espacio final) coexiste con `Pago tarjeta` en la columna Motivo.
  * Fechas en formato `d/m/yyyy` (no `dd/mm/yyyy`).

Todas estas funciones son puras y testeables sin tocar Streamlit ni la DB.
"""

from __future__ import annotations

import ast
import operator
from datetime import datetime, date
from typing import Optional


# Encoding usado por Excel español al exportar a CSV en sistemas legacy.
CSV_ENCODING = "latin-1"
CSV_SEPARATOR = ";"


def parse_currency(raw: object) -> float:
    """Convierte un string con formato de moneda en español a float.

    Casos cubiertos (verificados contra el CSV real del usuario):

    >>> parse_currency("$2.700.000,00")
    2700000.0
    >>> parse_currency(" $-   ")
    0.0
    >>> parse_currency("-$32.520,00")
    -32520.0
    >>> parse_currency("")
    0.0
    >>> parse_currency(None)
    0.0
    >>> parse_currency("$-")
    0.0
    >>> parse_currency("$80.800,00 ")
    80800.0
    """
    if raw is None:
        return 0.0

    # Aceptamos floats/ints ya parseados (por ejemplo desde pandas).
    if isinstance(raw, (int, float)):
        return float(raw)

    s = str(raw).strip()
    if not s:
        return 0.0

    # Detectar signo negativo al inicio (antes del $).
    sign = 1
    if s.startswith("-"):
        sign = -1
        s = s[1:].strip()

    # Sacar símbolo de moneda.
    s = s.lstrip("$").strip()

    # Si lo que queda es vacío o sólo un guión, es cero.
    if not s or s == "-":
        return 0.0

    # Excel español: "." separa miles, "," separa decimales.
    # Convertir a formato "1234.56" para float().
    s = s.replace(".", "").replace(",", ".")

    try:
        return sign * float(s)
    except ValueError:
        # No pudimos parsear: devolvemos cero y dejamos que la capa de ingest
        # registre el incidente. Nunca silenciamos retornando None porque
        # corromper Caja es peor que mostrar un cero en una fila puntual.
        return 0.0


def parse_date(raw: object) -> Optional[date]:
    """Convierte una fecha en formato d/m/yyyy o dd/mm/yyyy a `date`.

    Devuelve None si la celda está vacía (fila de cierre del CSV).

    >>> parse_date("1/1/2026")
    datetime.date(2026, 1, 1)
    >>> parse_date("11/5/2026")
    datetime.date(2026, 5, 11)
    >>> parse_date("") is None
    True
    """
    if raw is None:
        return None

    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw

    s = str(raw).strip()
    if not s:
        return None

    # Intentamos varios formatos por si Excel cambia comportamiento.
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def normalize_motivo(raw: object) -> str:
    """Limpia el campo Motivo: trim de espacios y normalización de capitalización.

    Mantiene el casing original (los nombres están en español con mayúsculas
    iniciales) pero saca espacios trailing/leading para evitar que
    `"Pago tarjeta "` y `"Pago tarjeta"` sean categorías distintas.

    >>> normalize_motivo("Pago tarjeta ")
    'Pago tarjeta'
    >>> normalize_motivo("  Compras  ")
    'Compras'
    >>> normalize_motivo("")
    ''
    >>> normalize_motivo(None)
    ''
    """
    if raw is None:
        return ""
    return str(raw).strip()


# ---------- Parser de expresiones aritméticas (input de Importe) ----------

# Operadores permitidos. Pow (**) deliberadamente NO está — evita confusiones
# y abusos (un número grande elevado a otro grande puede colgar el servidor).
_EXPR_OPS = {
    ast.Add:  operator.add,
    ast.Sub:  operator.sub,
    ast.Mult: operator.mul,
    ast.Div:  operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def parse_expression(raw: object) -> float:
    """Evalúa una expresión aritmética con formato argentino. Devuelve float.

    Acepta:
      - números enteros y decimales
      - operadores: + - * / ( )
      - '.' = separador de miles (se ignora)
      - ',' = separador decimal
      - espacios libres
      - signo unario al inicio o adentro

    Rechaza (lanza ValueError):
      - nombres de variables, llamadas a funciones (no se puede inyectar `__import__`)
      - operadores no listados (potencia, módulo, bit-shift)
      - sintaxis inválida

    >>> parse_expression("10000")
    10000.0
    >>> parse_expression("10.000")
    10000.0
    >>> parse_expression("10000 + 5000")
    15000.0
    >>> parse_expression("10.000 - 5.000")
    5000.0
    >>> parse_expression("(2500 + 1750) * 2")
    8500.0
    >>> parse_expression("10.000,50 + 200,25")
    10200.75
    >>> parse_expression("")
    0.0
    """
    if raw is None:
        return 0.0
    # Si ya es número, devolverlo tal cual (evita reinterpretar el '.' como miles).
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return 0.0

    # Formato argentino: el '.' es separador de miles (se elimina); el ',' es decimal.
    s_norm = s.replace(".", "").replace(",", ".")

    try:
        tree = ast.parse(s_norm, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Expresión inválida: {raw!r}") from e

    return float(_eval_expr_node(tree))


def _eval_expr_node(node):
    """Evalúa recursivamente un nodo AST permitiendo sólo números y _EXPR_OPS."""
    if isinstance(node, ast.Expression):
        return _eval_expr_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Constante no numérica: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = _EXPR_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Operador no permitido: {type(node.op).__name__}")
        return op(_eval_expr_node(node.left), _eval_expr_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _EXPR_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Operador unario no permitido: {type(node.op).__name__}")
        return op(_eval_expr_node(node.operand))
    raise ValueError(f"Expresión no permitida ({type(node).__name__})")


def is_valid_transaction_row(fecha: Optional[date], motivo: str) -> bool:
    """¿La fila tiene fecha y motivo? Filtra filas vacías y la de cierre del CSV.

    El CSV tiene una fila final tipo `;;;; $1.849.316,01 ;;;` (sólo Caja, sin
    fecha ni motivo) que es el saldo de cierre, no una transacción.
    """
    return fecha is not None and bool(motivo)
