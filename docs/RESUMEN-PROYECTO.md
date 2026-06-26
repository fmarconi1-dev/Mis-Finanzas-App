# Resumen del proyecto Radar Financiero

> Documento auto-contenido para retomar el proyecto en otra conversación.
> Capturado en junio 2026.

---

## 1. Resumen ejecutivo en una página

**Qué es:** una app web personal de seguimiento financiero llamada
**Radar Financiero**, construida sobre **Streamlit + SQLite + Plotly + Python**.
Reemplaza un Excel de gastos que Franco usaba (carpeta original
`C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\App seguimiento de gastos`).

**Estado actual:** **deployada en producción en Fly.io**, multi-usuario, con
auth bcrypt, multi-tenant (queries filtradas por `user_id`), backups automáticos
en cada escritura, deploy reproducible vía Docker. URL pública:
**https://radar-financiero.fly.dev**.

**Stack:**
- Backend: Python 3.11, SQLite (modo WAL), bcrypt
- Frontend: Streamlit ≥1.30, Plotly, pandas, openpyxl
- Tests: pytest
- Deploy: Docker + Fly.io (región `gru` São Paulo, volumen persistente)
- Auth: módulo propio con bcrypt (no streamlit-authenticator)

**Características delivered:**
- Dashboard con KPIs (Ingreso anual/mes, Gasto fijo/variable, % distribución,
  Saldo cuenta corriente, Fondo emergencia USD), gráficos (evolución de Caja
  con medias móviles configurables, Ingresos vs Gastos por mes, donut por
  categoría).
- Tab Transacciones: alta/edición/borrado con form, parser de expresiones
  aritméticas en el campo Importe (`5000 + 3200 - 200`), modo rápido con chips
  de motivos frecuentes y montos recurrentes.
- Tab Diario: vista cronológica de los últimos N días con saldo después de
  cada movimiento.
- Tab Mensual: Previsión vs Realidad con barras de progreso (ProgressColumn)
  + editor de previsiones inline (data_editor + bulk "copiar al año").
- Tab Configuración: editor de categorías (data_editor inline), borrado de
  motivos sin uso, saldo inicial editable, export a Excel con snapshot completo.
- Autenticación: signup, login, logout, hash bcrypt.
- Onboarding para usuarios nuevos: form simple (saldo inicial + fondo USD).
- Tema visual: dark theme con paleta semántica (azul=ingreso, rojo=gasto,
  verde=inversión, ámbar=desahorro), template Plotly unificado, formato corto
  ($15,0M) en KPIs con exacto en hover.

---

## 2. Estructura de archivos

```
App seguimiento de gastos/
├── app.py                       # Entry point Streamlit + auth gate + tabs
├── Dockerfile                   # Imagen Python 3.11-slim + entrypoint
├── docker-compose.yml           # Servicio local opcional
├── .dockerignore                # Excluye data/, tests/, seed, etc.
├── docker-entrypoint.sh         # Siembra DB si está vacía (legacy de migración inicial)
├── fly.toml                     # Config Fly.io
├── requirements.txt
├── .env.example
├── .streamlit/
│   └── config.toml              # Tema visual (paleta, fondo, font)
├── core/                        # Lógica pura, testeable
│   ├── auth.py                  # hash_password, verify_password, authenticate, create_user
│   ├── budget.py                # comparativa_mes, presupuesto CRUD (upsert/delete/copy_year)
│   ├── categorias.py            # CRUD categorías (update/delete/insert) + motivos_sin_uso
│   ├── categorizer.py           # DEFAULT_CATEGORIAS, efective_grupo (regla dual)
│   ├── current_user.py          # contextvar para user_id (set en app.py post-login)
│   ├── db.py                    # connect, init_db, schema, migraciones M1-M4, backups
│   ├── diario.py                # libro_diario (últimos N días con saldo acumulado)
│   ├── export.py                # export_xlsx (snapshot completo)
│   ├── ingest.py                # import_diario, import_mensual, init_categorias, CLI
│   ├── metrics.py               # load_transactions, compute_kpis, caja_diaria_con_medias
│   ├── parsers.py               # parse_currency, parse_date, parse_expression
│   └── transactions.py          # CRUD transacciones + motivos_recientes + montos_frecuentes
├── ui/                          # Vistas Streamlit
│   ├── _format.py               # fmt_ars, fmt_ars_corto, fmt_usd, fmt_pct
│   ├── _theme.py                # paleta semántica + template Plotly
│   ├── configuracion.py
│   ├── dashboard.py
│   ├── diario.py
│   ├── login.py                 # login + signup tabs
│   ├── mensual.py
│   ├── onboarding.py            # pantalla de bienvenida nuevos
│   └── transacciones.py
├── tests/
│   ├── test_kpis.py             # parametrizado: 11 montos + 4 % vs valores esperados
│   ├── test_parsers.py          # 30+ casos del parser de expresiones
│   └── test_reconciliacion.py   # Caja calculada == Caja CSV ±$0.01 fila por fila
├── scripts/
│   └── setup_password.py        # CLI para setear/resetear password de un usuario
├── data/                        # Generada en runtime
│   ├── finanzas.db              # DB local
│   └── backups/                 # finanzas-YYYYMMDD-HHMMSS.db (retención: 30)
├── Diario.csv, Mensual.csv      # CSVs originales del Excel inicial (intactos)
└── docs y artefactos
    ├── README.md
    ├── DEPLOY.md                # Guía deploy Oracle Cloud + Cloudflare Tunnel
    ├── MEJORAS-UX.md            # Backlog completo de mejoras (sección por bloque)
    ├── premortem-report-2026-05-12.html / .md      # Premortem inicial app
    ├── premortem-inversiones-2026-05-27.html / .md # Premortem módulo inversiones
    └── RESUMEN-PROYECTO.md      # Este documento
```

