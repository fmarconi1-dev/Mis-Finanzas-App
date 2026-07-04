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

        # ============================================================
        # M6 (premortem #5, SHADOW): infraestructura para workspaces.
        # ============================================================
        # Modelo: cada usuario tiene un workspace personal (kind='personal')
        # creado automáticamente acá. Puede tener además uno o más workspaces
        # familiares (kind='familiar') compartidos con otros usuarios vía
        # código de invitación.
        #
        # Esta migración SOLO agrega infraestructura (tablas + columnas +
        # backfill). Las queries del `core/` siguen filtrando por `user_id`
        # — el cutover a `workspace_id` viene en M7. Esto permite deployar el
        # cambio sin tocar comportamiento y validar que la data quedó bien
        # antes del cutover.
        #
        # Invariante de la migración (verificada en tests/test_premortem5.py):
        #   ∀ usuario u, ∀ tabla T ∈ {transacciones, categorias, presupuesto,
        #                              configuracion}:
        #     COUNT(T WHERE user_id = u) ==
        #     COUNT(T WHERE workspace_id = workspace_personal_de(u))

        # 6.1: tablas nuevas.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('personal', 'familiar')),
                nombre TEXT NOT NULL,
                invitation_code_hash TEXT,
                saldo_inicial REAL NOT NULL DEFAULT 0,
                fondo_usd REAL NOT NULL DEFAULT 0,
                creado_en TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workspace_members (
                workspace_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin' CHECK(role IN ('admin', 'viewer')),
                member_label TEXT NOT NULL,
                joined_en TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (workspace_id, user_id),
                UNIQUE (workspace_id, member_label),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_members_user ON workspace_members(user_id)"
        )

        # 6.2: columna workspace_id (nullable durante shadow) en las 4 tablas.
        for tabla in ("transacciones", "categorias", "presupuesto", "configuracion"):
            cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({tabla})")]
            if "workspace_id" not in cols:
                cur.execute(
                    f"ALTER TABLE {tabla} ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id)"
                )
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{tabla}_workspace ON {tabla}(workspace_id)"
                )

        # 6.3: columna creado_por_member_label en transacciones (auditoría
        # cosmética: dentro de un workspace familiar, qué miembro la cargó).
        trans_cols = [r["name"] for r in cur.execute("PRAGMA table_info(transacciones)")]
        if "creado_por_member_label" not in trans_cols:
            cur.execute("ALTER TABLE transacciones ADD COLUMN creado_por_member_label TEXT")

        # 6.4: backfill — por cada usuario sin workspace personal, crear uno
        # con el saldo + fondo USD actuales, y asociarlo como admin con
        # member_label = fullname (o username si no hay fullname).
        usuarios_sin_personal = cur.execute("""
            SELECT u.id, u.username, u.fullname
            FROM usuarios u
            WHERE NOT EXISTS (
                SELECT 1 FROM workspace_members wm
                JOIN workspaces w ON w.id = wm.workspace_id
                WHERE wm.user_id = u.id AND w.kind = 'personal'
            )
        """).fetchall()

        for u in usuarios_sin_personal:
            row_saldo = cur.execute(
                "SELECT valor FROM configuracion "
                "WHERE clave = 'saldo_inicial_caja' AND user_id = ?",
                (u["id"],),
            ).fetchone()
            row_fondo = cur.execute(
                "SELECT valor FROM configuracion "
                "WHERE clave = 'fondo_emergencia_usd' AND user_id = ?",
                (u["id"],),
            ).fetchone()
            try:
                saldo = float(row_saldo["valor"]) if row_saldo else 0.0
            except (ValueError, TypeError):
                saldo = 0.0
            try:
                fondo = float(row_fondo["valor"]) if row_fondo else 0.0
            except (ValueError, TypeError):
                fondo = 0.0

            nombre_ws = f"Personal de {u['fullname'] or u['username']}"
            cur.execute(
                "INSERT INTO workspaces (kind, nombre, saldo_inicial, fondo_usd) "
                "VALUES ('personal', ?, ?, ?)",
                (nombre_ws, saldo, fondo),
            )
            ws_id = cur.lastrowid
            member_label = u["fullname"] or u["username"]
            cur.execute(
                "INSERT INTO workspace_members "
                "(workspace_id, user_id, role, member_label) "
                "VALUES (?, ?, 'admin', ?)",
                (ws_id, u["id"], member_label),
            )

            for tabla in ("transacciones", "categorias", "presupuesto", "configuracion"):
                cur.execute(
                    f"UPDATE {tabla} SET workspace_id = ? "
                    f"WHERE user_id = ? AND workspace_id IS NULL",
                    (ws_id, u["id"]),
                )

        # ============================================================
        # M7: subcategorías canonical para los motivos default.
        # ============================================================
        # Backfill idempotente: solo actualiza filas con subcategoria NULL
        # o vacía. NO pisa subcategorías puestas manualmente por el usuario.
        # Cubre los motivos que vienen en `DEFAULT_CATEGORIAS_NEW_USER` y
        # `DEFAULT_CATEGORIAS` de `core/categorizer.py`.
        _default_subcats = {
            "Haberes Fundación":  "Sueldo",
            "Haberes SBT":        "Sueldo",
            "Haberes UCEMA":      "Sueldo",
            "Sueldo":             "Sueldo",
            "Otros ingresos":     "Otros",
            "Venta divisa":       "Desahorro",
            "Retiro Inversiones": "Desahorro",
            "Auto":               "Movilidad",
            "Transportes":        "Movilidad",
            "Expensas":           "Hogar",
            "Servicios":          "Hogar",
            "Impuestos":          "Impuestos",
            "Pago tarjeta":       "Financiero",
            "Compras":            "Consumo",
            "Supermercado":       "Consumo",
            "Salidas":            "Ocio",
            "Viajes":             "Ocio",
            "Inversiones":        "Activos financieros",
            "Compra Divisa":      "Ahorro y Resguardo",
        }
        for motivo, subcat in _default_subcats.items():
            cur.execute(
                "UPDATE categorias SET subcategoria = ? "
                "WHERE motivo = ? "
                "AND (subcategoria IS NULL OR subcategoria = '')",
                (subcat, motivo),
            )

        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise


