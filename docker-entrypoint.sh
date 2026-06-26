#!/bin/sh
# Entrypoint: siembra la base en el volumen la primera vez (o si quedó vacía),
# usando seed_finanzas.db si existe en la imagen. Después arranca Streamlit.
#
# Es idempotente y seguro de dejar permanentemente:
#   - Sólo siembra si hay un seed Y la base del volumen no existe o tiene 0 txns.
#   - Si no hay seed (deploy normal), no hace nada y arranca la app.

SEED=/app/seed_finanzas.db
DB=/app/data/finanzas.db

needs_seed() {
  [ ! -f "$DB" ] && return 0
  count=$(python -c "import sqlite3;print(sqlite3.connect('$DB').execute('SELECT COUNT(*) FROM transacciones').fetchone()[0])" 2>/dev/null || echo 0)
  [ "$count" = "0" ] && return 0
  return 1
}

if [ -f "$SEED" ] && needs_seed; then
  echo "[entrypoint] Sembrando base inicial desde seed_finanzas.db..."
  cp "$SEED" "$DB"
  rm -f "$DB-wal" "$DB-shm"
  echo "[entrypoint] Listo."
fi

exec streamlit run app.py