---

## 3. Decisiones arquitectónicas clave (con razón)

1. **SQLite + WAL mode**: simple, gratis, sin servidor, persistente vía volumen
   en Fly. WAL permite lectores concurrentes mientras un proceso escribe.

2. **Caja NO se almacena, se calcula**: cada vez que se necesita el saldo CC se
   computa como `saldo_inicial + SUM(ingresos - pasivos)`. Decisión tomada en
   el premortem inicial para evitar que la DB tenga un "Caja stale" diferente a
   sus propias transacciones. Cualquier edit/alta/borrado de transacciones
   recalcula automáticamente todo.

3. **Multi-tenant via contextvar (`core/current_user.py`)**: el `user_id` se
   setea en `app.py` post-login y todas las queries en `core/` lo leen sin
   tener que pasarlo explícitamente. Excepción: callbacks de Streamlit corren
   en otro contexto — esos pasan `user_id` explícito desde `session_state`
   (ej. el callback del Fondo USD en Dashboard).

4. **bcrypt + auth custom**: no usamos `streamlit-authenticator` por dependencia
   pesada y porque controlamos mejor el flujo. ~150 líneas en `core/auth.py`.

5. **Schema multi-tenant desde Fase 2 con migraciones**: agregar `user_id` y
   PKs compuestas DESPUÉS de tener datos resultó ser más fácil de lo esperado
   por las migraciones idempotentes en `_migrate()`. **Lección:** migraciones
   incrementales ganan.

6. **Categorización con regla dual**: el motivo "Inversiones" se reclasifica
   automáticamente a "Ingreso / Desahorro" si aparece del lado del ingreso
   (cobranza de cupón, venta de activos). Implementado en
   `categorizer.efective_grupo()`.

7. **Fórmula del % resto preservada del Excel del usuario**: la fórmula del
   Excel resta inversión dos veces (`1 - %fijo - %variable - %inversion`). En
   nuestra Fase 2b cambiamos a buckets disjuntos: `fijo + variable + inversion
   + resto = 100%` con variable e inversion ya no superpuestos. Esto cambió
   los % visibles vs el Excel original — documentado en el código y el test
   actualizado.

8. **Parser de expresiones aritméticas safe (no `eval`)**: el campo Importe
   acepta `5000 + 3200 * 2` etc. Usa `ast.parse(..., mode='eval')` + walking
   con whitelist de operadores (`+ - * / ( )`, sin pow, sin nombres). Maneja
   formato argentino (`.` miles, `,` decimal). En `core/parsers.py`.

9. **Tests de reconciliación como gate del MVP**: antes de cualquier UI, los
   números tenían que cuadrar al céntimo con el CSV original. El test
   `test_reconciliacion.py` recorre las 146 filas y verifica
   `caja_calculada == caja_csv`. Sin esto verde no había dashboard.

10. **Cada escritura dispara backup automático**: `backup_db()` se llama tras
    cada insert/update/delete. Retención de los 30 más recientes en
    `data/backups/`.

---

## 4. Categorización (taxonomía actual)

**Estructura jerárquica Motivo → Grupo (macro) → Subcategoría.**

- **Ingreso** → Sueldo (Haberes Fundación / SBT / UCEMA), Otros, **Desahorro**
  (Venta divisa siempre; Inversiones cuando viene como ingreso vía regla dual).
- **Gasto Fijo** → Movilidad (Auto), Hogar (Servicios, Expensas), Impuestos,
  Financiero (Pago tarjeta).
- **Gasto Variable** → Consumo (Compras), Ocio (Salidas, Viajes), Movilidad
  (Transportes).
- **Inversion** → Activos financieros (Inversiones), Ahorro y Resguardo
  (Compra Divisa).