# ============================================================
#  Conexión y init
# ============================================================

def get_db_path() -> Path:
    """Ruta a la DB activa: respeta `DB_PATH` (env) o usa el default."""
    return Path(os.environ.get("DB_PATH", str(DEFAULT_DB_PATH)))


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Abrir una conexión SQLite con row_factory, WAL y FKs activos.

    `isolation_level=None` deshabilita el autocommit implícito del driver:
    así los `BEGIN`/`COMMIT`/`ROLLBACK` que escribimos en el código (ej.
    `core/ingest.py`, `_migrate()`) funcionan tal como están escritos. Sin
    esto, el driver intercala transacciones implícitas y rompe el control
    manual.
    """
    path = Path(db_path) if db_path is not None else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Crear schema base si no existe + correr migraciones idempotentes."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _resolve_user_id(user_id: Optional[int]) -> int:
    """Resuelve user_id explícito o lo lee del contextvar."""
    return user_id if user_id is not None else require_current_user_id()


def set_config(
    conn: sqlite3.Connection,
    clave: str,
    valor: str,
    user_id: Optional[int] = None,
) -> None:
    """UPSERT en `configuracion` filtrando por (clave, user_id).

    NO hace commit — eso queda a cargo del caller. Importante para no romper
    transacciones externas (caso típico: `core/ingest.py` que hace BEGIN/COMMIT
    explícito alrededor del bulk insert + set_config).
    El context manager de `connect()` y los `with conn:` commitean al salir.
    """
    uid = _resolve_user_id(user_id)
    conn.execute(
        "INSERT INTO configuracion (clave, valor, user_id) VALUES (?, ?, ?) "
        "ON CONFLICT(clave, user_id) DO UPDATE SET valor = excluded.valor",
        (clave, str(valor), uid),
    )


def get_config(
    conn: sqlite3.Connection,
    clave: str,
    default: str = "",
    user_id: Optional[int] = None,
) -> str:
    """Lee `clave` para el usuario activo. Devuelve `default` si no existe."""
    uid = _resolve_user_id(user_id)
    row = conn.execute(
        "SELECT valor FROM configuracion WHERE clave = ? AND user_id = ?",
        (clave, uid),
    ).fetchone()
    return row["valor"] if row else default


def backup_db(
    conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None
) -> Path:
    """Copia online de la DB a `BACKUP_DIR/finanzas-YYYYMMDD-HHMMSS.db`.

    `conn` es OPCIONAL: los call sites de core/ (transactions, budget,
    categorias) llaman `backup_db()` sin argumentos y acá se abre una
    conexión propia a la DB activa.

    Regresión 2/7/2026: al reconstruir este módulo tras la corrupción de
    OneDrive, la firma quedó exigiendo `conn` y TODA escritura en producción
    crasheaba con TypeError (y sin backup). Cubierto por
    tests/test_backup_regresion.py — no volver a hacer `conn` obligatorio.
    """
    backup_dir = BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"finanzas-{ts}.db"
    conn_propia = conn is None
    if conn_propia:
        conn = sqlite3.connect(db_path if db_path is not None else get_db_path())
    backup_conn = sqlite3.connect(dest)
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()
        if conn_propia:
            conn.close()
    retention = int(os.environ.get("BACKUP_RETENTION", "30"))
    _purge_old_backups(retention_days=retention, keep_recent=10)
    return dest


def _purge_old_backups(
    retention_days: int = 30, keep_recent: int = 10
) -> None:
    """Conserva el ULTIMO backup de cada dia dentro de retention_days +
    los keep_recent absolutamente mas recientes.

    Usa el `BACKUP_DIR` del módulo (monkeypatcheable por los tests).
    """
    backup_dir = BACKUP_DIR
    if not backup_dir.exists():
        return
    files = sorted(backup_dir.glob("finanzas-*.db"), key=lambda p: p.name)
    if not files:
        return

    def _fecha_de(p: Path) -> Optional[str]:
        stem = p.stem
        partes = stem.split("-")
        if len(partes) < 3:
            return None
        return partes[1]

    a_preservar = set(files[-keep_recent:])
    hoy = datetime.now().date()
    ventana = {
        (hoy - timedelta(days=i)).strftime("%Y%m%d")
        for i in range(retention_days + 1)
    }
    por_dia = {}
    for p in files:
        fecha = _fecha_de(p)
        if fecha is None or fecha not in ventana:
            continue
        prev = por_dia.get(fecha)
        if prev is None or p.name > prev.name:
            por_dia[fecha] = p
    a_preservar.update(por_dia.values())

    for p in files:
        if p not in a_preservar:
            try:
                p.unlink()
            except OSError:
                pass
