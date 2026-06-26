# Mis Finanzas — App Personal de Seguimiento

App local en Streamlit para consolidar el seguimiento de gastos personales.
Lee tu `Diario.csv` + `Mensual.csv`, los importa a una base SQLite, y te
ofrece un dashboard con los mismos KPIs que ya tenías en Excel.

## Estado actual: Fase 2 completa

  * ✅ Ingesta de Diario.csv y Mensual.csv a SQLite
  * ✅ Dashboard con KPIs anuales/mensuales, medias móviles configurables,
        donut de gastos y gráfico Ingresos vs Gastos por mes
  * ✅ Tab Transacciones: alta, edición y borrado desde la UI con backup automático
  * ✅ Tab Diario: vista de los últimos N días sin agregación, con resumen por grupo
  * ✅ Tab Mensual: previsión vs realidad con totales separados
        (Ingresos / Gastos consumo / Inversión / Saldo mensual)
  * ✅ Tab Configuración: editor inline de categorías (grupo + subcategoría),
        creación / borrado de motivos, saldo inicial editable, export a Excel
  * ✅ Taxonomía jerárquica Motivo → Grupo → Subcategoría
        (Compra Divisa pasa a Inversion/Ahorro, Venta divisa a Ingreso/Desahorro)
  * ✅ Fondo USD editable desde Dashboard
  * ✅ Backups automáticos en cada escritura (`data/backups/`)
  * ✅ Schema multi-user-ready (columna `user_id`, tabla `usuarios`)
  * ✅ Tests de reconciliación de Caja y de KPIs
  * ⏳ Fase 3: signup + login multi-usuario, deploy a Oracle Cloud con Cloudflare Tunnel

## Quick start

```bash
# 1. Crear entorno virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Copiar config y ajustar
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux

# 4. Correr los tests primero (gate del MVP — DEBEN pasar antes de mirar la UI)
pytest tests/ -v

# 5. Importar los CSV a SQLite (primera vez)
python -m core.ingest

# 6. Levantar Streamlit
streamlit run app.py
```

La app abre en http://localhost:8501. La DB queda en `data/finanzas.db`.

## Tests — el gate del MVP

Si querés confiar en los números de la app, estos dos archivos tienen que pasar:

```bash
# Reconciliación de Caja: Caja calculada == Caja del CSV en TODAS las 146 filas (±$0.01)
pytest tests/test_reconciliacion.py -v

# KPIs: ingresos, gastos, fijos, variables, inversión, % cuadran con Mensual.csv (±$1)
pytest tests/test_kpis.py -v
```

Si algún test rojea: **NO uses los números de la app todavía**, hay un bug que tenemos
que resolver antes. La idea es que ningún cambio futuro pase silenciosamente.

## Estructura

```
App seguimiento de gastos/
├── Diario.csv, Mensual.csv      ← tus originales (no se tocan)
├── Diario.xlsx, Mensual.xlsx    ← tus originales (no se tocan)
│
├── app.py                       ← entry point Streamlit
├── core/                        ← lógica pura, testeable
│   ├── parsers.py               (moneda/fecha/encoding latin-1)
│   ├── db.py                    (schema SQLite + backups)
│   ├── categorizer.py           (Motivo → Grupo)
│   ├── ingest.py                (importa CSV → SQLite)
│   ├── metrics.py               (KPIs + evolución Caja)
│   └── budget.py                (Previsión vs Realidad)
├── ui/                          ← vistas Streamlit
│   ├── dashboard.py
│   ├── mensual.py
│   └── configuracion.py
├── tests/                       ← gates del MVP
│   ├── test_reconciliacion.py
│   └── test_kpis.py
├── data/                        ← creado en runtime
│   ├── finanzas.db
│   └── backups/                 ← en Fase 2
│
├── requirements.txt
├── .env.example
└── README.md (este archivo)
```

## Re-importación / reset

Si querés volver a importar desde cero (por ejemplo después de editar el CSV):

```bash
python -m core.ingest --force
```

Esto borra el contenido de `transacciones`, `presupuesto` y `configuracion`
en la DB y re-importa. Las tablas son recreadas en orden, sin perder el schema.

## Configuración (.env)

| Variable                | Default              | Qué hace                          |
|-------------------------|----------------------|-----------------------------------|
| `DB_PATH`               | `./data/finanzas.db` | Ruta a la DB SQLite               |
| `DIARIO_CSV`            | `./Diario.csv`       | Ruta al CSV diario (sólo ingest)  |
| `MENSUAL_CSV`           | `./Mensual.csv`      | Ruta al CSV mensual (sólo ingest) |
| `FONDO_EMERGENCIA_USD`  | `864`                | Saldo informativo USD             |
| `BACKUP_RETENTION`      | `30`                 | Cuántos backups conservar (Fase 2)|

## Categorización Motivo → Grupo