- **Saldo Inicial** → Caja (fila especial del 1/1, no es transacción).

**Defaults para usuarios NUEVOS** (`DEFAULT_CATEGORIAS_NEW_USER` en
`categorizer.py`): set genérico sin los "Haberes Fundación/SBT/UCEMA" específicos
de Franco. Tiene "Sueldo" genérico, Salidas, Compras, etc.

**Defaults para Franco (legacy)**: `DEFAULT_CATEGORIAS` mantiene los Haberes
específicos para el seed inicial de su data.

**Onboarding actual**: NO siembra categorías. El nuevo usuario arranca con
mapping vacío y las crea desde Configuración o al cargar transacciones (cada
motivo nuevo se crea como "Sin categorizar").

---

## 5. Migraciones de schema (M1 a M4)

Implementadas en `core/db.py::_migrate()`, idempotentes, corren en cada
`init_db()`.

- **M1 (Fase 2):** agrega columna `user_id INTEGER NOT NULL DEFAULT 1` a las
  tablas de datos + crea tabla `usuarios` + siembra usuario `local` (id=1) que
  Franco después renombró a `franco`.
- **M2 (Fase 2b):** agrega columna `subcategoria TEXT` a `categorias`.
- **M3 (Fase 2b):** mueve Compra Divisa de `Gasto Variable` a `Inversion`
  (UPDATE condicional, sólo si todavía está en el grupo viejo, para no pisar
  cambios manuales del usuario). Y agrega subcategoría `Desahorro` a Venta
  divisa.
- **M4 (Fase 3 R2):** PKs compuestas con `user_id` en `categorias`,
  `presupuesto` y `configuracion` (SQLite no permite alterar PK, así que
  recrea las tablas preservando los datos).

---

## 6. Fases delivered y resultados clave

### Fase 1 (MVP, mayo 2026): read-only
- Parser CSV con encoding latin-1, formato argentino, casos borde.
- Schema SQLite con WAL.
- Dashboard, Mensual, Configuración (read-only).
- 23 tests reconciliando hasta el céntimo con el Excel original.
- KPIs cuadran exactos: Ingreso anual $15.014.431, Gasto $13.266.630, % fijo
  28.47%, % variable 59.89%, % inv 9.06%, % resto 2.58%, Saldo CC $1.849.316,01.

### Fase 2 (mayo 2026): edit + features
- Tab Transacciones con alta/edición/borrado.
- Tab Diario.
- Editor de categorías inline en Configuración.
- Saldo inicial editable, fondo USD editable desde Dashboard.
- Export a Excel.
- Migración multi-user ready (sin filtrar todavía).
- Macro/subcategorías (Compra Divisa pasa a Inversion).
- Fórmula disjunta de KPIs (nueva taxonomía cambia los %).
- Libro Diario (últimos N días).
- Backups automáticos en cada escritura.

### Fase 3 (mayo 2026): multi-user + deploy
- **R1:** bcrypt + módulo auth + login screen + setup_password script.
- **R2:** PKs compuestas + refactor de TODAS las queries en core/ para filtrar
  por user_id + onboarding para nuevos + signup habilitado.
- **R3:** Dockerfile + docker-compose + DEPLOY.md (Oracle Cloud option) +
  finalmente deploy a **Fly.io** (más simple). App name `radar-financiero`,
  región `gru` (São Paulo), volumen 1GB. Migración de la data local de Franco
  vía seed temporal en la imagen Docker (159 transacciones + usuario `franco`
  con password). Después se removió el seed y se redeployó limpio.

### Fase 4 (en progreso, junio 2026): UX y features
Hecho:
- Tema visual (`.streamlit/config.toml`).
- Paleta semántica (`ui/_theme.py`).
- Template Plotly unificado.
- Formato corto en KPIs (fmt_ars_corto).
- st.toast en confirmaciones.
- Iconos en pestañas.
- Containers con border en Dashboard (jerarquía visual).
- Empty states amables.
- Delta con signo explícito (+/-) para colores.
- Barras de progreso (ProgressColumn) en Mensual.
- Editor de previsiones inline + bulk "copiar al año".
- Parser de expresiones aritméticas en Importe.
- Alta rápida: modo rápido (toggle) + chips de motivos frecuentes + chips de
  montos recurrentes.

Pendiente:
- **Tutorial guiado simple** (4.1 b): empezado pero no terminado. Diseño:
  panel contextual por pestaña, `tutorial_completado` en config, 5 pasos
  lineales. Archivos planeados: `ui/_tour.py` (nuevo) + ediciones en
  `onboarding.py` y cada `ui/<tab>.py` para llamar `render_tour_panel("...")`
  al inicio de su `render()`.
