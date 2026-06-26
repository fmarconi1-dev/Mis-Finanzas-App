"""Importa Diario.csv y Mensual.csv a SQLite.

Estrategia:

  1. Diario.csv → tabla `transacciones`. La primera fila con motivo=='Caja'
     se interpreta como saldo de apertura y se guarda en `configuracion`
     (clave `saldo_inicial_caja`), NO como transacción.
  2. Mensual.csv → tabla `presupuesto`. Sólo importamos las columnas
     PREVISIÓN (12 columnas, una por mes); las columnas REALIDAD se ignoran
     porque van a ser recalculadas desde `transacciones`.
  3. La tabla `categorias` se inicializa con el mapping default si está vacía.

La importación es idempotente:
  - `--force`: borra el contenido previo y re-importa.
  - sin `--force`: detecta DB existente y aborta para evitar duplicados.

Uso desde CLI:
    python -m core.ingest                 # importa la primera vez
    python -m core.ingest --force         # re-importa desde cero
    python -m core.ingest --diario X.csv  # CSV personalizado
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# Soportamos correr como `python -m core.ingest` o `python core/ingest.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import (
    connect,
    init_db,
    set_config,
    get_db_path,
)
from core.parsers import (
    CSV_ENCODING,
    CSV_SEPARATOR,
    is_valid_transaction_row,
    normalize_motivo,
    parse_currency,
    parse_date,
)
from core.categorizer import DEFAULT_CATEGORIAS, DEFAULT_GRUPOS


# user_id por defecto para el flujo de ingest CLI (seed de Franco).
_DEFAULT_INGEST_USER_ID = 1


# ---------- Resultado de la importación ----------

@dataclass
class ImportResult:
    transacciones_insertadas: int = 0
    saldo_inicial: float = 0.0
    presupuesto_filas: int = 0
    categorias_inicializadas: int = 0
    motivos_sin_categorizar: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"  Transacciones importadas:   {self.transacciones_insertadas}",
            f"  Saldo inicial detectado:    ${self.saldo_inicial:,.2f}",
            f"  Filas de presupuesto:       {self.presupuesto_filas}",
            f"  Categorías inicializadas:   {self.categorias_inicializadas}",
        ]
        if self.motivos_sin_categorizar:
            lines.append(
                f"  Motivos SIN categorizar:    {', '.join(self.motivos_sin_categorizar)}"
            )
        if self.advertencias:
            lines.append("  Advertencias:")
            for w in self.advertencias:
                lines.append(f"    - {w}")
        return "\n".join(lines)


# ---------- Lectura CSV ----------

def _read_csv_rows(path: Path) -> list[list[str]]:
    """Lee un CSV con la configuración estándar del usuario (latin-1, `;`)."""
    with open(path, encoding=CSV_ENCODING, newline="") as f:
        return list(csv.reader(f, delimiter=CSV_SEPARATOR))


# ---------- Importación de Diario ----------

def import_diario(
    diario_path: Path, conn, user_id: int = _DEFAULT_INGEST_USER_ID
) -> ImportResult:
    """Lee Diario.csv y popula `transacciones` + `configuracion.saldo_inicial_caja`."""
    rows = _read_csv_rows(diario_path)
    if len(rows) < 2:
        raise ValueError(f"{diario_path} no tiene datos (sólo {len(rows)} filas)")

    result = ImportResult()
    saldo_inicial: float | None = None
    transacciones: list[tuple] = []

    # rows[0] es el header. Iteramos desde rows[1].
    for line_no, raw_row in enumerate(rows[1:], start=2):
        # Asegurar mínimo 5 columnas (Fecha, Pasivos, Ingresos, Motivo, Caja).
        row = (raw_row + [""] * 5)[:5]
        fecha_raw, pasivos_raw, ingresos_raw, motivo_raw, caja_raw = row

        fecha = parse_date(fecha_raw)
        motivo = normalize_motivo(motivo_raw)

        # Primera fila con motivo "Caja" = saldo inicial. NO es transacción.
        if motivo == "Caja" and saldo_inicial is None:
            saldo_inicial = parse_currency(caja_raw)
            continue

        # Filas vacías o de cierre del CSV: ignorar silenciosamente.
        if not is_valid_transaction_row(fecha, motivo):
            continue

        pasivos = parse_currency(pasivos_raw)
        ingresos = parse_currency(ingresos_raw)

        transacciones.append((fecha.isoformat(), pasivos, ingresos, motivo, user_id))

    if saldo_inicial is None:
        saldo_inicial = 0.0
        result.advertencias.append(
            "No se encontró fila de saldo inicial (motivo 'Caja'); se asume $0."
        )

    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        cur.executemany(
            "INSERT INTO transacciones (fecha, pasivos, ingresos, motivo, user_id) "
            "VALUES (?, ?, ?, ?, ?)",
            transacciones,
        )
        set_config(conn, "saldo_inicial_caja", f"{saldo_inicial:.2f}", user_id=user_id)
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise

    result.transacciones_insertadas = len(transacciones)
    result.saldo_inicial = saldo_inicial

    # Detectar motivos sin categorizar para advertir al usuario.
    motivos_unicos = {m for (_, _, _, m, _) in transacciones}
    sin_cat = sorted(m for m in motivos_unicos if m and m not in DEFAULT_GRUPOS)
    result.motivos_sin_categorizar = sin_cat

    return result


# ---------- Importación de Mensual ----------

# Filas a ignorar en Mensual.csv (totales, subtotales, errores Excel).
_MENSUAL_IGNORE_PREFIXES = (
    "TOTAL",
    "Diferencia",
    "SALDO",
    "#",  # #¡DIV/0! u otros errores Excel
)


def import_mensual(
    mensual_path: Path, anio: int, conn, user_id: int = _DEFAULT_INGEST_USER_ID
) -> int:
    """Lee Mensual.csv y popula `presupuesto` con las columnas PREVISIÓN.

    Layout esperado del CSV:
      - Fila con primer celda 'INGRESOS Y GASTOS' marca el header de la tabla.
      - Desde la fila siguiente, col 0 = motivo, cols 1, 3, 5, ..., 23 = PREVISIÓN
        para enero...diciembre (12 meses, paso 2).
      - Filas con motivo vacío o que empiezan con TOTAL/Diferencia/SALDO se ignoran.
    """
    rows = _read_csv_rows(mensual_path)

    header_idx = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == "INGRESOS Y GASTOS":
            header_idx = i
            break
    if header_idx is None:
        return 0  # no hay tabla; presupuesto queda vacío

    insertadas = 0
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        for raw_row in rows[header_idx + 1 :]:
            if not raw_row or not raw_row[0].strip():
                continue
            motivo = normalize_motivo(raw_row[0])
            if any(motivo.startswith(p) for p in _MENSUAL_IGNORE_PREFIXES):
                continue

            for mes in range(1, 13):
                col_idx = 1 + (mes - 1) * 2  # PREVISIÓN de cada mes
                if col_idx >= len(raw_row):
                    break
                monto = parse_currency(raw_row[col_idx])
                if monto == 0:
                    # No insertamos previsiones de cero: el SQL outer-join las trata como NaN
                    # y eso es preferible a "previsiones falsamente cero".
                    continue
                cur.execute(
                    "INSERT OR REPLACE INTO presupuesto "
                    "(motivo, anio, mes, monto_previsto, user_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (motivo, anio, mes, monto, user_id),
                )
                insertadas += 1
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    return insertadas


# ---------- Inicialización de categorías ----------

def init_categorias(
    conn,
    user_id: int = _DEFAULT_INGEST_USER_ID,
    defaults: Optional[dict] = None,
) -> int:
    """Inserta el mapping default para `user_id`. Idempotente.

    `defaults` controla qué set sembrar. Si es None, usa DEFAULT_CATEGORIAS
    (set legacy con Haberes Fundación/SBT/UCEMA — útil para el seed CLI de
    Franco). Para usuarios nuevos vía signup, pasar DEFAULT_CATEGORIAS_NEW_USER.
    """
    if defaults is None:
        defaults = DEFAULT_CATEGORIAS

    cur = conn.cursor()
    cur.execute("BEGIN")
    nuevas = 0
    try:
        for motivo, (grupo, subcat) in defaults.items():
            cur.execute(
                "INSERT INTO categorias (motivo, grupo, subcategoria, user_id) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(motivo, user_id) DO UPDATE SET "
                "    subcategoria = COALESCE(categorias.subcategoria, excluded.subcategoria)",
                (motivo, grupo, subcat, user_id),
            )
            if cur.rowcount > 0:
                nuevas += 1
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    return nuevas


# ---------- Orquestador ----------

def run_import(
    diario_path: Path,
    mensual_path: Path,
    anio: int,
    force: bool = False,
    user_id: int = _DEFAULT_INGEST_USER_ID,
) -> ImportResult:
    """Pipeline completo de importación para el `user_id` dado."""
    db_path = get_db_path()
    init_db(db_path)

    with connect(db_path) as conn:
        if force:
            for tbl in ("transacciones", "presupuesto", "configuracion"):
                conn.execute(f"DELETE FROM {tbl} WHERE user_id = ?", (user_id,))

        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM transacciones WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if existing["n"] > 0 and not force:
            raise RuntimeError(
                f"El usuario {user_id} ya tiene {existing['n']} transacciones. "
                "Usá --force para borrar y re-importar."
            )

        diario_result = import_diario(diario_path, conn, user_id=user_id)
        presupuesto_filas = import_mensual(mensual_path, anio, conn, user_id=user_id)
        nuevas_categorias = init_categorias(conn, user_id=user_id)

        diario_result.presupuesto_filas = presupuesto_filas
        diario_result.categorias_inicializadas = nuevas_categorias

    return diario_result


# ---------- CLI ----------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Importa Diario.csv y Mensual.csv a SQLite.")
    p.add_argument("--diario", type=Path, default=Path(os.environ.get("DIARIO_CSV", "Diario.csv")))
    p.add_argument("--mensual", type=Path, default=Path(os.environ.get("MENSUAL_CSV", "Mensual.csv")))
    p.add_argument("--anio", type=int, default=2026,
                   help="Año al que corresponden las previsiones del Mensual.csv (default 2026)")
    p.add_argument("--force", action="store_true",
                   help="Borra los datos previos antes de importar")
    p.add_argument("--user-id", type=int, default=_DEFAULT_INGEST_USER_ID,
                   help="Usuario destino del import (default 1 = local)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not args.diario.exists():
        print(f"ERROR: no encuentro {args.diario}", file=sys.stderr)
        return 1
    if not args.mensual.exists():
        print(f"ERROR: no encuentro {args.mensual}", file=sys.stderr)
        return 1

    print(f"Importando desde:")
    print(f"  Diario:  {args.diario}")
    print(f"  Mensual: {args.mensual}")
    print(f"  Año:     {args.anio}")
    print(f"  DB:      {get_db_path()}")
    print(f"  Force:   {args.force}")
    print()

    try:
        result = run_import(
            args.diario, args.mensual, args.anio,
            force=args.force, user_id=args.user_id,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print("Importación completada:")
    print(result.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