Está definida en `core/categorizer.py` y replica la taxonomía de tu Excel
para que los % coincidan exactamente:

  * **Ingreso**: Haberes Fundación, Haberes SBT, Haberes UCEMA, Otros ingresos, Venta divisa
  * **Gasto Fijo**: Auto, Servicios, Impuestos, Expensas, Pago tarjeta
  * **Gasto Variable**: Compras, Salidas, Viajes, Compra Divisa, Transportes
  * **Inversion**: Inversiones
  * **Saldo Inicial**: Caja (fila especial del 1/1, no es transacción)

Si más adelante decidís mover una categoría (ej. Auto a variable), por ahora
hay que editar `categorizer.py` y volver a correr `python -m core.ingest --force`.
En Fase 2 esto va a ser editable desde la UI.

## Troubleshooting

**"La DB ya tiene N transacciones. Usá --force..."**  
Ya importaste antes y no es seguro re-insertar sin borrar. Usá `--force`
si querés re-importar desde cero.

**"No se encontró fila de saldo inicial (motivo 'Caja')"**  
Tu CSV no tiene la fila inicial con motivo "Caja". La app asume saldo $0
y avisa. Editá el CSV o setear el saldo inicial desde la DB:

```bash
sqlite3 data/finanzas.db "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('saldo_inicial_caja', '101515.65')"
```

**Test de reconciliación falla en alguna fila**  
Significa que `parse_currency` o la lógica de Caja no maneja algún formato
nuevo en tu CSV. El test muestra qué fila, qué motivo, y qué diferencia hay.
Ese caso hay que agregarlo a los doctests de `core/parsers.py`.

**Saldo CC del dashboard ≠ extracto del banco**  
Si el test de reconciliación pasa pero tu extracto no cuadra: el CSV original
también difería. Compará Diario.csv ↔ extracto antes de echarle la culpa a la app.

## Categorías (Fase 2b)

Motivos están organizados en jerarquía Macro (`grupo`) → Subcategoría:

  * **Ingreso** → Sueldo (Haberes Fundación/SBT/UCEMA), Otros, Desahorro (Venta divisa)
  * **Gasto Fijo** → Movilidad (Auto), Hogar (Servicios, Expensas), Impuestos, Financiero (Pago tarjeta)
  * **Gasto Variable** → Consumo (Compras), Ocio (Salidas, Viajes), Movilidad (Transportes)
  * **Inversion** → Activos financieros (Inversiones), Ahorro y Resguardo (Compra Divisa)

La fórmula de % es disjunta: `fijo + variable + inversion + resto = 100%`.

**Regla dual**: si el motivo "Inversiones" aparece como ingreso (cobranza de
bonos, venta de activos), se reclasifica automáticamente a Ingreso/Desahorro.

Todo esto es editable desde Configuración → Editor de categorías.

## Roadmap

### Fase 3 (próxima): multi-usuario + deploy a Oracle Cloud
- Streamlit-Authenticator con signup/login/logout
- Tabla `usuarios` con password bcrypt
- Refactor: queries filtran por `current_user_id` (la columna ya existe)
- Onboarding para usuarios nuevos: form de saldo inicial + opción "subir mi CSV"
- Categorías per-usuario (cada uno arranca limpio o con DEFAULT_CATEGORIAS)
- Dockerfile + docker-compose para deploy reproducible
- Cloudflare Tunnel + Cloudflare Access (no abrir puertos al mundo)
- Backups automáticos a Oracle Object Storage (free tier)

### Post-Fase 3 (nice-to-have)
- Alertas tipo "Compras va 50% arriba del presupuesto del mes"
- Vista anual con métricas Q1 vs Q2
- Tracking USD↔ARS con tipo de cambio histórico
- Recategorización masiva (multi-select + cambio de motivo)

**Por qué no deploy directo desde Fase 1:** exponer la app a internet
requiere auth, HTTPS, backups remotos, multi-tenancy. El código está diseñado
para que ese deploy sea flip-of-a-switch (config por env vars, schema
preparado con user_id, sin paths hardcoded).

## Premortem

Antes de empezar a construir, corrimos un premortem que identificó 8 modos de
fallo potenciales. Los archivos viven en este mismo directorio:

  * `premortem-report-2026-05-12.html` — versión visual
  * `premortem-transcript-2026-05-12.md` — análisis completo

Las mitigaciones aplicadas:

  1. Tests de reconciliación fila-por-fila antes de cualquier UI
  2. Tests de KPIs vs Excel
  3. Categorías calibradas para matchear los % del Excel
  4. Parser robusto contra los 7 quirks detectados en el CSV real
  5. Caja no se almacena, se calcula (no puede haber desincronía interna)
  6. Schema con CHECKs para evitar grupos inválidos
  7. Importación idempotente con --force
  8. Scope estricto: sólo lectura en Fase 1

## Licencia

Uso personal. Sin garantías. Los números los chequeás vos.