- Rediseño onboarding más cálido (4.1 a): 1-2 hs.
- Design system CSS custom (4.2): 1 día completo.
- Toggle claro/oscuro (4.4): 1 hs, bajo impacto.

---

## 7. Premortems realizados

### Premortem #1: Inicial (mayo 2026)
- Archivos: `premortem-report-2026-05-12.html` + `premortem-transcript-2026-05-12.md`
- 8 modos de fallo identificados.
- Fallo más probable: divergencia con el Excel viejo si Franco lo mantiene en
  paralelo.
- Fallo más peligroso: Caja no reconcilia el día 1 por la fila inicial "Caja"
  mal tratada como ingreso.
- **Acciones aplicadas:** tests de reconciliación obligatorios, categorías
  editables desde el día uno, schema con Caja calculada en vez de almacenada,
  backups por escritura.

### Premortem #2: Módulo de Inversiones (mayo 2026)
- Archivos: `premortem-inversiones-2026-05-27.html` + `premortem-inversiones-2026-05-27.md`
- 12 modos de fallo identificados.
- Fallo más probable: la app termina exigiendo MÁS mantenimiento manual que el
  Excel actual (que ya tiene addin BYMADATA tirando precios solo).
- Fallo más peligroso: reconciliación con extracto del broker no cuadra +
  bonos mal calculados (bonos = 60% de la cartera de Franco).
- Supuesto oculto: "el Excel es manual, la app sería automática". FALSO.
- **Recomendación firme:** **NO reemplazar el Excel.** Visualizar + integrar.
  El Excel queda como fuente de verdad para la cartera; la app importa el CSV
  "Movimientos Procesado" y agrega un dashboard + reconciliación broker ↔
  cuenta corriente personal. Scope reducido ~70%.

---

## 8. Backlog priorizado (de MEJORAS-UX.md)

| # | Item | Esfuerzo | Cuándo |
|---|---|---|---|
| 4.1.b | Tutorial guiado simple (empezado) | 3-4 hs | **Próximo** |
| 4.1.a | Onboarding más cálido | 1-2 hs | Después |
| 4.2 | CSS custom design system | 1 día | Cuando haya tiempo grande |
| 4.4 | Toggle claro/oscuro | 1 hs | Bajo impacto |
| 8 | Chatbot WhatsApp | 3-5 días | Cuando crezca uso real |
| 9 | Cartera inversiones (visualizador) | 1 fin de semana | Final del roadmap, segundo premortem antes |
| 10 | Monetización | Diferido | Después de 5-10 usuarios activos |

**Sobre monetización (sección 10 de MEJORAS-UX):** la conclusión es que **NO
poner publicidad** en una app de finanzas (mata confianza, regulatorio,
matemática no cierra). Mejor freemium / una compra / suscripción cuando llegue
el momento. Por ahora, no monetizar hasta tener 5-10 usuarios activos.

**Sobre el chatbot (sección 8):** originalmente Telegram, después corregido a
WhatsApp por adopción argentina. WhatsApp Business Cloud API tier gratis hasta
1000 conversaciones/mes. Arquitectura recomendada: FastAPI embebido en la
misma máquina Fly + webhook. Requiere número dedicado verificado en Meta
Business.

---

## 9. Deploy y mantenimiento

### URL pública
**https://radar-financiero.fly.dev**

### Comandos típicos
```powershell
# Activar venv local
cd "C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\App seguimiento de gastos"
.venv\Scripts\activate

# Tests
pytest tests/ -v

# Probar local
streamlit run app.py

# Deploy a producción
fly deploy

# Ver logs producción
fly logs -a radar-financiero

# Acceso SSH
fly ssh console -a radar-financiero

# Verificar datos en cloud
fly ssh console -a radar-financiero -C "ls -la /app/data"
```

### Volumen persistente
- Nombre: `finanzas_data` (1GB)
- Mount: `/app/data` en el contenedor
- Contiene: `finanzas.db` + carpeta `backups/`
- **CRÍTICO:** `fly deploy` NO toca este volumen. El código se reemplaza, la
  data persiste.

### Auth
- Usuario único actual: `franco` (id=1) con password seteado vía
  `scripts/setup_password.py`.
- Signup habilitado en el login. Cada usuario nuevo arranca con base vacía
  (multi-tenant real).
- Sesión vía `st.session_state` (no JWT externo).

### Warning conocido
- `fly deploy` siempre tira warning "not listening on 0.0.0.0:8501". Es
  **cosmético**: Streamlit tarda 5-9s en bootear y el smoke check de Fly lo
  prueba antes. La app sí arranca, confirmable en `fly logs`. Tenemos
  health_service.checks con `grace_period = "30s"` pero el warning del smoke
  check no se puede silenciar fácilmente.

---

## 10. Estado de la base de datos local vs cloud (junio 2026)

