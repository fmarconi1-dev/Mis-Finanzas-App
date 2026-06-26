# Mejoras pendientes

Backlog priorizado. Se ordena por impacto / esfuerzo / riesgo. Lo que se va completando pasa a la [BITACORA](BITACORA.md).

> **El backlog histórico de UX** vive en [`docs/MEJORAS-UX.md`](docs/MEJORAS-UX.md). Este archivo consolida lo que sigue pendiente.

---

## 🟢 Próximo (alto ROI, bajo riesgo)

### M1.b · Verificar Cosmic Slate en producción
- **Qué:** `fly deploy` con los cambios de paleta + tipografía aplicados (config.toml, `_theme.py`, `_styles.py`).
- **Cómo:** correr el deploy, abrir la app en desktop + mobile, ver si los `data-testid` resisten en la versión de Streamlit en producción.
- **Esfuerzo:** 30 min.
- **Riesgo:** bajo. Si algún selector quedó desfasado, los tokens CSS `--cs-*` se ajustan en un solo lugar.

### M2 · Subcategorías visibles en UI
- **Qué:** la subcategoría (Supermercado, Alquiler, Sueldo) ya existe en `core/categorizer.py` pero no se muestra en Transacciones ni en el donut del Dashboard.
- **Por qué:** desambiguar gastos. "Compras" puede ser supermercado, ropa o regalos: con la subcategoría se entiende qué dispara el mes.
- **Esfuerzo:** 1 día.
- **Riesgo:** bajo. Solo es UI + 2 queries adicionales.

### Bug-fix · Eliminar archivos basura del raíz
- `4.1.0`, `seed_finanzas.db-wal`, `.fuse_hidden0000001100000004` no se pudieron borrar desde acá (OneDrive bloqueó). **Pendiente que Franco los borre manualmente** desde Explorer antes del primer commit.

---

## 🟡 Importante (cambio estructural, requiere su propio premortem)

### M3 · Grupo familiar (workspaces) — adaptado del proyecto paralelo
- **Qué:** cada usuario podría tener un **Espacio Personal** + un **Espacio Familiar** compartido con código de invitación. Dentro del familiar, dropdown "firmar como" (Papá / Mamá / Juan) que queda en `creado_por_member_label`. Switch instantáneo entre ambos.
- **Modelo SQLite propuesto:**
  ```
  workspaces(id, owner_user_id, kind, nombre, invitation_code_hash, saldo_inicial, fondo_usd, created_at)
  workspace_members(workspace_id, user_id, role, member_label, joined_at)
  -- transacciones: cambia user_id → workspace_id (+ creado_por_member_label opcional)
  -- categorias / presupuesto / configuracion: idem workspace_id
  ```
- **Endurecimientos respecto a la otra app:** código de invitación con `secrets.token_urlsafe(8)` + hash (no `FAM-XXXX-NNN` predecible); member_labels editables (no hardcoded `['Papá', 'Mamá', 'Juan']`); UI deja claro que "firmar como" es etiqueta cosmética y NO impide editar transacciones de otros miembros.
- **Esfuerzo:** 3-5 días.
- **Riesgo:** ALTO. Cambia schema, toca todas las queries del core, afecta datos productivos. **Premortem específico requerido antes de ejecutar.**

### M4 · Importador inteligente de CSV con LLM
- **Qué:** cuando importás un CSV nuevo (no del formato Diario.csv original), una llamada offline a Claude / Gemini que devuelve mapping de columnas + sugerencias de categorías. Output revisable antes de impactar la DB.
- **Por qué offline:** evitar costo runtime (no en hot path del dashboard) y dependencia de red. Una sola llamada por importación.
- **Esfuerzo:** 3-5 días.
- **Riesgo:** medio (silent failure si el LLM categoriza mal — mitigable con preview obligatorio).

