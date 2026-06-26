# Mis Finanzas Personales

App web personal de seguimiento financiero, construida sobre **Streamlit + SQLite + Plotly + Python**. Reemplaza un Excel de gastos con una app multi-usuario deployada en la nube. La estética actual ("Cosmic Slate") es minimalista y de alta densidad de datos: fondo zinc-950, paneles zinc-900, acentos violeta, tipografía Inter + JetBrains Mono.

> **Estado:** en producción en Fly.io · multi-usuario · backups automáticos · datos privados del repo (cada usuario carga los suyos).

---

## ¿Qué hace?

- **Dashboard** con KPIs anuales y mensuales (Ingreso, Gasto fijo/variable, Inversión, Saldo cuenta corriente, Fondo emergencia USD), evolución de Caja con medias móviles configurables, Ingresos vs Gastos por mes, y donut de gastos por categoría.
- **Transacciones**: alta / edición / borrado con form, parser de expresiones aritméticas en el campo Importe (`5000 + 3200 - 200`), modo rápido con chips de motivos frecuentes y montos recurrentes.
- **Libro Diario**: vista cronológica de los últimos N días con saldo acumulado después de cada movimiento.
- **Mensual (Presupuesto)**: previsión vs realidad con barras de progreso semáforo + editor inline de previsiones + bulk "copiar al año".
- **Configuración**: editor de categorías inline (data_editor), borrado de motivos sin uso, saldo inicial editable, export a Excel con snapshot completo.
- **Auth** con bcrypt + signup gateado por código de invitación + rate-limit del login (5 fallos / 15 min → 5 min de bloqueo) + sesión "recordarme" con token firmado HMAC.
- **Multi-tenant** real: cada usuario ve solo sus propias transacciones, categorías y presupuestos.

## Stack

- **Backend:** Python 3.11, SQLite (modo WAL), bcrypt.
- **Frontend:** Streamlit ≥1.33, Plotly, pandas, openpyxl.
- **Tests:** pytest.
- **Deploy:** Docker + Fly.io (región `gru` São Paulo, volumen persistente para la DB).
- **Auth:** módulo propio (sin streamlit-authenticator).

## Estructura

```
.
├── app.py                    Entry point Streamlit (auth gate + tabs)
├── core/                     Lógica pura, testeable
│   ├── auth.py               hash bcrypt + verify + create_user + rate-limit
│   ├── budget.py             comparativa Previsión vs Realidad
│   ├── categorias.py         CRUD categorías + motivos_sin_uso
│   ├── categorizer.py        DEFAULT_CATEGORIAS + regla dual (Inversión↔Desahorro)
│   ├── current_user.py       contextvar de user_id activo (multi-tenant)
│   ├── db.py                 connect, init_db, migraciones M1-M5, backups
│   ├── diario.py             libro diario (últimos N días con saldo)
│   ├── export.py             snapshot a Excel
│   ├── ingest.py             import_diario / import_mensual / init_categorias (CLI)
│   ├── metrics.py            load_transactions, KPIs, caja_diaria_con_medias
│   ├── parsers.py            parse_currency, parse_date, parse_expression (safe ast)
│   ├── session_tokens.py     tokens HMAC para sesión persistente
│   └── transactions.py       CRUD transacciones + motivos_recientes
├── ui/                       Vistas Streamlit
│   ├── auth/login.py
│   ├── views/                dashboard, transacciones, diario, mensual, configuracion, onboarding
│   └── helpers/              _format, _theme, _html, _logo, _responsive, _styles, _tour
├── tests/
│   ├── test_kpis.py
│   ├── test_parsers.py
│   ├── test_premortem3.py
│   └── test_reconciliacion.py
├── scripts/
│   └── setup_password.py     CLI para setear / resetear password de un usuario
├── assets/                   Logo SVG + favicon
├── docs/                     Docs del proyecto (DEPLOY, MEJORAS-UX, RUNBOOK, premortems, RESUMEN-PROYECTO)
├── Dockerfile, fly.toml      Deploy
├── .env.example              Plantilla de variables de entorno
├── requirements.txt
├── README.md                 Este archivo
├── MEJORAS.md                Backlog priorizado
├── BITACORA.md               Changelog narrativo (qué se hizo cuándo y por qué)
└── LICENSE
```