- **Local** (`data/finanzas.db`): 165 transacciones, última 27/5/2026. Quedó
  desactualizada porque Franco cargó nuevas vía el sitio cloud.
- **Cloud** (volumen Fly): fuente de verdad actual. Tiene transacciones
  posteriores al 27/5.
- **No hay riesgo de pisar la cloud al deployar**. El volumen es persistente y
  el entrypoint chequea si la DB tiene >0 transacciones antes de sembrar (no
  siembra si ya hay data).

---

## 11. Cómo continuar (recomendación concreta para retomar)

1. **Verificar el estado actual:**
   ```powershell
   fly ssh console -a radar-financiero -C "python -c \"import sqlite3; c=sqlite3.connect('/app/data/finanzas.db'); print('TXNS:', c.execute('SELECT COUNT(*) FROM transacciones WHERE user_id=1').fetchone()[0]); print('ULTIMA:', c.execute('SELECT fecha, motivo FROM transacciones WHERE user_id=1 ORDER BY fecha DESC, id DESC LIMIT 1').fetchone())\""
   ```

2. **Próxima feature recomendada:** completar el tutorial guiado simple.
   Implementación pendiente:
   - Crear `ui/_tour.py` con: `start_tour()`, `finish_tour()`,
     `is_tour_active()`, `render_tour_panel(tab_name)`.
   - Estados: `tutorial_completado` en `configuracion` (None = pre-tutorial
     user, "0" = tour activo, "1" = completado).
   - 5 pasos: dashboard → transacciones → diario → mensual → configuracion.
   - Cada paso: panel con título, body explicativo, botones "Listo, siguiente →"
     y "Saltar tutorial". El último paso: "🎉 Finalizar".
   - En `onboarding.py` post-submit: llamar `start_tour()`.
   - En cada `ui/<tab>.py::render()`: primer línea `render_tour_panel("...")`.

3. **Después del tutorial:** decidir entre CSS custom (4.2), chatbot WhatsApp,
   o módulo de inversiones (con segundo premortem antes).

---

## 12. Convenciones / "voz" del proyecto

- **Idioma:** español de Argentina (formal pero informal: vos, no usted).
- **Microcopy:** segunda persona, alentador, tono de pareja técnica
  ("dale, vamos con esto", "te dejo armado X").
- **Premortem como herramienta:** se aplicó antes del proyecto inicial y antes
  de la feature de inversiones. Sirve para identificar fallos antes y ajustar
  el plan.
- **Tests como gate:** ninguna feature financiera va a UI sin tests verdes
  primero. Reconciliación al céntimo es no negociable.
- **Backups en cada escritura:** consistente en todo el código.
- **Ahorro de tokens:** durante las conversaciones, respuestas concisas,
  sin re-explicar contexto, sin headers innecesarios. Esto se adoptó como
  hábito desde principios del proyecto.

---

## 13. Datos del usuario para retomar

- **Nombre:** Franco Marconi
- **Email:** fmarconi1@gmail.com
- **Username en la app:** `franco` (id=1)
- **Sistema:** Windows con PowerShell, venv en `.venv/`
- **Editor:** Notepad / VSCode equivalente
- **Carpeta del proyecto:** `C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\App seguimiento de gastos`
- **Broker que usa:** Inviu (Argentina)
- **Cartera de inversiones:** en USD ~14.500, diversificada en bonos USD,
  CEDEARs, acciones argentinas, BTC, cauciones. Tracked en
  `C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\Inversiones.xlsx`
  (16 hojas, 600+ movimientos procesados, addin BYMADATA para precios).

---

## 14. Pasos para retomar en una conversación nueva

1. Abrí este documento (`RESUMEN-PROYECTO.md`) y compartilo con Claude.
2. Decile: "estoy retomando este proyecto, leé el resumen y orientate".
3. Pedile que verifique el estado actual con `fly logs` o consultas a la DB
   antes de proponer cambios.
4. Continúa con lo que esté pendiente del backlog (sección 8).

Cualquier dato concreto que necesite cualquier conversación nueva está acá o en
los archivos referenciados (`MEJORAS-UX.md`, `DEPLOY.md`, los dos premortems).

---

## 15. Changelog — Premortem #3 y hardening (11/6/2026)

Se corrió un premortem sobre la app completa (`premortem-report-2026-06-11.html`
+ transcript). 8 modos de fallo. Cambios aplicados (76 tests verdes, 18 nuevos
en `tests/test_premortem3.py`):

- **R2** `core/db.py`: retención de backups por EDAD (último de cada día por
  30 días + 10 más recientes), ya no "los 30 últimos".
- **R3** `core/budget.py`: `comparativa_mes` ahora clasifica fila a fila con
  `efective_grupo` (nueva `realidad_mensual_efectiva`). Fix del bug F6: una
  venta de "Inversiones" desaparecía de la pestaña Mensual.
