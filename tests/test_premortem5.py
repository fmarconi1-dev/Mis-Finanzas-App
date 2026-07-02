"""Tests del premortem #5 — Grupo familiar D1 (Shadow).

Verifica que la migración M6 deja los datos productivos en estado consistente:
las queries del `core/` siguen filtrando por `user_id`, pero la columna
`workspace_id` está backfilled de forma que para cada usuario, las filas con
`user_id = u.id` son exactamente las mismas que las filas con
`workspace_id = workspace_personal_de(u)`.

Si CUALQUIERA de estos tests falla, **NO HACER CUTOVER M7**.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.db import _migrate, init_db


# ---------- Helpers ----------

def _crear_schema_legacy(conn: sqlite3.Connection) -> None:
    """Crea un schema previo a M6 (con user_id, sin workspace_id).

    Replica el estado de una DB productiva post-M5. Útil para simular que la
    migración M6 corre sobre datos existentes (caso de Franco).
    """
    c = conn.cursor()
    c.execute("""
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            fullname TEXT,
            creado_en TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            pasivos REAL NOT NULL DEFAULT 0,
            ingresos REAL NOT NULL DEFAULT 0,
            motivo TEXT NOT NULL,
            comentario TEXT,
            creado_en TEXT NOT NULL DEFAULT (datetime('now')),
            user_id INTEGER NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE categorias (
            motivo TEXT NOT NULL,
            grupo TEXT NOT NULL CHECK (grupo IN (
                'Ingreso', 'Gasto Fijo', 'Gasto Variable', 'Inversion',
                'Flujo Capital', 'Saldo Inicial', 'Sin categorizar'
            )),
            subcategoria TEXT,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (motivo, user_id)
        )
    """)
    c.execute("""
        CREATE TABLE presupuesto (
            motivo TEXT NOT NULL,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
            monto_previsto REAL NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (motivo, anio, mes, user_id)
        )
    """)
    c.execute("""
        CREATE TABLE configuracion (
            clave TEXT NOT NULL,
            valor TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (clave, user_id)
        )
    """)
    conn.commit()


def _sembrar_dos_usuarios(conn: sqlite3.Connection) -> None:
    """Siembra Franco (user_id=1) con data + Mamá (user_id=2) con data distinta.

    Replica la situación productiva: Franco ya tiene 165 transacciones, hay
    una segunda cuenta también con data. La migración tiene que separar
    correctamente los workspaces personales sin mezclar nada.
    """
    c = conn.cursor()
    # Usuarios
    c.execute(
        "INSERT INTO usuarios (id, username, fullname) VALUES (1, 'franco', 'Franco Marconi')"
    )
    c.execute(
        "INSERT INTO usuarios (id, username, fullname) VALUES (2, 'mama', 'Mamá Test')"
    )
    # Configuración por usuario (saldo + fondo)
    c.execute(
        "INSERT INTO configuracion (clave, valor, user_id) "
        "VALUES ('saldo_inicial_caja', '101515.65', 1)"
    )
    c.execute(
        "INSERT INTO configuracion (clave, valor, user_id) "
        "VALUES ('fondo_emergencia_usd', '864', 1)"
    )
    c.execute(
        "INSERT INTO configuracion (clave, valor, user_id) "
        "VALUES ('saldo_inicial_caja', '50000', 2)"
    )
    # 3 transacciones de Franco
    for fecha, motivo, ing, pas in [
        ("2026-01-15", "Sueldo", 500000, 0),
        ("2026-01-20", "Compras", 0, 8500),
        ("2026-02-01", "Salidas", 0, 12000),
    ]:
        c.execute(
            "INSERT INTO transacciones (fecha, motivo, ingresos, pasivos, user_id) "
            "VALUES (?, ?, ?, ?, 1)",
            (fecha, motivo, ing, pas),
        )
    # 2 transacciones de Mamá
    for fecha, motivo, ing, pas in [
        ("2026-01-10", "Sueldo", 300000, 0),
        ("2026-01-25", "Supermercado", 0, 15000),
    ]:
        c.execute(
            "INSERT INTO transacciones (fecha, motivo, ingresos, pasivos, user_id) "
            "VALUES (?, ?, ?, ?, 2)",
            (fecha, motivo, ing, pas),
        )
    # Categorías de cada uno
    c.execute(
        "INSERT INTO categorias (motivo, grupo, user_id) "
        "VALUES ('Sueldo', 'Ingreso', 1)"
    )
    c.execute(
        "INSERT INTO categorias (motivo, grupo, user_id) "
        "VALUES ('Compras', 'Gasto Variable', 1)"
    )
    c.execute(
        "INSERT INTO categorias (motivo, grupo, user_id) "
        "VALUES ('Sueldo', 'Ingreso', 2)"
    )
    # Presupuesto solo para Franco
    c.execute(
        "INSERT INTO presupuesto (motivo, anio, mes, monto_previsto, user_id) "
        "VALUES ('Compras', 2026, 1, 100000, 1)"
    )
    conn.commit()


# ---------- Fixtures ----------

@pytest.fixture
def db_legacy(tmp_path):
    """Crea una DB legacy (sin M6) con dos usuarios y data, lista para migrar."""
    db_path = tmp_path / "test_m6.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _crear_schema_legacy(conn)
    _sembrar_dos_usuarios(conn)
    yield conn, db_path
    conn.close()


# ---------- Tests ----------

class TestM6CreaInfraestructura:
    """Las tablas y columnas nuevas se crean correctamente."""

    def test_crea_tabla_workspaces(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(workspaces)")]
        assert "id" in cols
        assert "kind" in cols
        assert "nombre" in cols
        assert "invitation_code_hash" in cols
        assert "saldo_inicial" in cols
        assert "fondo_usd" in cols

    def test_crea_tabla_workspace_members(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(workspace_members)")]
        assert "workspace_id" in cols
        assert "user_id" in cols
        assert "role" in cols
        assert "member_label" in cols

    def test_agrega_columna_workspace_id_a_las_4_tablas(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        for tabla in ("transacciones", "categorias", "presupuesto", "configuracion"):
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})")]
            assert "workspace_id" in cols, f"falta workspace_id en {tabla}"

    def test_agrega_columna_creado_por_member_label_en_transacciones(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(transacciones)")]
        assert "creado_por_member_label" in cols


class TestM6BackfillCorrecto:
    """El backfill asigna workspace_id correctamente sin mezclar usuarios."""

    def test_cada_usuario_recibe_su_workspace_personal(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        # Cada usuario tiene exactamente 1 workspace personal asociado
        for user_id in (1, 2):
            rows = conn.execute("""
                SELECT w.id FROM workspaces w
                JOIN workspace_members wm ON wm.workspace_id = w.id
                WHERE wm.user_id = ? AND w.kind = 'personal'
            """, (user_id,)).fetchall()
            assert len(rows) == 1, f"user {user_id}: esperado 1 workspace personal, hay {len(rows)}"

    def test_workspace_personal_de_franco_tiene_su_saldo_y_fondo(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        row = conn.execute("""
            SELECT w.saldo_inicial, w.fondo_usd FROM workspaces w
            JOIN workspace_members wm ON wm.workspace_id = w.id
            WHERE wm.user_id = 1 AND w.kind = 'personal'
        """).fetchone()
        assert row is not None
        assert abs(row["saldo_inicial"] - 101515.65) < 0.01
        assert abs(row["fondo_usd"] - 864.0) < 0.01

    def test_member_label_es_fullname(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        labels = {
            r["user_id"]: r["member_label"]
            for r in conn.execute(
                "SELECT user_id, member_label FROM workspace_members"
            )
        }
        assert labels[1] == "Franco Marconi"
        assert labels[2] == "Mamá Test"

    def test_invariante_count_transacciones(self, db_legacy):
        """Para cada user, COUNT(transacciones por user_id) == COUNT por workspace_id."""
        conn, _ = db_legacy
        _migrate(conn)
        for user_id in (1, 2):
            ws_id = conn.execute("""
                SELECT w.id FROM workspaces w
                JOIN workspace_members wm ON wm.workspace_id = w.id
                WHERE wm.user_id = ? AND w.kind = 'personal'
            """, (user_id,)).fetchone()["id"]

            n_by_user = conn.execute(
                "SELECT COUNT(*) AS n FROM transacciones WHERE user_id = ?",
                (user_id,),
            ).fetchone()["n"]
            n_by_ws = conn.execute(
                "SELECT COUNT(*) AS n FROM transacciones WHERE workspace_id = ?",
                (ws_id,),
            ).fetchone()["n"]
            assert n_by_user == n_by_ws, (
                f"user {user_id}: COUNT por user_id={n_by_user} != "
                f"COUNT por workspace_id={n_by_ws}"
            )

    def test_invariante_count_todas_las_tablas(self, db_legacy):
        """Mismo invariante para categorias, presupuesto, configuracion."""
        conn, _ = db_legacy
        _migrate(conn)
        for user_id in (1, 2):
            ws_id_row = conn.execute("""
                SELECT w.id FROM workspaces w
                JOIN workspace_members wm ON wm.workspace_id = w.id
                WHERE wm.user_id = ? AND w.kind = 'personal'
            """, (user_id,)).fetchone()
            if ws_id_row is None:
                continue
            ws_id = ws_id_row["id"]
            for tabla in ("categorias", "presupuesto", "configuracion"):
                n_by_user = conn.execute(
                    f"SELECT COUNT(*) AS n FROM {tabla} WHERE user_id = ?",
                    (user_id,),
                ).fetchone()["n"]
                n_by_ws = conn.execute(
                    f"SELECT COUNT(*) AS n FROM {tabla} WHERE workspace_id = ?",
                    (ws_id,),
                ).fetchone()["n"]
                assert n_by_user == n_by_ws, (
                    f"{tabla} user={user_id}: COUNT user_id={n_by_user} != "
                    f"COUNT workspace_id={n_by_ws}"
                )

    def test_no_hay_data_huerfana(self, db_legacy):
        """Ninguna fila legacy queda sin workspace_id después del backfill."""
        conn, _ = db_legacy
        _migrate(conn)
        for tabla in ("transacciones", "categorias", "presupuesto", "configuracion"):
            huerfanas = conn.execute(
                f"SELECT COUNT(*) AS n FROM {tabla} WHERE workspace_id IS NULL"
            ).fetchone()["n"]
            assert huerfanas == 0, f"{tabla}: {huerfanas} filas sin workspace_id"


class TestM6Idempotente:
    """Correr M6 dos veces no duplica nada (caso típico: redeploy)."""

    def test_correr_dos_veces_no_duplica_workspaces(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        ws_antes = conn.execute("SELECT COUNT(*) AS n FROM workspaces").fetchone()["n"]
        _migrate(conn)
        ws_despues = conn.execute("SELECT COUNT(*) AS n FROM workspaces").fetchone()["n"]
        assert ws_antes == ws_despues, "M6 duplicó workspaces al correrse 2 veces"

    def test_correr_dos_veces_no_duplica_members(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        m_antes = conn.execute("SELECT COUNT(*) AS n FROM workspace_members").fetchone()["n"]
        _migrate(conn)
        m_despues = conn.execute("SELECT COUNT(*) AS n FROM workspace_members").fetchone()["n"]
        assert m_antes == m_despues, "M6 duplicó members al correrse 2 veces"


class TestM6ConstraintsActivos:
    """CHECK / UNIQUE / FK constraints disparan correctamente."""

    def test_kind_invalido_es_rechazado(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO workspaces (kind, nombre) VALUES ('invalido', 'x')"
            )

    def test_member_label_duplicado_es_rechazado(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        # Tomo el workspace de Franco
        ws_id = conn.execute("""
            SELECT w.id FROM workspaces w
            JOIN workspace_members wm ON wm.workspace_id = w.id
            WHERE wm.user_id = 1 AND w.kind = 'personal'
        """).fetchone()["id"]
        # Intento insertar otro miembro con la misma label
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO workspace_members "
                "(workspace_id, user_id, member_label) VALUES (?, 2, 'Franco Marconi')",
                (ws_id,),
            )

    def test_role_invalido_es_rechazado(self, db_legacy):
        conn, _ = db_legacy
        _migrate(conn)
        ws_id = conn.execute("""
            SELECT w.id FROM workspaces w
            JOIN workspace_members wm ON wm.workspace_id = w.id
            WHERE wm.user_id = 1 AND w.kind = 'personal'
        """).fetchone()["id"]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO workspace_members "
                "(workspace_id, user_id, role, member_label) "
                "VALUES (?, 2, 'super', 'X')",
                (ws_id,),
            )
