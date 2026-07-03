# Bitácora del proyecto

Changelog narrativo: qué se hizo, cuándo, por qué. Ordenado del más reciente arriba al más viejo abajo. Las entradas son resumen ejecutivo — el detalle técnico vive en `docs/RESUMEN-PROYECTO.md` y `docs/MEJORAS-UX.md`.

---

## 2026-07-02 · Deploy productivo M2 + M6 (D1 Shadow)

**Qué:** subida a producción de las dos features nuevas de esta semana. Todo verificado en https://radar-financiero.fly.dev con datos reales.

**Cambios efectivos:**

- **M2 (Subcategorías visibles en UI)** — la columna Subcategoría ya aparece en Transacciones, Mensual (tabla principal + editor de previsiones) y como toggle en el donut del Dashboard. Diario ya la tenía.
- **M6 (Grupo familiar D1 Shadow)** — tablas `workspaces` y `workspace_members` creadas en la DB productiva. Backfill ejecutado correctamente:
  - Franco Marconi (`user_id=1`) → workspace personal id=1, saldo $101.515,65, fondo USD $0.
  - Agustina Franco (`user_id=2`) → workspace personal id=2, saldo $0, fondo USD $0.
  - **230/230 transacciones** con `workspace_id` asignado (invariante crítico cumplido).
- **Estética Cosmic Slate** verificada en producción tras el deploy: fondo #09090B, botones violeta, tipografías Inter + JetBrains Mono. Todos los cambios visibles.

**Otras acciones de la sesión:**

- **Repo público en GitHub creado y sincronizado**: `fmarconi1-dev/Mis-Finanzas-App` (branch `main`). Push exitoso tras resolver conflictos de credenciales locales (Git Credential Manager tenía la cuenta `tresterciosadmin` en caché, se limpió).
- Se actualizó Git Credential Manager y se configuró user.name/user.email correctos.
- Se subieron README.md + LICENSE + MEJORAS.md + BITACORA.md al repo.
- Docs consolidados en `docs/` (DEPLOY, RESUMEN-PROYECTO, MEJORAS-UX, RUNBOOK, premortems).

**Sanity:** **94/94 tests verdes** (76 anteriores + 15 premortem5 + 3 mejoras que Franco hizo en test_premortem5.py).

**Bugs sorteados durante la sesión:**

- `core/db.py` se corrompió dos veces durante los edits por conflictos con OneDrive:
  - Una vez perdió el bloque desde línea 410 hasta el final (funciones `get_db_path`, `connect`, `init_db`, `set_config`, `get_config`, `backup_db`, `_purge_old_backups`). Se reconstruyeron a partir de los tests y las signaturas que las llamaban.
  - Otra vez OneDrive metió null bytes al final del archivo que hacían crashear `_purge_old_backups`. Se detectó vía `file core/db.py` y se limpió con Python.
- El primer `git push` falló por credenciales de GCM cacheadas de otra cuenta (`tresterciosadmin`). Solución: `git credential-manager github logout tresterciosadmin` + reintento.

**Estado de D2 (Cutover):** las queries del `core/` siguen usando `user_id` — el feature de grupo familiar NO está visible al usuario. El próximo trabajo grande es D2. Ver `MEJORAS.md` para el alcance detallado.

**Confirmaciones del usuario para D2:**
- 1-2 personas concretas van a usar el feature (ya Agustina tiene cuenta).
- Alcance: "feature completo" (badge + switcher + crear/unirse/salir + firmar como + multi-owner).
- Ownership: multi-owner, sin jerarquía.
- Estrategia: shadow + cutover (D1 ya hecho, D2 pendiente).

---

## 2026-06-26 · Grupo familiar D1 (Shadow) — migración M6

**Qué:** primer deploy del feature de grupo familiar. Solo infraestructura; las queries del `core/` siguen usando `user_id`. El cutover a `workspace_id` viene en D2.

**Contexto:** premortem #5 identificó 15 modos de fallo (migración rota, refactor incompleto del core, confusión de modo, ownership mal definido, feature no se usa). Franco eligió: 1-2 personas concretas usando el feature, alcance "feature completo", multi-owner, migración shadow+cutover.

**Cambios:**