- **R4** `core/metrics.py` + `ui/dashboard.py`: `anios_con_datos` /
  `filtrar_anio` + selector de año en Dashboard. Fix de la "bomba de año
  nuevo" (KPIs anuales sumaban toda la historia).
- **R5** `ui/login.py` + `core/auth.py`: signup cerrado salvo que exista
  `SIGNUP_CODE` (código de invitación) + rate-limit de login (5 fallos/15 min
  → 5 min de bloqueo).
- **R6** `core/db.py`: migración **M5** — user_id sin DEFAULT en las 4 tablas;
  un INSERT sin user_id lanza IntegrityError (antes caía silencioso en id=1).
- **R8** `Dockerfile`: usa `requirements.lock` si existe (generarlo: runbook §4).
- **R9** `core/session_tokens.py` + `app.py` + `ui/login.py`: sesión
  persistente con token HMAC en URL, activa sólo si `SESSION_SECRET` está
  seteado.
- **R1/R7/R10** `scripts/backup_remoto.ps1` + `RUNBOOK-OPERACION.md`: backup
  externo diario a la PC, ensayo de restore, monitoreo, billing.

**Pendiente de Franco (no automatizable desde acá):** correr el primer
`backup_remoto.ps1`, programarlo en Task Scheduler, setear secrets
(`SIGNUP_CODE`/`SESSION_SECRET`), crear monitor de uptime, generar
`requirements.lock`, ensayar UN restore, y `fly deploy`. Todo en el runbook.

---

## 16. Changelog — Fixes producción + nuevo helper st.html (26/6/2026)

Después del deploy de la Fase 4 (rename a Radar Financiero + logo + design
system + responsive), aparecieron 3 bugs en producción que mobile screenshot
mostró:

1. **HTML inline renderizado como texto literal** (login hero, onboarding hero,
   saludo del dashboard). Causa: en Streamlit ≥1.41, `st.markdown(html,
   unsafe_allow_html=True)` deja de renderizar inline tags (`<div>`, `<p>`,
   `<h1>`) y los escapa como texto. Los `<style>` SÍ pasan (por eso los
   containers/botones con CSS sí se veían lindos).
2. **TypeError `'text/html' is not a valid JavaScript MIME type`** en
   Transacciones. Causa: `st.logo("assets/logo.svg")` intentando cargar el SVG
   como módulo JS y el server respondía `text/html`.
3. **Donut de gasto por categoría con etiquetas solapadas en mobile**
   (`textposition="outside"` no entra en viewport de 375px).

**Fixes aplicados:**

- Nuevo módulo `ui/_html.py` con helper `render_html(html)` que usa
  `st.html()` cuando está disponible (Streamlit ≥1.33) y cae a
  `st.markdown(unsafe_allow_html=True)` para versiones viejas.
- `ui/_responsive.py` y `ui/_styles.py` migrados a `render_html()`.
- Login y onboarding: el hero usa `render_logo()` (nuevo en `ui/_logo.py`,
  dibuja el SVG como `st.image()` centrado en 3 columnas, sobrevive al
  sanitizer de DOMPurify de `st.html()`). El resto del hero (h1 + tagline) va
  vía `render_html()`.
- Dashboard: el saludo "👋 Hola, **Franco**" pasó a `st.markdown()` puro
  (markdown nativo, sin HTML inline).
- `app.py`: removido `try_set_logo()` (causaba el TypeError). `page_icon`
  cambiado de `assets/logo.svg` a `🎯` (evita el mismo problema en el
  favicon).
- Donut: `textposition="inside"` + `textinfo="percent"` +
  `insidetextorientation="radial"` + leyenda horizontal abajo. Hover muestra
  nombre + monto + %.
- `requirements.txt`: `streamlit>=1.33.0` (antes 1.30.0) para garantizar
  `st.html`.

**Inventario de archivos tocados:**
`ui/_html.py` (nuevo), `ui/_logo.py`, `ui/_responsive.py`, `ui/_styles.py`,
`ui/login.py`, `ui/onboarding.py`, `ui/dashboard.py`, `app.py`,
`requirements.txt`.

**Lección reusable:** en Streamlit moderno, separar SIEMPRE:
- CSS injection → `st.html()` (vía `render_html`).
- HTML inline complejo con `<div>` `<p>` `<h1>` → `st.html()` (vía
  `render_html`), pero ojo: el sanitizer remueve `<svg>` inline y `<script>`.
- SVG/imágenes → `st.image()` con archivo en disco. NUNCA `st.html()` con
  `<svg>` inline.
- Texto simple con formato → `st.markdown()` nativo, sin HTML.

---

## 17. Premortem #4 — Decisión: ¿migrar a React+Firestore+Gemini? NO. (26/6/2026)