## Quick start (desarrollo local)

```bash
# 1. Clonar
git clone https://github.com/<tu-usuario>/mis-finanzas-personales.git
cd mis-finanzas-personales

# 2. Entorno virtual
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Dependencias
pip install -r requirements.txt

# 4. Config local
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# Editá .env si necesitás (la app funciona con defaults).

# 5. Tests (deberían quedar verdes antes de tocar la UI)
pytest tests/ -v

# 6. Levantar Streamlit
streamlit run app.py
```

Abre en http://localhost:8501. La primera vez te lleva al signup; después al onboarding (saldo inicial + fondo USD); después al Dashboard.

## Deploy en Fly.io

Resumen rápido (la guía completa está en [`docs/DEPLOY.md`](docs/DEPLOY.md)):

```bash
fly auth login
fly launch --no-deploy      # genera fly.toml (ya está commiteado, podés saltear)
fly volumes create finanzas_data --region gru --size 1
fly secrets set SIGNUP_CODE=tu-codigo-de-invitacion
fly secrets set SESSION_SECRET=$(openssl rand -hex 32)
fly deploy
```

URL pública del deploy original: https://radar-financiero.fly.dev

> **El volume persiste entre deploys.** `fly deploy` reemplaza el código, NO toca `/app/data` (donde vive `finanzas.db` y los backups).

## Tests — el gate del proyecto

Tres archivos protegen los números:

```bash
# Reconciliación: Caja calculada == Caja del CSV original, ±$0.01 fila por fila.
pytest tests/test_reconciliacion.py -v

# KPIs: ingresos, gastos, fijos, variables, % de distribución cuadran con el Excel.
pytest tests/test_kpis.py -v

# Parsers: 30+ casos de parse_currency / parse_date / parse_expression.
pytest tests/test_parsers.py -v

# Premortem #3: rate-limit del login, retención de backups, taxonomía dual.
pytest tests/test_premortem3.py -v
```

Si algún test rojea, no confíes en los números de la app hasta resolverlo.

## Datos

- La DB local vive en `data/finanzas.db`.
- Cada escritura (insert / update / delete) dispara `backup_db()` que copia la DB a `data/backups/finanzas-YYYYMMDD-HHMMSS.db`. Política de retención: último de cada día por 30 días + los 10 más recientes (defensa contra borrado silencioso).
- **Nada de `data/` se commitea al repo.** Cada usuario tiene su propia DB local. La carpeta arranca vacía en clones nuevos.

## Privacidad / seguridad

- Repo público: la `.gitignore` excluye `.env`, `data/`, backups, y los CSVs originales con tus datos. Antes de un `git push` revisá con `git status` que no esté arrastrando nada raro.
- Auth con bcrypt (no se guarda la contraseña en claro).
- Signup deshabilitado salvo que `SIGNUP_CODE` esté definido en el entorno.
- Sesión opcional con token HMAC firmado (`SESSION_SECRET`); rotar el secret invalida todas las sesiones recordadas.
- Rate-limit del login en RAM del proceso.

## Documentación adicional

| Archivo | Para qué |
|---|---|
| [`README.md`](README.md) | Este archivo: qué es, cómo correr, cómo deployar. |
| [`MEJORAS.md`](MEJORAS.md) | Backlog priorizado de mejoras y features pendientes. |
| [`BITACORA.md`](BITACORA.md) | Changelog narrativo: qué se hizo, cuándo, y por qué. |
| [`docs/RESUMEN-PROYECTO.md`](docs/RESUMEN-PROYECTO.md) | Documento auto-contenido para retomar el proyecto en otra conversación. |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Guía paso a paso de deploy en Fly.io (y opción Oracle Cloud). |
| [`docs/RUNBOOK-OPERACION.md`](docs/RUNBOOK-OPERACION.md) | Operación: backups remotos, restore, monitoreo, billing. |
| [`docs/MEJORAS-UX.md`](docs/MEJORAS-UX.md) | Backlog original de UX (queda como referencia histórica). |
| [`docs/premortems/`](docs/premortems/) | Premortems aplicados al proyecto. |
| [`docs/README-LEGACY.md`](docs/README-LEGACY.md) | README original de Fase 1 (referencia histórica). |

## Licencia

MIT. Ver [`LICENSE`](LICENSE).