- **`core/db.py`** — nueva migración `M6` (premortem #5, Shadow), idempotente:
  - Tabla `workspaces (id, kind, nombre, invitation_code_hash, saldo_inicial, fondo_usd, creado_en)` con `CHECK(kind IN ('personal','familiar'))`.
  - Tabla `workspace_members (workspace_id, user_id, role, member_label, joined_en)` con PK compuesta, `UNIQUE (workspace_id, member_label)` para evitar labels colisionantes, y FK con `ON DELETE CASCADE`.
  - Columna `workspace_id INTEGER REFERENCES workspaces(id)` nullable en `transacciones`, `categorias`, `presupuesto`, `configuracion`.
  - Columna `creado_por_member_label TEXT` en `transacciones` (auditoría cosmética).
  - **Backfill**: por cada usuario sin workspace personal, se crea uno con el saldo y fondo USD actuales; se agrega como admin con `member_label = fullname or username`; se UPDATE cada tabla poniendo `workspace_id` en las filas que todavía tenían `NULL`.
- **`tests/test_premortem5.py`** — 15 tests nuevos organizados en 4 clases:
  - `TestM6CreaInfraestructura` (4 tests): tablas y columnas nuevas existen.
  - `TestM6BackfillCorrecto` (6 tests, incluyen invariante crítico): `COUNT(tabla WHERE user_id = u) == COUNT(tabla WHERE workspace_id = personal_de(u))` para las 4 tablas y todos los usuarios; ninguna fila queda con `workspace_id IS NULL`.
  - `TestM6Idempotente` (2 tests): correr `_migrate()` dos veces no duplica workspaces ni miembros.
  - `TestM6ConstraintsActivos` (3 tests): CHECK, UNIQUE y FK constraints disparan.

**Sanity:** **91/91 tests verdes** (76 anteriores + 15 nuevos M6).

**Notas de la sesión:** durante la reconstrucción del final de `core/db.py` (perdido en un edit anterior por conflicto de OneDrive), aprovechamos para dejar documentado en el docstring de `connect()` que se usa `isolation_level=None` (necesario para el BEGIN/COMMIT manual de `core/ingest.py`) y en `set_config()` que no hace commit interno (el caller decide). Un residual de null bytes en el archivo (metido por OneDrive) rompía `_purge_old_backups` — se limpió.

---

## 2026-06-26 · Subcategorías visibles en UI (M2)

**Qué:** la subcategoría ya estaba en datos (`core/categorizer.py`, `core/metrics.py::load_categorias_full`) pero solo el libro Diario la mostraba. Las otras vistas usaban únicamente el motivo, dejando ambigüedad: "Compras" puede ser supermercado, ropa o regalos.

**Cambios:**
- **Transacciones** (`ui/views/transacciones.py`): la tabla de últimas 20 transacciones suma una columna "Subcategoría" después de "Motivo". Se calcula fila a fila con `efective_grupo()` aplicando la regla dual (misma lógica del libro Diario).
- **Mensual** (`ui/views/mensual.py`):
  - Tabla "Previsión vs Realidad": columna "Subcategoría" después de "Motivo".
  - Editor de previsiones (expander): columna "Subcategoría" disabled junto a "Motivo" y "Grupo".
- **Dashboard donut** (`ui/views/dashboard.py`): toggle `st.radio` con opciones "Motivo" / "Subcategoría" arriba del gráfico. Si el usuario elige Subcategoría, reagrupa el DataFrame localmente (sin tocar core) preservando los colores del grupo para mantener semántica visual.
- **Libro Diario**: ya estaba — no se tocó.

**Sanity:** 40/40 .py compilan. Sin cambios de schema, sin migración, sin afectar reconciliación de Caja.

---

## 2026-06-26 · Reorganización para repo público

**Qué:** se preparó el proyecto para un repo público en GitHub (`mis-finanzas-personales`).

**Cambios:**
- Creada estructura `docs/` con todos los .md de proyecto (DEPLOY, MEJORAS-UX, RESUMEN-PROYECTO, RUNBOOK-OPERACION) y `docs/premortems/` con los dos premortems históricos.
- `ui/` reorganizado en `ui/auth/` (login), `ui/views/` (dashboard, transacciones, diario, mensual, configuracion, onboarding) y `ui/helpers/` (_format, _html, _logo, _responsive, _styles, _theme, _tour). Actualizados todos los imports — 40/40 archivos compilan.
- `.gitignore` reforzado para cubrir todos los datos personales (DB, backups, CSVs originales, Excels), Python (venv, pycache, lock files), IDE y archivos basura conocidos del proyecto.
- README nuevo al raíz (el viejo, de Fase 1, quedó en `docs/README-LEGACY.md` como referencia histórica).
- MEJORAS.md nuevo al raíz: backlog consolidado y priorizado.
- BITACORA.md nuevo al raíz (este archivo).
- LICENSE MIT al raíz.

**Pendiente manual de Franco:** borrar 3 archivos basura que OneDrive no permitió borrar desde acá (`4.1.0`, `seed_finanzas.db-wal`, `.fuse_hidden*`). El `.gitignore` los excluye igual.

---

## 2026-06-26 · Cosmic Slate (paleta + tipografía)

**Qué:** adoptada la estética "Cosmic Slate" del proyecto paralelo (React + Tailwind), **sin migrar el stack**.

**Cambios:**
- `.streamlit/config.toml`: primary `#6ee7b7` → `#8B5CF6` (violeta), background `#0e1117` → `#09090B` (zinc-950), secondary `#1a2030` → `#18181B` (zinc-900), text `#e8ecf4` → `#E4E4E7`.
- `ui/helpers/_theme.py`: COLOR_GASTO `#f87171` → `#F43F5E` (rose-500), COLOR_INVERSION `#34d399` → `#10B981` (emerald-500), COLOR_ACENTO `#6ee7b7` → `#8B5CF6`, COLOR_NEUTRO `#9aa3b8` → `#A1A1AA` (zinc-400). Plotly template ahora usa tipografía Inter y JetBrains Mono en hovers.
- `ui/helpers/_styles.py`: rewrite completo con tokens CSS `--cs-*` documentados. Carga Inter + Space Grotesk + JetBrains Mono desde Google Fonts. Componentes repintados (métricas, botones primarios con gradient violet→indigo, containers, expanders, inputs con focus violeta, tabs, sidebar, code blocks, scrollbars Cosmic Slate).

**Lo que NO cambió:** la paleta semántica (azul=ingreso, rojo=gasto, verde=inversión, ámbar=desahorro). Cosmic Slate cambia fondo + acentos, no significados.

---

## 2026-06-26 · Premortem #4 — Decisión: NO migrar a React + Firestore + Gemini

**Qué:** Franco compartió el zip del proyecto paralelo y pidió evaluar migrar. Se aplicó premortem comparando ambas opciones a 6 meses.

**Modos de fallo "migrar"** (11 identificados, top 5):
1. Costos: $0 → $25-60/mes (Firestore + Gemini).
2. Migración SQLite → Firestore rompe reconciliación de KPIs sobre datos productivos.
3. Vendor lock-in de Firebase (auth rules + security rules + hosting).
4. `firestore.rules` en la app paralela está **abierta al mundo** (`allow read, write: if true`). Confirma el riesgo identificado.
5. Premortem #3 (rate-limit + SIGNUP_CODE + SESSION_SECRET) a rehacer entero.

**Modos de fallo "quedarse"** (5 identificados): techo estético, mobile no premium, ausencia de agente conversacional (mitigable con FastAPI sidecar), SQLite techo a ~10-20 usuarios concurrentes, riesgo de estancamiento.

**Decisión:** mantener Streamlit + Fly.io. Adoptar lo bueno del proyecto paralelo de forma incremental (estética Cosmic Slate, futuro grupo familiar adaptado, API sidecar opcional). Trigger para reconsiderar: 20+ usuarios activos pagando o feature específica cuantificable bloqueada por Streamlit.

---

## 2026-06-26 · Fix bugs producción (HTML literal + TypeError + donut mobile)

**Qué:** tres bugs aparecieron en producción después del deploy de Fase 4. Capturas en mobile mostraron el problema.

**Bugs:**
1. **HTML inline renderizado como texto literal** en login hero, onboarding hero y saludo del dashboard. Causa: Streamlit ≥1.41 deja de renderizar inline tags vía `st.markdown(..., unsafe_allow_html=True)` y los escapa. Los `<style>` SÍ siguen pasando.
2. **TypeError "'text/html' is not a valid JavaScript MIME type"** en Transacciones. Causa: `st.logo("assets/logo.svg")` intentaba cargar el SVG como módulo JS.
3. **Donut chart con etiquetas solapadas en mobile** (viewport 375px no entra `textposition="outside"`).

**Fixes:**
- Nuevo `ui/helpers/_html.py` con helper `render_html(html)` que usa `st.html()` cuando está disponible (Streamlit ≥1.33) y cae a `st.markdown(unsafe_allow_html=True)` si no.
- `_responsive.py` y `_styles.py` migrados al helper.
- Login y onboarding usan `render_logo()` (nuevo en `_logo.py`) que dibuja el SVG como `st.image()` centrado en columnas — sobrevive al sanitizer DOMPurify de `st.html()`.
- Saludo del dashboard pasó a markdown puro: `st.markdown(f"👋 Hola, **{nombre}**")`.
- `app.py`: removido `try_set_logo()`, `page_icon` cambiado de `assets/logo.svg` a `🎯`.
- Donut: `textposition="inside"` + `textinfo="percent"` + `insidetextorientation="radial"` + leyenda horizontal abajo.
- `requirements.txt`: streamlit `>=1.30.0` → `>=1.33.0`.

---

## 2026-06-11 · Premortem #3 + hardening

**Qué:** se corrió un premortem sobre la app completa. Se identificaron 8 modos de fallo. Cambios aplicados (76 tests verdes, 18 nuevos en `tests/test_premortem3.py`):

- **R2:** retención de backups por edad (último de cada día por 30 días + 10 más recientes), no "los 30 últimos".
- **R3:** `comparativa_mes` clasifica fila a fila con `efective_grupo` (nueva `realidad_mensual_efectiva`). Fix: una venta de "Inversiones" desaparecía de la pestaña Mensual.
- **R4:** `anios_con_datos` + `filtrar_anio` + selector de año en Dashboard. Fix: KPIs anuales sumaban toda la historia.
- **R5:** signup cerrado salvo que exista `SIGNUP_CODE` + rate-limit de login (5 fallos / 15 min → 5 min de bloqueo).
- **R6:** migración M5 — user_id sin DEFAULT en las 4 tablas; un INSERT sin user_id lanza IntegrityError (antes caía silencioso en id=1).
- **R8:** Dockerfile usa `requirements.lock` si existe.
- **R9:** sesión persistente con token HMAC firmado en URL, activa solo si `SESSION_SECRET` está seteado.
- **R1/R7/R10:** `scripts/backup_remoto.ps1` + `RUNBOOK-OPERACION.md` con backup externo, ensayo de restore, monitoreo, billing.

---

## 2026-05-12 a 2026-06-11 · Fases 1 a 4 (resumen)

### Fase 1 (mayo 2026) — MVP read-only
Parser CSV con encoding latin-1, schema SQLite con WAL, Dashboard / Mensual / Configuración (read-only), 23 tests reconciliando hasta el céntimo. KPIs cuadran: Ingreso anual $15.014.431, Gasto $13.266.630, % fijo 28.47%, % variable 59.89%, % inv 9.06%, % resto 2.58%, Saldo CC $1.849.316,01.

### Fase 2 (mayo 2026) — Edit + features
Alta / edición / borrado en Transacciones. Tab Diario. Editor de categorías inline en Configuración. Saldo inicial editable. Fondo USD editable desde Dashboard. Export a Excel. Migración multi-user ready. Macro / subcategorías (Compra Divisa pasa a Inversion). Libro Diario (últimos N días). Backups automáticos en cada escritura.

### Fase 3 (mayo 2026) — Multi-user + deploy
- R1: bcrypt + módulo auth + login screen + setup_password script.
- R2: PKs compuestas + refactor de todas las queries en core/ para filtrar por user_id + onboarding para nuevos + signup habilitado.
- R3: Dockerfile + docker-compose + DEPLOY.md (con opción Oracle Cloud) + finalmente deploy a Fly.io. App name `radar-financiero`, región `gru` (São Paulo), volumen 1GB. Migración de la data local de Franco vía seed temporal en la imagen Docker (159 transacciones + usuario `franco` con password). Después se removió el seed y se redeployó limpio.

### Fase 4 (junio 2026) — UX iterativa
Tema visual + paleta semántica + template Plotly unificado + formato corto en KPIs + st.toast en confirmaciones + iconos en pestañas + containers con border en Dashboard + empty states amables + delta con signo explícito + barras de progreso en Mensual + editor de previsiones inline + parser de expresiones aritméticas en Importe + alta rápida (modo rápido + chips de motivos frecuentes + chips de montos recurrentes) + tutorial guiado (tour en 5 pasos) + onboarding cálido + rename a "Radar Financiero" + logo SVG + favicon + design system CSS + responsive mobile.

---

## 2026-05-12 · Premortem #1 (inicial)

8 modos de fallo identificados antes de empezar a construir. **Fallo más probable:** divergencia con el Excel viejo si Franco lo mantiene en paralelo. **Fallo más peligroso:** Caja no reconcilia el día 1 por la fila inicial "Caja" mal tratada como ingreso.

**Mitigaciones aplicadas:** tests de reconciliación obligatorios; categorías editables desde el día 1; schema con Caja calculada (no almacenada); backups por escritura.

---

## 2026-05-27 · Premortem #2 (módulo de inversiones)

12 modos de fallo identificados. **Fallo más probable:** la app termina exigiendo MÁS mantenimiento manual que el Excel actual (que ya tiene addin BYMADATA tirando precios solo). **Fallo más peligroso:** reconciliación con extracto del broker no cuadra + bonos mal calculados (bonos = 60% de la cartera de Franco). **Supuesto oculto:** "el Excel es manual, la app sería automática". FALSO.

**Recomendación firme:** NO reemplazar el Excel. Solo visualizar + integrar. El Excel sigue siendo fuente de verdad. Scope reducido al 70%.

---

## Hito original · Excel → app

El proyecto nació para reemplazar un Excel de seguimiento de gastos que Franco usaba en `C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\`. La premisa fue: si los KPIs no cuadran al céntimo con el Excel original, la app no sale. Esa premisa se sostiene hasta hoy (los tests de reconciliación son el gate del proyecto).