Franco compartió un proyecto paralelo (repo `fmarconi1-dev/Mis-Finanzas-app`,
no accesible públicamente) con stack React 18 + Vite + Express + Firebase
Auth + Firestore + Gemini 2.5 Flash. Estética "Cosmic Slate" (Inter +
JetBrains Mono, paleta zinc + violeta + esmeralda, layout Bento Box). Features
nuevas: Asistente de Preservación IA en dashboard, Importador Cognitivo de
CSV (LLM mapea esquemas arbitrarios), tiempo real vía Firestore.

Adjuntó también un snippet `ai_studio_code.ts` con endpoints externos
`GET /api/external/financial-summary` y `POST /api/external/add-transaction`
protegidos por `EXTERNAL_IA_TOKEN`.

**Premortem aplicado** (asumir falló a 6 meses, trabajar hacia atrás).

**11 modos de fallo para "migrar":**

1. Bola de nieve de costos Firestore + Gemini ($0 → $25-60/mes).
2. Migración de datos SQLite→Firestore rompe reconciliación de KPIs.
3. Vendor lock-in de Firebase (auth rules + security rules + hosting).
4. Reglas de Firestore sutilmente buggy → otro usuario lee tus transacciones.
5. Token `EXTERNAL_IA_TOKEN` filtra (commit, log Gemini, screenshot) → escritura externa hostil.
6. Gemini misclassifica filas en el importador → silent failure de KPIs.
7. El dossier es generado por LLM, no código verificable.
8. Surface area 5x más grande (React + Express + Firebase config + prompts).
9. Premortem #3 (rate-limit + SIGNUP_CODE + SESSION_SECRET) hay que rehacerlo entero.
10. "Tiempo real" de Firestore no aplica a un único usuario por workspace.
11. Reset de momentum: bugs que hoy se arreglan en horas pasan a días.

**5 modos de fallo para "quedarse":**

1. Techo estético de Streamlit.
2. Mobile aceptable pero no premium.
3. Sin agente conversacional para cargar (mitigable con FastAPI sidecar).
4. SQLite techo en 10-20 usuarios concurrentes (hoy somos 1-3).
5. Estancamiento por aburrimiento si lo que motivó del proyecto paralelo es
   aprender React/TS/Firebase.

**Decisión: NO migrar el stack.** Plan híbrido escalonado:

- **M1 (1-2 días):** trasladar paleta "Cosmic Slate" + tipografías Inter +
  JetBrains Mono al `_styles.py` actual. Sin riesgo, alto impacto visual.
- **M2 (1 día):** subcategorías visibles en UI (Transacciones + donut
  Dashboard). Ya existen en `categorizer.py`.
- **M3 (3-5 días, OPCIONAL):** importador inteligente de CSV con LLM, pero
  OFFLINE (script local), no en hot path del dashboard. Output revisable
  antes de impactar la DB.
- **M4 (1 semana, OPCIONAL):** sidecar FastAPI en el mismo Fly machine,
  escribiendo a la misma SQLite, con token rotable + rate-limit + validación
  Pydantic + log de auditoría. Endpoints `GET /summary` y `POST /transaction`.
  Esto cubre el caso de uso del archivo `ai_studio_code.ts` sin migrar nada.

**Trigger para reconsiderar:** 20+ usuarios activos pagando, o feature
específica cuantificable bloqueada por Streamlit (no "el look").

**Lo que NO se debe hacer:** llevar el snippet `ai_studio_code.ts` tal cual a
producción. Necesita: validación Pydantic del body, rate-limit por IP, log de
auditoría, rotación de token, restricción de `tipo` al enum válido.

**Esta decisión vale hasta que cambie alguna premisa.** Si Franco arma un MVP
del nuevo stack y lo prueba en paralelo 1 mes, la comparación se vuelve
factual y se puede rever sin compromisos.

---

## 18. Cosmic Slate aplicada + review del grupo familiar (26/6/2026)

Franco compartió el zip del proyecto paralelo (`Mis-Finanzas-app-main.zip`).
Lectura completa del código real (no solo el dossier):

### 18.1 Hallazgos críticos del proyecto paralelo
- **`firestore.rules` está abierto al mundo:** `allow read, write: if true;`.
  Confirma exactamente el modo de fallo #4 del premortem (anyone con el
  Firebase config lee/escribe TODO).
- **El "login" no usa Firebase Auth:** un sistema simple en colección `users`
  + localStorage. Hash de password sí, pero sin Firebase Auth real.
- **`miembroActivo` NO es identidad:** es un dropdown libre. La transacción
  guarda `creadoPor = miembroActivo` como etiqueta, sin verificación.
- **Código de invitación predecible:** `FAM-<4 chars>-<100-999>` = 900
  combinaciones por prefijo. Brute-force trivial.
