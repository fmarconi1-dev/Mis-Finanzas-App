"""Regresión del TypeError de backup_db (3/7/2026).

El 2/7, al reconstruir core/db.py tras una corrupción de OneDrive, la firma
de backup_db() quedó exigiendo `conn` — pero los 9 call sites de core/
(transactions, budget, categorias) la llaman SIN argumentos. Resultado:
toda escritura en producción crasheaba con TypeError y no se generaba
ningún backup. Los 94 tests estaban verdes porque ninguno pasaba por
backup_db. Estos tests cierran ese agujero: si la firma vuelve a cambiar,
esto rompe.
"""

from __future__ import annotations

from datetime import date

import pytest

from core import db as core_db
from core.db import backup_db, connect, init_db
from core.transactions import insert_transaction


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """DB temporal inicializada, con DB_PATH y BACKUP_DIR aislados."""
    db_path = tmp_path / "finanzas.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setattr(core_db, "BACKUP_DIR", tmp_path / "backups")
    init_db(db_path)
    conn = connect(db_path)
    yield conn
    conn.close()


def test_backup_db_sin_argumentos(db):
    """backup_db() a secas — como la llama todo core/ — tiene que funcionar."""
    dest = backup_db()
    assert dest.exists()
    assert dest.name.startswith("finanzas-")


def test_backup_db_con_conn_explicita(db):
    """La forma con conn explícita también sigue siendo válida."""
    dest = backup_db(db)
    assert dest.exists()


def test_insert_transaction_dispara_backup(db):
    """El flujo real de alta: INSERT + backup, sin TypeError.

    Este es exactamente el path que crasheaba en producción al agregar
    un gasto desde la UI.
    """
    new_id = insert_transaction(
        db, fecha=date(2026, 7, 3), motivo="Test regresion",
        pasivos=100.0, user_id=1,
    )
    assert new_id > 0
    backups = list(core_db.BACKUP_DIR.glob("finanzas-*.db"))
    assert backups, "insert_transaction tiene que dejar un backup"
