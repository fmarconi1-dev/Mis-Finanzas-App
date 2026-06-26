"""Tests de las correcciones del premortem #3 (11/6/2026).

Cubre:
  * R3: regla dual aplicada en la comparativa Mensual (F6).
  * R4: KPIs anuales con datos de DOS años calendario (F3).
  * R2: retención de backups por edad, no por cantidad (F7).
  * R6: user_id sin DEFAULT — INSERT sin usuario falla ruidoso (F5)
        + aislamiento multi-tenant básico.
  * R9: tokens de sesión firmados (emisión, verificación, expiración, tamper).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from core import db as core_db
from core.budget import comparativa_mes
from core.db import init_db, connect, _purge_old_backups
from core.metrics import (
    anios_con_datos,
    compute_kpis,
    filtrar_anio,
    load_transactions,
)
from core.session_tokens import issue_token, tokens_enabled, verify_token


# ---------- Fixtures ----------

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


def _insert_cat(conn, motivo, grupo, sub=None, user_id=1):
    conn.execute(
        "INSERT INTO categorias (motivo, grupo, subcategoria, user_id) "
        "VALUES (?, ?, ?, ?)",
        (motivo, grupo, sub, user_id),
    )


def _insert_txn(conn, fecha, motivo, pasivos=0.0, ingresos=0.0, user_id=1):
    conn.execute(
        "INSERT INTO transacciones (fecha, pasivos, ingresos, motivo, user_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (fecha, pasivos, ingresos, motivo, user_id),
    )


# ---------- R3: regla dual en Mensual (F6) ----------

class TestComparativaMesRegladual:
    def _seed(self, conn):
        _insert_cat(conn, "Sueldo", "Ingreso", "Sueldo")
        _insert_cat(conn, "Compras", "Gasto Variable", "Consumo")
        _insert_cat(conn, "Inversiones", "Inversion", "Activos financieros")
        _insert_txn(conn, "2026-06-05", "Sueldo", ingresos=1_000_000)
        _insert_txn(conn, "2026-06-10", "Compras", pasivos=200_000)
        # Compra de activos (lado pasivo → Inversion).
        _insert_txn(conn, "2026-06-12", "Inversiones", pasivos=300_000)
        # VENTA de activos (lado ingreso → regla dual → Ingreso/Desahorro).
        _insert_txn(conn, "2026-06-20", "Inversiones", ingresos=450_000)
        conn.execute(
            "INSERT INTO presupuesto (motivo, anio, mes, monto_previsto, user_id) "
            "VALUES ('Inversiones', 2026, 6, 300000, 1)"
        )

    def test_venta_de_inversiones_aparece_como_ingreso(self, db):
        """El bug F6: la venta desaparecía de Mensual. Ahora debe aparecer."""
        self._seed(db)
        df = comparativa_mes(db, 2026, 6, user_id=1)

        fila_ingreso = df[(df["motivo"] == "Inversiones") & (df["grupo"] == "Ingreso")]
        assert len(fila_ingreso) == 1, "La venta de Inversiones debe figurar como Ingreso"
        assert fila_ingreso.iloc[0]["monto_real"] == pytest.approx(450_000)

    def test_lado_pasivo_sigue_en_inversion_con_su_prevision(self, db):
        self._seed(db)
        df = comparativa_mes(db, 2026, 6, user_id=1)

        fila_inv = df[(df["motivo"] == "Inversiones") & (df["grupo"] == "Inversion")]
        assert len(fila_inv) == 1
        assert fila_inv.iloc[0]["monto_real"] == pytest.approx(300_000)
        assert fila_inv.iloc[0]["monto_previsto"] == pytest.approx(300_000)

    def test_total_ingresos_incluye_el_desahorro(self, db):
        """Coherencia con el Dashboard: Ingreso total del mes = sueldo + venta."""
        self._seed(db)
        df = comparativa_mes(db, 2026, 6, user_id=1)
        total_ingreso = df.loc[df["grupo"] == "Ingreso", "monto_real"].sum()
        assert total_ingreso == pytest.approx(1_450_000)

    def test_motivos_no_duales_sin_cambios(self, db):
        self._seed(db)
        df = comparativa_mes(db, 2026, 6, user_id=1)
        compras = df[df["motivo"] == "Compras"]
        assert len(compras) == 1
        assert compras.iloc[0]["grupo"] == "Gasto Variable"
        assert compras.iloc[0]["monto_real"] == pytest.approx(200_000)


# ---------- R4: KPIs con dos años calendario (F3) ----------

class TestKpisDosAnios:
    def _df_dos_anios(self):
        cats = {
            "Sueldo": ("Ingreso", "Sueldo"),
            "Compras": ("Gasto Variable", "Consumo"),
        }
        rows = []
        # 2026: 12 meses de sueldo 100 + compras 40.
        for mes in range(1, 13):
            rows.append((f"2026-{mes:02d}-05", 0.0, 100.0, "Sueldo"))
            rows.append((f"2026-{mes:02d}-15", 40.0, 0.0, "Compras"))
        # 2027: 2 meses de sueldo 200 + compras 50.
        for mes in (1, 2):
            rows.append((f"2027-{mes:02d}-05", 0.0, 200.0, "Sueldo"))
            rows.append((f"2027-{mes:02d}-15", 50.0, 0.0, "Compras"))
        df = pd.DataFrame(rows, columns=["fecha", "pasivos", "ingresos", "motivo"])
        df["fecha"] = pd.to_datetime(df["fecha"])
        return df, cats

    def test_anios_con_datos(self):
        df, _ = self._df_dos_anios()
        assert anios_con_datos(df) == [2026, 2027]

    def test_kpis_2027_no_arrastran_2026(self):
        """El fix de la 'bomba de año nuevo': filtrado, enero-febrero 2027
        muestra SOLO 2027 (ingreso 400, no 1600)."""
        df, cats = self._df_dos_anios()
        k = compute_kpis(filtrar_anio(df, 2027), cats)
        assert k["ingreso_anual"] == pytest.approx(400.0)
        assert k["meses_cubiertos"] == 2
        assert k["ingreso_mes"] == pytest.approx(200.0)
        assert k["variable_anual"] == pytest.approx(100.0)

    def test_kpis_2026_intactos(self):
        df, cats = self._df_dos_anios()
        k = compute_kpis(filtrar_anio(df, 2026), cats)
        assert k["ingreso_anual"] == pytest.approx(1200.0)
        assert k["meses_cubiertos"] == 12

    def test_sin_filtro_demuestra_el_bug_original(self):
        """Documenta el comportamiento que motivó R4: sin filtrar, 'anual'
        mezcla los dos años."""
        df, cats = self._df_dos_anios()
        k = compute_kpis(df, cats)
        assert k["ingreso_anual"] == pytest.approx(1600.0)  # 2026 + 2027
        assert k["meses_cubiertos"] == 14


# ---------- R2: retención de backups por edad (F7) ----------

class TestPurgeBackupsPorEdad:
    def _mk_backups(self, dir: Path, specs: list[tuple[str, str]]):
        dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for dia, hora in specs:
            p = dir / f"finanzas-{dia}-{hora}.db"
            p.write_bytes(b"x")
            paths.append(p)
        return paths

    def test_rafaga_no_purga_dias_anteriores(self, tmp_path, monkeypatch):
        """El escenario del premortem: 30+ escrituras en una sesión NO deben
        borrar el último backup de días anteriores."""
        bdir = tmp_path / "backups"
        monkeypatch.setattr(core_db, "BACKUP_DIR", bdir)

        hoy = datetime.now()
        d0 = hoy.strftime("%Y%m%d")
        d1 = (hoy - timedelta(days=1)).strftime("%Y%m%d")
        d7 = (hoy - timedelta(days=7)).strftime("%Y%m%d")

        # 1 backup hace 7 días, 2 ayer, ráfaga de 40 hoy.
        specs = [(d7, "120000"), (d1, "090000"), (d1, "210000")]
        specs += [(d0, f"10{i:02d}00") for i in range(40)]
        self._mk_backups(bdir, specs)

        _purge_old_backups(retention_days=30, keep_recent=10)
        restantes = {p.name for p in bdir.glob("finanzas-*.db")}

        assert f"finanzas-{d7}-120000.db" in restantes        # día viejo sobrevive
        assert f"finanzas-{d1}-210000.db" in restantes        # último de ayer sobrevive
        assert f"finanzas-{d0}-103900.db" in restantes        # el más nuevo de hoy
        # Los 10 más recientes de la ráfaga se conservan; el resto de hoy no.
        de_hoy = [n for n in restantes if f"-{d0}-" in n]
        assert len(de_hoy) == 10

    def test_backups_fuera_de_ventana_se_purgan(self, tmp_path, monkeypatch):
        bdir = tmp_path / "backups"
        monkeypatch.setattr(core_db, "BACKUP_DIR", bdir)

        viejo = (datetime.now() - timedelta(days=45)).strftime("%Y%m%d")
        hoy = datetime.now().strftime("%Y%m%d")
        self._mk_backups(bdir, [(viejo, "120000")] + [(hoy, f"11{i:02d}00") for i in range(12)])

        _purge_old_backups(retention_days=30, keep_recent=10)
        restantes = {p.name for p in bdir.glob("finanzas-*.db")}
        assert f"finanzas-{viejo}-120000.db" not in restantes


# ---------- R6: user_id obligatorio + aislamiento (F5) ----------

class TestMultiTenant:
    def test_insert_sin_user_id_falla_ruidoso(self, db):
        """Post-M5: olvidar el user_id debe ser un error, no una fuga a id=1."""
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO transacciones (fecha, pasivos, ingresos, motivo) "
                "VALUES ('2026-06-01', 100, 0, 'Compras')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO categorias (motivo, grupo) VALUES ('X', 'Ingreso')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO configuracion (clave, valor) VALUES ('k', 'v')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO presupuesto (motivo, anio, mes, monto_previsto) "
                "VALUES ('X', 2026, 6, 100)"
            )

    def test_aislamiento_entre_usuarios(self, db):
        db.execute(
            "INSERT INTO usuarios (id, username) VALUES (2, 'otro')"
        )
        _insert_txn(db, "2026-06-01", "Compras", pasivos=100, user_id=1)
        _insert_txn(db, "2026-06-01", "Compras", pasivos=999, user_id=2)

        df1 = load_transactions(db, user_id=1)
        df2 = load_transactions(db, user_id=2)
        assert len(df1) == 1 and df1.iloc[0]["pasivos"] == pytest.approx(100)
        assert len(df2) == 1 and df2.iloc[0]["pasivos"] == pytest.approx(999)

    def test_migracion_preserva_datos_existentes(self, tmp_path, monkeypatch):
        """init_db corrido dos veces (con M5 de por medio) no pierde filas."""
        db_path = tmp_path / "f.db"
        monkeypatch.setenv("DB_PATH", str(db_path))
        init_db(db_path)
        with connect(db_path) as conn:
            _insert_txn(conn, "2026-06-01", "Compras", pasivos=100, user_id=1)
        init_db(db_path)  # re-correr migraciones: idempotente
        with connect(db_path) as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM transacciones").fetchone()["n"]
        assert n == 1


# ---------- R9: tokens de sesión ----------

class TestSessionTokens:
    SECRET = "secreto-de-prueba-no-usar-en-prod"

    def test_deshabilitado_sin_secret(self, monkeypatch):
        monkeypatch.delenv("SESSION_SECRET", raising=False)
        assert not tokens_enabled()
        assert issue_token(1) is None
        assert verify_token("cualquier.cosa") is None

    def test_roundtrip(self, monkeypatch):
        monkeypatch.setenv("SESSION_SECRET", self.SECRET)
        token = issue_token(42)
        assert token is not None
        assert verify_token(token) == 42

    def test_token_adulterado_rechazado(self, monkeypatch):
        monkeypatch.setenv("SESSION_SECRET", self.SECRET)
        token = issue_token(42)
        payload, sig = token.split(".")
        assert verify_token(payload + "x." + sig) is None
        assert verify_token(payload + "." + sig[:-2]) is None
        assert verify_token("basura") is None
        assert verify_token(None) is None

    def test_token_expirado_rechazado(self, monkeypatch):
        monkeypatch.setenv("SESSION_SECRET", self.SECRET)
        token = issue_token(42, ttl=-10)
        assert verify_token(token) is None

    def test_secret_distinto_invalida(self, monkeypatch):
        monkeypatch.setenv("SESSION_SECRET", self.SECRET)
        token = issue_token(42)
        monkeypatch.setenv("SESSION_SECRET", "otro-secret")
        assert verify_token(token) is None