- **Miembros hardcodeados** en el seed (`['Papá', 'Mamá', 'Juan']`).

### 18.2 Modelo de grupo familiar (a portar a SQLite, próximo turno)

Cómo funciona el feature en la app paralela:
- Cada `Usuario` tiene `personalWorkspaceId` + `familyWorkspaceId` (opcional)
  + `activeWorkspaceId` que alterna.
- La familia tiene una lista de **etiquetas de miembros** (strings libres) y
  `miembroActivo` es la que firma las transacciones nuevas (queda en
  `Transaccion.creadoPor`).
- Persistencia: colecciones `workspaces`, `family_codes`, y un campo
  `workspaceId` en cada `transactions`/`categories`/`budgets`.
- Flujos: crear familia genera código `FAM-XXXX-NNN`; unirse busca el código;
  salir limpia campos family; el switcher en Header cambia el workspace
  activo; otro selector cambia el miembro activo dentro del familiar.

**Boceto del modelo SQLite propuesto** (NO ejecutado todavía, requiere
premortem propio):
```
workspaces(id, owner_user_id, kind, nombre, invitation_code_hash,
           saldo_inicial, fondo_usd, created_at)
workspace_members(workspace_id, user_id, role, member_label, joined_at)
-- transacciones: cambia user_id → workspace_id (+ creado_por_member_label)
-- categorias / presupuesto / configuracion: idem workspace_id
```

**Endurecimientos respecto a la app paralela:**
- Código de invitación: `secrets.token_urlsafe(8)` + hash en DB. Match por
  hash, nunca por valor crudo.
- `member_label` editable (no hardcoded a `['Papá', 'Mamá', 'Juan']`).
- UI deja claro que "firmar como" es etiqueta cosmética, no auth de
  permisos: cualquier miembro autenticado puede editar transacciones del
  workspace.

### 18.3 M1 Cosmic Slate APLICADO (este turno)

Adoptada la paleta sin tocar la semántica financiera (azul=ingreso,
rojo=gasto, verde=inversión, ámbar=desahorro — alineada con el original).
Archivos tocados:

- **`.streamlit/config.toml`:** `primaryColor #6ee7b7 → #8B5CF6` (violeta IA),
  `backgroundColor #0e1117 → #09090B`, `secondaryBackgroundColor #1a2030 →
  #18181B`, `textColor #e8ecf4 → #E4E4E7`. Comentado el mapping de tokens
  para futuras referencias.
- **`ui/_theme.py`:**
  - `COLOR_ACENTO #6ee7b7 → #8B5CF6` (violeta).
  - `COLOR_GASTO/VARIABLE #f87171 → #F43F5E` (rose-500 Cosmic Slate).
  - `COLOR_INVERSION #34d399 → #10B981` (emerald-500 Cosmic Slate).
  - `COLOR_NEUTRO #9aa3b8 → #A1A1AA` (zinc-400).
  - Template Plotly: gridcolor `#1a2030 → #27272A` (zinc-800), tipografía
    Inter para textos y JetBrains Mono en hover.
- **`ui/_styles.py`:** rewrite completo. Tokens CSS `--cs-*` documentados.
  Carga Inter + Space Grotesk + JetBrains Mono desde Google Fonts. Selectores
  data-testid actualizados:
  - Métricas: fondo zinc-900 con borde fino, hover acento violeta.
  - Botones primarios: gradient violet→indigo + glow al hover.
  - Containers/expanders: zinc-900 + border zinc-800.
  - Inputs: focus ring violeta.
  - Tabs: indicador violeta abajo.
  - Sidebar: fondo más oscuro (#0A0A0C) con border zinc-800.
  - Code blocks: violeta sobre zinc-950.
  - Scrollbar Cosmic Slate.

**Pendiente verificar en producción:** sin captura de cómo quedó. Próximo
`fly deploy` lo va a mostrar. Si los `data-testid` cambiaron entre versiones
de Streamlit, hay que ajustar selectores — el helper de tokens CSS `--cs-*`
deja eso a 1 búsqueda + reemplazo.

### 18.4 Lo que sigue (orden recomendado)

1. **Deploy M1** y verificar visualmente en mobile + desktop. Si hay drift de
   selectores, ajustar.
2. **Premortem específico** del cambio de schema multi-workspace (toca
   migraciones + todas las queries del core + datos reales en producción).
3. **M2 grupo familiar** detrás del premortem: tablas `workspaces` +
   `workspace_members`, migración M6 (transacciones.user_id → workspace_id),
   UI de creación/unión/salida en Configuración, switcher en sidebar,
   selector de "firmar como" en Transacciones.
4. **M3 subcategorías visibles** (1 día).
5. **M4 importador inteligente offline** (opcional).
6. **M5 FastAPI sidecar** (opcional).
