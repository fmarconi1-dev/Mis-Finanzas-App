# Runbook de operación — Radar Financiero

Salida del premortem #3 (11/6/2026). Cubre lo que el código no puede hacer solo:
backup externo, restore, monitoreo, secrets y deploy seguro.

---

## 1. Backup externo automático (R1) — HACER HOY

La DB y sus backups viven en UN volumen de Fly. Esta es la copia externa.

**Manual (primera vez, ya mismo):**
```powershell
cd "C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\App seguimiento de gastos"
powershell -ExecutionPolicy Bypass -File scripts\backup_remoto.ps1
```
Deja `backups-remotos\finanzas-cloud-YYYYMMDD-HHMMSS.db` (verificada con
`integrity_check`). La carpeta está dentro de OneDrive → copia local + nube.

**Automático (Programador de tareas de Windows):**
1. Abrir "Programador de tareas" → Crear tarea básica.
2. Nombre: `Backup Radar Financiero`. Desencadenador: Diariamente, 21:00.
3. Acción: Iniciar un programa → `powershell.exe`
   Argumentos: `-ExecutionPolicy Bypass -File "C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\App seguimiento de gastos\scripts\backup_remoto.ps1"`
4. Marcar "Ejecutar aunque el usuario no haya iniciado sesión" si la PC queda prendida.

**Snapshots de Fly (verificar una vez):**
```powershell
fly volumes list -a radar-financiero
fly volumes snapshots list <volume-id> -a radar-financiero
```
Fly toma snapshots diarios con ~5 días de retención. Son el segundo paracaídas,
no el principal (viven en la misma plataforma).

---

## 2. Ensayo de restore (R10) — hacerlo UNA vez esta semana

Un backup sin restore ensayado es una hipótesis. Ensayo completo en local:

```powershell
cd "C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\App seguimiento de gastos"
# 1. Tomar el backup remoto más nuevo y copiarlo a una DB de prueba
copy backups-remotos\finanzas-cloud-<el-mas-nuevo>.db data\finanzas-restore-test.db
# 2. Levantar la app local apuntando a esa DB
$env:DB_PATH = "data\finanzas-restore-test.db"
.venv\Scripts\activate
streamlit run app.py
# 3. Verificar: login OK, saldo CC coincide con producción, última transacción presente.
# 4. Borrar la DB de prueba y limpiar DB_PATH.
```

**Restore a producción (el día que haga falta):**
```powershell
# Subir el .db bueno al volumen y reiniciar
fly ssh sftp shell -a radar-financiero
# dentro del shell sftp:
#   put backups-remotos\finanzas-cloud-XXXX.db /app/data/finanzas.db
# salir y reiniciar:
fly apps restart radar-financiero
```
Nota: si la app estaba escribiendo, borrar también `/app/data/finanzas.db-wal`
y `finanzas.db-shm` antes de reiniciar (`fly ssh console -C "rm -f /app/data/finanzas.db-wal /app/data/finanzas.db-shm"`).

---

## 3. Monitoreo mínimo (R7) — 15 minutos

1. **Uptime:** crear monitor gratuito en https://uptimerobot.com →
   HTTP(s), URL `https://radar-financiero.fly.dev/_stcore/health`, cada 5 min,
   alerta al mail. (La máquina duerme por auto_stop: el monitor la despierta;
   si eso molesta, usar intervalo de 30-60 min.)
2. **Billing:** verificar HOY en https://fly.io/dashboard → Billing que la
   tarjeta esté vigente. Agregar `billing@fly.io` y `support@fly.io` a
   remitentes seguros del mail.
3. **Chequeo semanal (1 comando):**
   ```powershell
   fly ssh console -a radar-financiero -C "sh -c 'du -sh /app/data && ls /app/data/backups | wc -l'"
   ```
   Disco creciendo raro o cuenta de usuarios inflada = señal temprana de F4.

---

## 4. Dependencias reproducibles (R8)

El Dockerfile ya usa `requirements.lock` si existe. Generarlo desde la imagen
que HOY funciona en producción:

```powershell
fly ssh console -a radar-financiero -C "pip freeze" > requirements.lock
# limpiar líneas que no sean paquetes (warnings) si las hay, y commitear.
```
Desde ese momento, cada `fly deploy` instala exactamente esas versiones.
Para actualizar a propósito: borrar el lock, deployar, probar, regenerar.

---

## 5. Secrets nuevos (R5 + R9)

```powershell
# Habilitar signup con código de invitación (sin esto, el signup queda CERRADO):
fly secrets set SIGNUP_CODE=<elegir-codigo> -a radar-financiero

# Sesión persistente (no re-loguear en cada refresh):
fly secrets set SESSION_SECRET=<salida de: openssl rand -hex 32> -a radar-financiero
# (en Windows sin openssl: python -c "import secrets; print(secrets.token_hex(32))")
```
Cada `fly secrets set` redeploya la app. Rotar SESSION_SECRET cierra todas las
sesiones recordadas.

---

## 6. Deploy seguro (checklist)

1. `python -m pytest tests/ -v` → todo verde (76 tests).
2. Backup externo fresco (`scripts\backup_remoto.ps1`).
3. `fly deploy`.
4. Abrir la app, login, verificar saldo CC y última transacción.
5. La migración M5 corre sola en el primer arranque (rebuild de 4 tablas,
   idempotente). Si algo falla, el paso 2 es tu red.

---

## 7. Chequeo mensual (5 minutos)

- [ ] ¿El backup externo más nuevo tiene menos de 48 hs? (`backups-remotos\`)
- [ ] ¿UptimeRobot sin caídas raras?
- [ ] ¿`SELECT COUNT(*) FROM usuarios` = la gente que conocés?
      `fly ssh console -a radar-financiero -C "python -c \"import sqlite3; print(sqlite3.connect('/app/data/finanzas.db').execute('SELECT COUNT(*) FROM usuarios').fetchone())\""`
- [ ] ¿Tarjeta de Fly vigente?
