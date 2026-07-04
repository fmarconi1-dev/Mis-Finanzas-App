# Mejoras pendientes

Backlog priorizado. Se ordena por impacto / esfuerzo / riesgo. Lo que se va completando pasa a la [BITACORA](BITACORA.md).

> **El backlog histórico de UX** vive en [`docs/MEJORAS-UX.md`](docs/MEJORAS-UX.md). Este archivo consolida lo que sigue pendiente.
>
> **Para el estado completo del proyecto**, ver [`docs/RESUMEN-PROYECTO.md § 19`](docs/RESUMEN-PROYECTO.md).

---

## 🔴 Próximo trabajo grande

### D2 · Grupo familiar Cutover (siguiente sesión)

**Contexto:** D1 (Shadow) ya está en producción — tablas `workspaces` y `workspace_members` creadas, backfill correcto, 15 tests de invariante en verde. Las queries del `core/` todavía filtran por `user_id`; el feature está invisible al usuario.

**Alcance (decidido con Franco 2/7/2026):**
- Feature completo: badge persistente + switcher + crear/unirse/salir + "firmar como" + multi-owner.
- Estimación: 4-5 días.

**Backend (refactor):**
- Nuevo contextvar `current_workspace_id` en `core/current_workspace.py` (o mismo `core/current_user.py`).
- Refactor de queries: `user_id` → `workspace_id` en:
  - `core/transactions.py` (list_recent, all_motivos, motivos_recientes, montos_frecuentes, insert/update/delete_transaction).
  - `core/budget.py` (comparativa_mes, previsiones_editor, upsert/delete_presupuesto, copy_year, meses_con_datos, realidad_mensual_efectiva).
  - `core/categorias.py` (todas las funciones CRUD).
  - `core/diario.py` (libro_diario, saldo_inicial).
  - `core/metrics.py` (load_transactions, load_categorias_map/full, compute_kpis, saldo_cuenta_corriente, fondo_emergencia_usd, etc.).
  - `core/db.py::set_config/get_config`.
- Módulo nuevo `core/workspaces.py` con: `create_family_workspace(user_id, nombre) → workspace_id, invitation_code`, `join_family_workspace(user_id, member_label, invitation_code)`, `leave_family_workspace(workspace_id, user_id)`, `list_user_workspaces(user_id)`, `set_active_workspace(session_state, workspace_id, member_label)`.
- Código de invitación: `secrets.token_urlsafe(8)` + hash SHA-256 en DB. Match por hash.

**UI:**
- Badge persistente en la barra superior de `app.py` con el workspace activo y el `member_label` cuando corresponde.
- Switcher (dropdown o botones) en `ui/views/configuracion.py` o directamente en la sidebar.
- Formularios crear/unirse/salir en `ui/views/configuracion.py` sección nueva "Espacio compartido".
- Dropdown "Firmar como" en `ui/views/transacciones.py` cuando el workspace activo es familiar. Guarda en `Transaccion.creado_por_member_label`.
- Multi-owner: todos los miembros con role `admin`. Cualquiera puede invitar/expulsar.

**Tests:**
- Nuevos en `tests/test_premortem5.py`:
  - Crear workspace familiar genera code único.
  - Join con code correcto suma miembro; con code inválido rechaza.
  - Leave elimina al miembro pero preserva el workspace si quedan más.
  - `creado_por_member_label` se registra correctamente al insertar en familiar.
  - Query de KPIs filtra correctamente por workspace_id (Franco Personal ≠ Franco+Agus Familiar).

**Riesgos identificados en el premortem #5 a mitigar durante D2:**
- Refactor incompleto: alguna query queda filtrando por `user_id` → filas del workspace equivocado.
- Confusión de modo: cargás transacción en Personal creyendo estar en Familiar. Mitigación: badge grande y de color distinto por modo.
- `miembroActivo` sin verificación: dejarlo explícito en la UI que es etiqueta cosmética, no auth.
- Callbacks de Streamlit sin contextvar: pasar `workspace_id` explícito desde session_state (mismo patrón que ya usa el Fondo USD del Dashboard).

---

## 🟢 Trabajos chicos que quedaron sueltos

### Voz consistente (Sección 7 del backlog UX)
- Módulo `ui/helpers/_voz.py` con reglas documentadas + hitos de celebración (1ª transacción, 10ª, 50ª, 100ª, 365ª).
- Integración en `ui/views/transacciones.py` post-insert.
- **Esfuerzo:** 1 día. **Riesgo:** cero.

### Ajustar Fondo USD de Franco en producción
- Después de M6, quedó en $0 (antes era $864). Editable desde el Dashboard.
- No es bug: el backfill leyó el valor actual de `configuracion`. Puede que Franco lo haya bajado sin recordar o que el valor productivo ya estuviera en 0.
- **Acción:** Franco lo ajusta desde el Dashboard cuando quiera.

---

## 🟡 Importante — features grandes con premortem propio requerido

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

### Sección 8 — Chatbot WhatsApp
- Tier gratis de WhatsApp Business Cloud API (1000 conversaciones/mes). Arquitectura: FastAPI embebido + webhook. Requiere número dedicado verificado en Meta Business.
- **Pre-requisito:** M5 (API sidecar) hecho.

### Sección 9 — Módulo de inversiones
- Scope reducido al 70% por el [premortem #2](docs/premortems/premortem-inversiones-2026-05-27.md): **NO reemplazar el Excel de Inviu**. Solo visualizar + reconciliar broker ↔ cuenta corriente personal.
- **Pre-requisito:** el módulo Excel actual sigue siendo fuente de verdad.

### Sección 10 — Monetización
- **NO publicidad** (mata confianza, regulatorio, matemática no cierra). Freemium o suscripción cuando llegue el momento.
- Diferido hasta 5-10 usuarios activos.

### Sección 4.4 — Toggle claro / oscuro
- Bajo impacto, conflictúa con el dark CSS de Cosmic Slate. Diferido.

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

---

## ✅ Completado en las últimas sesiones

- **Deploy estética 1** (3/7/2026): contraste WCAG en labels de métricas, focus-visible, prefers-reduced-motion, tabular-nums, radii unificados, `streamlit==1.58.0` pinneado, `use_container_width` → `width="stretch"`. Ver BITACORA.
- **M6 Grupo familiar D1 Shadow** (2/7/2026): tablas + backfill + 15 tests. Deploy exitoso en producción con 230+ transacciones y 2 workspaces creados (Franco y Agustina).
- **M2 Subcategorías visibles en UI** (2/7/2026): Transacciones, Mensual (tabla + editor), Dashboard donut (toggle Motivo/Subcategoría).
- **Estética Cosmic Slate** (26/6/2026): paleta zinc + violeta + esmeralda, tipografía Inter/Space Grotesk/JetBrains Mono.
- **Reorganización moderada** (26/6/2026): `docs/`, `ui/{auth,views,helpers}`, imports actualizados.
- **Repo público en GitHub** (26/6/2026): `fmarconi1-dev/Mis-Finanzas-App` con README + MEJORAS + BITACORA + LICENSE + `.gitignore` robusto.
- **Fix bugs producción** (26/6/2026): HTML literal, TypeError `st.logo`, donut mobile.
- **Premortem #4** (26/6/2026): decisión de NO migrar el stack.
- **Premortem #5** (2/7/2026): 15 modos de fallo del grupo familiar identificados y mitigados en D1.

Ver [BITACORA.md](BITACORA.md) para el detalle cronológico.