### M5 · API sidecar para agente conversacional
- **Qué:** FastAPI corriendo en el mismo Fly machine, escribiendo a la misma SQLite, con token bearer rotable + rate-limit por IP + validación Pydantic + log de auditoría. Endpoints: `GET /summary`, `POST /transaction`.
- **Para qué:** habilita el caso de uso del archivo `ai_studio_code.ts` (anotar gastos desde WhatsApp / Telegram / iOS Shortcuts) **sin migrar de stack**.
- **Esfuerzo:** 1 semana.
- **Riesgo:** medio. Hay que cuidar la superficie de ataque del endpoint público.

---

## 🟠 UX continua (del backlog histórico)

### Sección 7 — Voz consistente (pendiente)
- Módulo `ui/helpers/_voz.py` con reglas documentadas + hitos de celebración (1ª transacción, 10ª, 50ª, 100ª, 365ª).
- Integración en `ui/views/transacciones.py` post-insert.
- **Esfuerzo:** 1 día.

### Sección 4.4 — Toggle claro / oscuro
- Bajo impacto, conflictúa con el dark CSS de Cosmic Slate. Diferido.

### Sección 8 — Chatbot WhatsApp
- Tier gratis de WhatsApp Business Cloud API (1000 conversaciones/mes). Arquitectura: FastAPI embebido + webhook. Requiere número dedicado verificado en Meta Business.
- **Pre-requisito:** M5 (API sidecar) hecho.

### Sección 9 — Módulo de inversiones
- Scope reducido al 70% por el [premortem #2](docs/premortems/premortem-inversiones-2026-05-27.md): **NO reemplazar el Excel de Inviu**. Solo visualizar + reconciliar broker ↔ cuenta corriente personal.
- **Pre-requisito:** el módulo Excel actual sigue siendo fuente de verdad.

### Sección 10 — Monetización
- **NO publicidad** (mata confianza, regulatorio, matemática no cierra). Freemium o suscripción cuando llegue el momento.
- Diferido hasta 5-10 usuarios activos.

---

## 🔵 Operación (RUNBOOK)

Pendiente que Franco haga manualmente (ver [`docs/RUNBOOK-OPERACION.md`](docs/RUNBOOK-OPERACION.md)):

- [ ] Correr el primer `backup_remoto.ps1` y verificar que copia bien la DB de Fly a la PC.
- [ ] Programar `backup_remoto.ps1` en Task Scheduler para que corra todos los días.
- [ ] Setear secrets en Fly: `fly secrets set SIGNUP_CODE=...` y `fly secrets set SESSION_SECRET=$(openssl rand -hex 32)`.
- [ ] Crear monitor de uptime (UptimeRobot u otro).
- [ ] Generar `requirements.lock` con `pip freeze > requirements.lock` para builds reproducibles.
- [ ] Ensayar UN restore desde un backup, end-to-end, para validar el procedimiento.

---

## 🚫 Decisiones cerradas (no hacer)

### NO migrar el stack a React + Firestore + Gemini
- **Decisión:** [Premortem #4](docs/RESUMEN-PROYECTO.md#17-premortem-4--decisión-migrar-a-reactfirestoregemini-no-2662026) (26/6/2026).
- **Razones principales:** costos ($0 → $25-60/mes), vendor lock-in Firebase, security rules abiertas en la versión paralela (`allow read, write: if true`), premortem #3 (rate-limit + SIGNUP_CODE + SESSION_SECRET) a rehacer entero, surface area 5x más grande, riesgo de pérdida de datos en migración.
- **Trigger para reconsiderar:** 20+ usuarios activos pagando, o feature específica cuantificable bloqueada por Streamlit.

### NO reemplazar el Excel de Inviu para inversiones
- **Decisión:** [Premortem #2](docs/premortems/premortem-inversiones-2026-05-27.md).
- **Razón:** el Excel ya tiene addin BYMADATA tirando precios solo. Reemplazarlo implica mantener integraciones de precios. Mejor visualizar + reconciliar.
