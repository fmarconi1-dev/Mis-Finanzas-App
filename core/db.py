"""Conexión a SQLite y schema.

Decisiones de diseño:

  * Usamos `sqlite3` de la stdlib (sin SQLAlchemy) para minimizar dependencias.
  * Modo WAL: permite lectores concurrentes mientras un proceso escribe.
    Importante para Streamlit, que mantiene la DB abierta en sesiones.
  * El saldo de Caja NO se almacena. Se calcula como acumulado:
        saldo_inicial + SUM(ingresos - pasivos) ORDER BY fecha, id
    Así la app es siempre auto-consistente: no hay forma de que la DB tenga
    un Caja "stale" porque no existe la columna.
  * El schema es idempotente: `init_db()` se puede correr N veces sin perder
    datos. Si una migración futura agrega columnas, lo manejamos con `ALTER TABLE`
    condicional (todavía no es necesario).
"""

from __future__ import annotations

import os
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from core.current_user import require_current_user_id

DEFAULT_DB_PATH = Path("data/finanzas.db")
BACKUP_DIR = Path("data/backups")


# ---------- Schema ----------

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS transacciones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT NOT NULL,                    -- ISO 'YYYY-MM-DD'
    pasivos     REAL NOT NULL DEFAULT 0,          -- egresos (positivo); negativo = devolución
    ingresos    REAL NOT NULL DEFAULT 0,
    motivo      TEXT NOT NULL,
    comentario  TEXT,
    creado_en   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transacciones_fecha
    ON transacciones(fecha);

CREATE INDEX IF NOT EXISTS idx_transacciones_motivo
    ON transacciones(motivo);

CREATE TABLE IF NOT EXISTS categorias (
    motivo  TEXT PRIMARY KEY,
    grupo   TEXT NOT NULL
        CHECK (grupo IN (
            'Ingreso',
            'Gasto Fijo',
            'Gasto Variable',
            'Inversion',
            'Flujo Capital',
            'Saldo Inicial',
            'Sin categorizar'
        ))
);

CREATE TABLE IF NOT EXISTS presupuesto (
    motivo         TEXT NOT NULL,
    anio           INTEGER NOT NULL,
    mes            INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    monto_previsto REAL NOT NULL,
    PRIMARY KEY (motivo, anio, mes)
);

CREATE TABLE IF NOT EXISTS configuracion (
    clave  TEXT PRIMARY KEY,
    valor  TEXT NOT NULL
);

-- Multi-usuario: por ahora hay un único usuario "local" con id=1.
-- En Fase 3, login con Streamlit-Authenticator setea current_user_id.
CREATE TABLE IF NOT EXISTS usuarios (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT UNIQUE NOT NULL,
    password_hash  TEXT,                          -- NULL hasta Fase 3
    fullname       TEXT,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# Tablas que en Fase 3 van a filtrarse por current_user_id.
_USER_SCOPED_TABLES = ("transacciones", "categorias", "presupuesto", "configuracion")


def _migrate(conn: sqlite3.Connection) -> None:
    """Migraciones idempotentes. Se corren después de crear el schema base.

    Migraciones actuales:
      M1 (Fase 2): user_id en tablas de datos + usuario local.
      M2 (Fase 2b): columna `subcategoria` en `categorias` para jerarquía
                    macro/sub (ej: Inversion → Ahorro vs Activos financieros).
    """
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        # M1: user_id.
        for tabla in _USER_SCOPED_TABLES:
            cols = [
                r["name"] for r in cur.execute(f"PRAGMA table_info({tabla})")
            ]
            if "user_id" not in cols:
                cur.execute(
                    f"ALTER TABLE {tabla} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1"
                )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{tabla}_user ON {tabla}(user_id)"
            )
        cur.execute(
            "INSERT OR IGNORE INTO usuarios (id, username, fullname) "
            "VALUES (1, 'local', 'Usuario local')"
        )

        # M2: subcategoria en categorias.
        cat_cols = [r["name"] for r in cur.execute("PRAGMA table_info(categorias)")]
        if "subcategoria" not in cat_cols:
            cur.execute("ALTER TABLE categorias ADD COLUMN subcategoria TEXT")

        # M3: reclasificación de Fase 2b.
        #   * Compra Divisa: "Gasto Variable" → "Inversion / Ahorro y Resguardo".
        #   * Venta divisa: "Ingreso" sin subcat → "Ingreso / Desahorro".
        cur.execute(
            "UPDATE categorias SET grupo = 'Inversion', subcategoria = 'Ahorro y Resguardo' "
            "WHERE motivo = 'Compra Divisa' AND grupo = 'Gasto Variable'"
        )
        cur.execute(
            "UPDATE categorias SET subcategoria = 'Desahorro' "
            "WHERE motivo = 'Venta divisa' AND grupo = 'Ingreso' AND "
            "      (subcategoria IS NULL OR subcategoria = '')"
        )

        # M4 (Fase 3): PKs compuestas con user_id en categorias, presupuesto y
        # configuracion. SQLite no permite alterar PK, así que recreamos cada
        # tabla preservando los datos.
        def _pk_has_user_id(table: str) -> bool:
            info = cur.execute(f"PRAGMA table_info({table})").fetchall()
            return any(r["name"] == "user_id" and r["pk"] > 0 for r in info)

        if not _pk_has_user_id("categorias"):
            cur.execute("""
                CREATE TABLE categorias_new (
                    motivo        TEXT NOT NULL,
                    grupo         TEXT NOT NULL CHECK (grupo IN (
                        'Ingreso', 'Gasto Fijo', 'Gasto Variable', 'Inversion',
                        'Flujo Capital', 'Saldo Inicial', 'Sin categorizar'
                    )),
                    subcategoria  TEXT,
                    user_id       INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (motivo, user_id)
                )
            """)
            cur.execute(
                "INSERT INTO categorias_new (motivo, grupo, subcategoria, user_id) "
                "SELECT motivo, grupo, subcategoria, user_id FROM categorias"
            )
            cur.execute("DROP TABLE categorias")
            cur.execute("ALTER TABLE categorias_new RENAME TO categorias")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_categorias_user ON categorias(user_id)"
            )

        if not _pk_has_user_id("presupuesto"):
            cur.execute("""
                CREATE TABLE presupuesto_new (
                    motivo         TEXT NOT NULL,
                    anio           INTEGER NOT NULL,
                    mes            INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
                    monto_previsto REAL NOT NULL,
                    user_id        INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (motivo, anio, mes, user_id)
                )
            """)
            cur.execute(
                "INSERT INTO presupuesto_new (motivo, anio, mes, monto_previsto, user_id) "
                "SELECT motivo, anio, mes, monto_previsto, user_id FROM presupuesto"
            )
            cur.execute("DROP TABLE presupuesto")
            cur.execute("ALTER TABLE presupuesto_new RENAME TO presupuesto")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_presupuesto_user ON presupuesto(user_id)"
            )

        if not _pk_has_user_id("configuracion"):
            cur.execute("""
                CREATE TABLE configuracion_new (
                    clave   TEXT NOT NULL,
                    valor   TEXT NOT NULL,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (clave, user_id)
                )
            """)
            cur.execute(
                "INSERT INTO configuracion_new (clave, valor, user_id) "
                "SELECT clave, valor, user_id FROM configuracion"
            )
            cur.execute("DROP TABLE configuracion")
            cur.execute("ALTER TABLE configuracion_new RENAME TO configuracion")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_configuracion_user ON configuracion(user_id)"
            )

        # M5 (premortem #3, F5/R6): quitar el DEFAULT 1 de user_id en TODAS
        # las tablas de datos. Con DEFAULT 1, cualquier INSERT futuro que
        # olvide el user_id (un callback sin contextvar, un script, el
        # chatbot) deposita datos SILENCIOSAMENTE en la cuenta id=1 (Franco).
        # Sin default, ese INSERT lanza IntegrityError: falla ruidoso > fuga
        # silenciosa. SQLite no permite alterar el default → rebuild.
        def _user_id_con_default(table: str) -> bool:
            info = cur.execute(f"PRAGMA table_info({table})").fetchall()
            return any(
                r["name"] == "user_id" and r["dflt_value"] is not None
                for r in info
            )

        if _user_id_con_default("transacciones"):
            cur.execute("""
                CREATE TABLE transacciones_m5 (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha       TEXT NOT NULL,
                    pasivos     REAL NOT NULL DEFAULT 0,
                    ingresos    REAL NOT NULL DEFAULT 0,
                    motivo      TEXT NOT NULL,
                    comentario  TEXT,
                    creado_en   TEXT NOT NULL DEFAULT (datetime('now')),
                    user_id     INTEGER NOT NULL
                )
            """)
            cur.execute(
                "INSERT INTO transacciones_m5 "
                "(id, fecha, pasivos, ingresos, motivo, comentario, creado_en, user_id) "
                "SELECT id, fecha, pasivos, ingresos, motivo, comentario, creado_en, user_id "
                "FROM transacciones"
            )
            cur.execute("DROP TABLE transacciones")
            cur.execute("ALTER TABLE transacciones_m5 RENAME TO transacciones")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_transacciones_fecha ON transacciones(fecha)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_transacciones_motivo ON transacciones(motivo)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_transacciones_user ON transacciones(user_id)"
            )

        if _user_id_con_default("categorias"):
            cur.execute("""
                CREATE TABLE categorias_m5 (
                    motivo        TEXT NOT NULL,
                    grupo         TEXT NOT NULL CHECK (grupo IN (
                        'Ingreso', 'Gasto Fijo', 'Gasto Variable', 'Inversion',
                        'Flujo Capital', 'Saldo Inicial', 'Sin categorizar'
                    )),
                    subcategoria  TEXT,
                    user_id       INTEGER NOT NULL,
                    PRIMARY KEY (motivo, user_id)
                )
            """)
            cur.execute(
                "INSERT INTO categorias_m5 (motivo, grupo, subcategoria, user_id) "
                "SELECT motivo, grupo, subcategoria, user_id FROM categorias"
            )
            cur.execute("DROP TABLE categorias")
            cur.execute("ALTER TABLE categorias_m5 RENAME TO categorias")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_categorias_user ON categorias(user_id)"
            )

        if _user_id_con_default("presupuesto"):
            cur.execute("""
                CREATE TABLE presupuesto_m5 (
                    motivo         TEXT NOT NULL,
                    anio           INTEGER NOT NULL,
                    mes            INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
                    monto_previsto REAL NOT NULL,
                    user_id        INTEGER NOT NULL,
                    PRIMARY KEY (motivo, anio, mes, user_id)
                )
            """)
            cur.execute(
                "INSERT INTO presupuesto_m5 (motivo, anio, mes, monto_previsto, user_id) "
                "SELECT motivo, anio, mes, monto_previsto, user_id FROM presupuesto"
            )
            cur.execute("DROP TABLE presupuesto")
            cur.execute("ALTER TABLE presupuesto_m5 RENAME TO presupuesto")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_presupuesto_user ON presupuesto(user_id)"
            )

        if _user_id_con_default("configuracion"):
            cur.execute("""
                CREATE TABLE configuracion_m5 (
                    clave   TEXT NOT NULL,
                    valor   TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    PRIMARY KEY (clave, user_id)
                )
            """)
            cur.execute(
                "INSERT INTO configuracion_m5 (clave, valor, user_id) "
                "SELECT clave, valor, user_id FROM configuracion"
            )
            cur.execute("DROP TABLE configuracion")
            cur.execute("ALTER TABLE configuracion_m5 RENAME TO configuracion")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_configuracion_user ON configuracion(user_id)"
            )

        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise


def get_db_path() -> Path:
    """Lee la ruta a la DB del entorno o usa el default."""
    raw = os.environ.get("DB_PATH", str(DEFAULT_DB_PATH))
    return Path(raw)


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Abre una conexión SQLite con row_factory configurado para acceso por nombre."""
    path = Path(db_path) if db_path is not None else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit-friendly
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Crea el schema si no existe y corre migraciones pendientes. Idempotente."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


# ---------- Configuración (clave/valor) ----------

def _resolve_user_id(user_id: Optional[int]) -> int:
    """Si user_id es None, lo toma del contextvar. Si no hay contexto, error."""
    if user_id is not None:
        return user_id
    return require_current_user_id()


def set_config(
    conn: sqlite3.Connection,
    clave: str,
    valor: str,
    user_id: Optional[int] = None,
) -> None:
    uid = _resolve_user_id(user_id)
    conn.execute(
        "INSERT INTO configuracion (clave, valor, user_id) VALUES (?, ?, ?) "
        "ON CONFLICT(clave, user_id) DO UPDATE SET valor = excluded.valor",
        (clave, valor, uid),
    )


def get_config(
    conn: sqlite3.Connection,
    clave: str,
    default: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[str]:
    uid = _resolve_user_id(user_id)
    row = conn.execute(
        "SELECT valor FROM configuracion WHERE clave = ? AND user_id = ?",
        (clave, uid),
    ).fetchone()
    return row["valor"] if row else default


# ---------- Backups ----------

def backup_db(
    db_path: Optional[Path] = None,
    retention_days: int = 30,
    keep_recent: int = 10,
) -> Path:
    """Copia la DB a `data/backups/finanzas-YYYYMMDD-HHMMSS.db` y purga viejos.

    Se invoca tras cada escritura desde la UI. Es deliberadamente síncrono
    y barato (el archivo SQLite de finanzas personales pesará pocos MB).

    Retención (premortem #3, R2): por EDAD, no por cantidad. Una sesión
    intensa de carga ya no purga el historial: se conservan los últimos
    `keep_recent` backups inmediatos + el ÚLTIMO backup de cada día de los
    últimos `retention_days` días. Ventana de recuperación real: ~30 días.
    """
    src = Path(db_path) if db_path is not None else get_db_path()
    if not src.exists():
        raise FileNotFoundError(f"No se puede backupear; la DB no existe en {src}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"finanzas-{timestamp}.db"
    # Usamos el API nativo de SQLite (no shutil.copy) para garantizar consistencia
    # incluso si hay otra conexión escribiendo.
    with connect(src) as src_conn, sqlite3.connect(str(dest)) as dest_conn:
        src_conn.backup(dest_conn)

    _purge_old_backups(retention_days=retention_days, keep_recent=keep_recent)
    return dest


def _purge_old_backups(retention_days: int = 30, keep_recent: int = 10) -> None:
    """Purga por edad: conserva los `keep_recent` más nuevos + el último
    backup de cada día dentro de la ventana de `retention_days` días.

    El nombre `finanzas-YYYYMMDD-HHMMSS.db` ordena cronológicamente por
    string, así que `sorted()` alcanza.
    """
    backups = sorted(BACKUP_DIR.glob("finanzas-*.db"))
    if not backups:
        return

    keep: set[Path] = set(backups[-keep_recent:]) if keep_recent > 0 else set()

    # Último backup de cada día (sorted asc → el último sobrescribe).
    prefix_len = len("finanzas-")
    ultimo_por_dia: dict[str, Path] = {}
    for b in backups:
        dia = b.name[prefix_len:prefix_len + 8]  # YYYYMMDD
        ultimo_por_dia[dia] = b

    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y%m%d")
    for dia, b in ultimo_por_dia.items():
        if dia >= cutoff:
            keep.add(b)

    for old in backups:
        if old in keep:
            continue
        try:
            old.unlink()
        except OSError:
            # No es crítico; el siguiente backup volverá a intentar.
            pass
