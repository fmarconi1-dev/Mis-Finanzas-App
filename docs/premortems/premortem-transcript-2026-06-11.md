# Premortem #3 — Radar Financiero (app completa)
**Fecha:** 11 de junio de 2026
**Objeto:** todo lo construido hasta la fecha (Fases 1–4 parcial, deploy en Fly.io, multi-user)
**Método:** revisión íntegra del código + premortem Klein con 8 agentes de análisis profundo en paralelo

---

## 1. Contexto recopilado

- **Qué es:** Radar Financiero, app web personal de finanzas (Streamlit + SQLite + Plotly), deployada en https://radar-financiero.fly.dev, multi-tenant con signup abierto. Único usuario real: `franco` (id=1).
- **Para quién:** Franco como usuario principal; eventualmente 5–10 usuarios conocidos.
- **Éxito:** Franco confía en la app como registro financiero principal durante años; los números cuadran al céntimo entre todas las vistas; los datos sobreviven a cualquier incidente.

### Verificación técnica previa (11/6/2026)
- 58 tests pasan (parsers, KPIs, reconciliación). Cero tests de multi-tenant, auth, presupuesto o callbacks.
- DB local: 1 usuario, desactualizada (última txn 27/5). La cloud es la única fuente de verdad.
- Carpeta `data/backups/` local: 24 backups; el 18/5 se generaron 10 en ~5 minutos → la retención por cantidad (30) da una ventana de recuperación de minutos, no de días.
- Hallazgos de la revisión de código (resumen):
  - `compute_kpis` suma **toda la historia** sin filtro de año; "Ingreso anual" deja de ser anual el 1/1/2027.
  - La regla dual de "Inversiones" se aplica en Dashboard/Diario pero **no** en Mensual (`comparativa_mes` usa `load_categorias_map` plano; el lado ingreso de una venta de activos no aparece).
  - `MOTIVOS_DUAL_DESAHORRO = {"Inversiones"}` hardcodeado al string exacto.
  - Todas las columnas `user_id` tienen `DEFAULT 1` (la cuenta de Franco): un INSERT sin user_id contamina silenciosamente sus datos.
  - DB y backups comparten el mismo volumen Fly de 1GB; no existe copia externa automática.
  - `backup_db()` por cada escritura amplifica ×31 el uso de disco y permite que cualquier usuario/bot lo dispare.
  - Signup abierto sin captcha/verificación/rate-limit; login sin rate-limit.
  - `requirements.txt` con rangos abiertos, sin lockfile: cada build instala lo último.
  - Sesión solo en `st.session_state`: cada refresh = re-login; máquina con auto_stop = cold start.
  - Restore jamás ensayado; archivos sueltos confusos (`seed_finanzas.db-wal`, `finanzas.db.pre-r2-bak`, `4.1.0`, `.fuse_hidden*`).

---

## 2. Premortem en bruto — 8 modos de fallo

1. **F1 — Pérdida total de datos:** DB + los 30 backups en el mismo volumen único de Fly (sin réplica, sin copia externa); el volumen muere / la cuenta se suspende y desaparece el historial completo.
2. **F2 — Abandono por fricción de carga:** carga manual + cold start + re-login en cada visita; el costo diario supera el beneficio; el dashboard queda desactualizado y Franco vuelve al Excel.
3. **F3 — Bomba de año nuevo:** los KPIs "anuales" mezclan 2026 + 2027 a partir del 1/1; promedios diluidos, % sin sentido, dashboard que "miente".
4. **F4 — Signup abierto sin defensas:** bots crean cuentas, inflan la DB, el backup-por-escritura multiplica ×31 y llena el volumen de 1GB; o brute force al login sin rate-limit.
5. **F5 — Fuga multi-tenant silenciosa:** `DEFAULT 1` + contextvar que no llega a callbacks; datos ajenos caen en la cuenta de Franco sin error visible.
6. **F6 — Números que no cuadran entre pestañas:** la regla dual aplicada en Dashboard pero no en Mensual; una venta de inversiones aparece distinto (o desaparece) según la vista.
7. **F7 — Backups que no rescatan:** retención por cantidad → ventana de minutos; restore nunca ensayado; copia local meses vieja.
8. **F8 — Erosión silenciosa de plataforma:** pricing/billing de Fly, tarjeta vencida, deploy con dependencia nueva que rompe; sin monitoreo, nadie se entera por días/semanas.

---

## 3. Análisis profundos (8 agentes en paralelo)

### F1 — Pérdida total e irrecuperable de datos

**La historia del fallo.** Es el 14 de octubre de 2026. Franco lleva nueve meses cargando cada gasto en Radar Financiero, y hace tres meses que ni abre el Excel. Esa madrugada, Fly.io ejecuta un proceso de mantenimiento de hosts en la región `gru` y migra la máquina a otro host físico. La migración falla a mitad de camino: el volumen persistente queda en estado `corrupted` y la máquina no vuelve a bootear. Franco lo nota recién a la tarde, cuando entra a anotar el almuerzo y la app no responde — gracias al `auto_stop`, llevaba dos días sin abrirla y nadie notó nada antes.

Entra al dashboard de Fly, ve la máquina en `failed` y el volumen en `corrupted`. Intenta `fly volumes extract` y `fly machine restart`: nada. Abre un ticket de soporte (plan económico, sin SLA) y la respuesta tarda cuatro días: "el volumen no es recuperable, los volúmenes de Fly no tienen replicación automática salvo que configures `fork` o snapshots, que no estaban verificados". `finanzas.db` y los 30 backups en `data/backups/` — todos en el mismo disco — desaparecieron juntos. La última copia local en su PC es del 27 de mayo. Faltan más de cuatro meses de transacciones. Franco intenta reconstruir desde resúmenes bancarios y mails de Mercado Pago, pero después de dos noches perdidas, abandona. Vuelve al Excel.

**Supuesto subyacente.** "Si `backup_db()` corre después de cada escritura y guarda 30 copias, ya tengo backups."

**Señales tempranas.**
- Cero bytes de respaldo fuera del volumen Fly (ni S3/B2, ni GitHub, ni el PC) desde enero.
- `fly volumes snapshots list` nunca ejecutado: nadie verificó la retención real de los snapshots automáticos ni probó un restore.

---

### F2 — Muerte por fricción de carga

**La historia del fallo.** La primera semana Franco cargó todo religiosamente: el modo rápido con chips funcionaba bien, sentado en la compu. El quiebre empezó con los gastos chicos del día a día —un café, el kiosco, la SUBE— que pasan en la calle, con el celu. Ahí el flujo real era: abrir el navegador, esperar 5-9 segundos de cold start porque la máquina de Fly se durmió, volver a loguearse porque `st.session_state` se resetea con cualquier refresh, navegar a Transacciones, y recién ahí tipear el monto en un teclado mobile. Cinco a ocho pasos para anotar $2.500 de café.

La primera vez que "lo anoto después" pasó un jueves; el viernes ya eran tres gastos pendientes. El 27/5 cargó el último registro y entró en la espiral: cada día sin abrir la app hacía que cargar de memoria fuera más tedioso y generara números inventados. El dashboard, que era la recompensa, dejó de reflejar la realidad —y un dashboard con huecos de dos semanas no sirve para decidir nada—, así que dejó de abrir la app del todo. El Excel, con todos sus defectos, al menos vivía abierto en una pestaña fija de la compu del trabajo, sin login ni cold start.

**Supuesto subyacente.** "Si la carga es solo un poco más rápida que el Excel, la voy a sostener."

**Señales tempranas.**
- Gap de más de 48hs entre la fecha de un registro y su carga real (carga en lote "de memoria").
- Frecuencia de sesiones cayendo semana a semana mientras los gastos reales se mantienen constantes — ya visible desde la última semana de mayo.

---

### F3 — La bomba de año nuevo (KPIs "anuales" que no son anuales)

**La historia del fallo.** El 2 de enero de 2027, Franco abre Radar Financiero para cargar el cierre de diciembre y armar el presupuesto del año nuevo. El dashboard muestra "Ingreso anual: $18,4M" — un número que no existe en ningún lado de su realidad 2027, porque es la suma de 13 meses (todo 2026 + enero 2027). "Gasto fijo anual" salta a valores que no esperaba y el "% gasto variable" baja tres puntos de golpe, no porque haya gastado menos sino porque `meses_cubiertos` ahora es 13 y los porcentajes se recalculan sobre una masa de ingresos que arrastra noviembre y diciembre de 2026.

Franco hace lo que siempre hizo: reconcilia a mano. El número no cierra. Revisa transacciones, no encuentra error de carga. Entra a `compute_kpis` (es su propio código) y ve `df.loc[df["grupo"] == "Ingreso", "ingresos"].sum()` sin ningún filtro por año — y entiende que el bug estuvo ahí desde Fase 2b, dormido, esperando que pasara un 1° de enero. La fórmula que tanto validó contra el Excel era válida solo porque en 2026 "histórico" y "anual" eran sinónimos. A mediados de febrero, con los KPIs visiblemente rotos y sin selector de año para corregirlo, deja de mirar el Dashboard y vuelve al Excel para el seguimiento mensual.

**Supuesto subyacente.** "Si los tests pasan con datos de un año, van a seguir pasando cuando haya dos."

**Señales tempranas.**
- Ninguno de los 58 tests usa un fixture con transacciones de más de un año calendario.
- `gasto_por_categoria` ya acepta `anio`/`mes` pero el Dashboard lo llama sin filtros — la inconsistencia entre firma y uso es detectable por code review hoy.

---

### F4 — Signup público sin defensas

**La historia del fallo.** 15 de septiembre, 03:14 AM. Un scraper que indexa `fly.dev` buscando paneles de login expuestos encuentra Radar Financiero. Detecta el tab "Crear cuenta", sin captcha, sin verificación de mail. Un bot genera 200 cuentas en 40 minutos. Cada signup es gratis, instantáneo, sin fricción.

A las 04:02, uno de esos bots empieza a insertar transacciones basura en loop, 5 req/seg. Cada insert dispara `backup_db()`. La DB, que pesaba 8MB con los datos reales, crece con las cuentas basura. A las 06:30 ya pesa 35MB. Con retención de 30 backups, el volumen necesita 35MB × 31 ≈ 1.08GB. El volumen de 1GB se llena a las 06:47. A las 06:48, SQLite tira `database or disk is full`: la app queda en error para TODAS las escrituras, incluidas las de Franco. Los backups limpios previos al ataque ya fueron purgados por la rotación de 30 — quedaron solo copias de la base inflada con basura. Franco se entera días después.

**Supuesto subyacente.** "Nadie va a encontrar ni le va a importar una app de finanzas personales con un solo usuario real."

**Señales tempranas.**
- `du -sh data/` saltando de MB a decenas de MB en horas en lugar de KB/día.
- `SELECT COUNT(*) FROM usuarios` pasando de un puñado a cientos en una noche — la alarma más barata de implementar.

---

### F5 — Fuga multi-tenant silenciosa

**La historia del fallo.** Octubre 2026. Franco agrega una feature nueva con callbacks de Streamlit. Copia el patrón del Fondo USD —que sí leía `user_id` de `session_state` a mano— pero en el callback nuevo se le pasa por alto: el handler llama a código de `core/` que internamente hace `require_current_user_id()`. Como el contextvar no está seteado en el contexto del callback, debería tirar `RuntimeError`... pero un parche reciente envolvió la llamada en un `try/except` que cae a `user_id=1` "para no romper producción". Se mergeó sin test, porque los 58 tests cubren parsers y KPIs de un solo usuario, no callbacks ni multi-tenant.

Durante tres semanas, cada edición hecha por los usuarios que entraron por el signup abierto cae silenciosamente en `user_id=1` — la cuenta de Franco. Franco nota previsiones de gastos que no reconoce: un alquiler en otra ciudad, la cuota de un auto que no tiene. Lo atribuye a un bug de fechas. Recién cuando un usuario reporta "no veo mi fondo de emergencia" y Franco corre `SELECT user_id, COUNT(*)`, ve cientos de filas con `user_id=1` que él nunca cargó. Para ese momento ya hizo dos reconciliaciones mensuales con datos contaminados. Separar qué fila es de quién es imposible: no hay rastro de la sesión de origen, solo `user_id=1`.

**Supuesto subyacente.** "Si el contextvar no está seteado, el código va a explotar fuerte y rápido — no va a fallar en silencio hacia mi cuenta."

**Señales tempranas.**
- Cualquier `except` alrededor de `require_current_user_id()` / `get_current_user_id()` en el codebase: un grep periódico debería dar siempre cero.
- `SELECT COUNT(*) FROM <tabla> WHERE user_id=1` creciendo más rápido que lo que Franco carga conscientemente.

---

### F6 — Números que no cuadran entre pestañas (regla dual incompleta)

**La historia del fallo.** Octubre 2026. Franco vende un tramo de su cartera Inviu —unos USD 3.200 en bonos— para cubrir un gasto grande. Carga la transacción con motivo "Inversiones", `ingresos = 3.200`, `pasivos = 0`. Esa noche entra al Dashboard: ahí `efective_grupo()` detecta el ingreso y lo reclasifica a Ingreso/Desahorro. El Dashboard muestra el "ingreso extra" y el saldo de caja sube. Todo cuadra.

Días después abre Mensual para revisar el presupuesto. Ahí `comparativa_mes` usa `load_categorias_map` —el mapeo estático `{"Inversiones": "Inversion"}`, sin pasar por `efective_grupo`—. La fila queda en grupo "Inversion", y como no es "Ingreso", `_pick_real` toma `pasivos_mes`, que para esa transacción es 0. Resultado: la venta muestra `monto_real = 0` en Mensual, como si nunca hubiera pasado; tampoco aparece en el grupo Ingreso. El saldo mensual real de Mensual no coincide con lo que sugiere el Dashboard, y ninguno coincide exactamente con el extracto del broker (que sí refleja la venta). Franco pasa media hora exportando a Excel y recalculando a mano. La sensación no es "encontré un bug menor", es "no sé en cuál de las tres pestañas confiar". A partir de ahí lleva el control real en una planilla aparte y abre la app cada vez menos.

**Supuesto subyacente.** "Si una regla de negocio está implementada y funciona en una pantalla, funciona en todas las pantallas que muestran el mismo dato."

**Señales tempranas.**
- Grep de `efective_grupo`: se usa en `core/metrics.py` y `core/diario.py`, pero `core/budget.py::comparativa_mes` usa `load_categorias_map` — dos fuentes de verdad distintas para "a qué grupo pertenece esta fila".
- Test barato: para cualquier mes con una transacción "Inversiones" con `ingresos > 0`, comparar el Desahorro del Dashboard vs su reflejo en Mensual; si difieren, el bug está activo (hoy difieren).

---

### F7 — Backups que no rescatan

**La historia del fallo.** Es jueves a la noche, primera semana de noviembre. Franco está cargando los gastos de octubre y, mientras edita previsiones en el editor inline, toca sin querer una transacción de hace tres semanas: cambia el monto de un alquiler de $180.000 a $18.000. No se da cuenta. Sigue cargando, edita seis previsiones más, agrega categorías nuevas. Cuarenta y tantas escrituras esa noche. Los reportes ya no cierran, pero lo atribuye a "diferencias de redondeo".

Tres semanas después, armando el resumen anual, nota el desfase de $162.000 y encuentra el error. Va a buscar el backup de esa noche de noviembre. No existe: esa sesión sola generó más de 30 backups, y los 30 retenidos son todos de las semanas siguientes. El error está en absolutamente todos. Prueba con la copia local de Windows: última transacción del 27/5, inservible. Intenta entonces ensayar un restore en Fly y descubre que nunca documentó cómo subir un .db al volumen — pierde dos horas entre `flyctl ssh console`, herramientas que no están en la imagen y permisos del volumen. Reconstruye el dato a mano desde resúmenes de tarjeta. Funciona, pero la sensación que queda es: "tengo 30 backups y ninguno me sirvió de nada".

**Supuesto subyacente.** "Si tengo 30 copias guardadas, tengo 30 puntos en el tiempo distintos para volver."

**Señales tempranas.**
- `data/backups/` con 10 archivos en una ventana de 5 minutos (18/5/2026) — prueba directa de que "30 backups" puede significar "30 minutos".
- Cero ensayos de restore desde el deploy inicial: ninguna evidencia de que el camino de recuperación sea operable bajo presión.

---

### F8 — Erosión silenciosa de plataforma

**La historia del fallo.** Julio 2026: Fly.io ajusta su política de billing (algo que ya hicieron antes) y empieza a facturar el volumen que antes entraba en el tier gratuito. La tarjeta que Franco cargó venció en junio. Fly manda un mail de "actualizá tu método de pago" que se pierde entre 200 mails sin leer. La app sigue corriendo unas semanas porque la máquina con auto_stop casi no consume, pero a fin de mes Fly suspende la cuenta y el volumen queda en cuarentena.

Franco no se entera porque hace tres semanas que no abre la app —vacaciones, después se le pasó—. Cuando intenta entrar, la URL tira "app suspended". Asume que es temporal y lo deja para después. Pasan diez días. Cuando investiga, descubre que tiene una ventana limitada para reactivar el volumen antes del borrado definitivo. En paralelo, un redeploy menor del mes anterior instaló un Streamlit más nuevo (requirements sin pin) que cambió el comportamiento de un widget: la app "funcionaba" pero un control quedó roto en silencio. Franco lo notó, pensó "raro, lo reviso después" y nunca volvió. Cada incidente sumó fricción y desconfianza ("¿estará andando?"), hasta que en diciembre volvió a anotar gastos en una planilla "hasta arreglar lo de Fly", y nunca lo arregló.

**Supuesto subyacente.** "Si algo se rompe, me voy a dar cuenta cuando entre a usarla."

**Señales tempranas.**
- Mails de Fly (billing/pricing) sin abrir por más de 7 días.
- Más de 2-3 semanas sin abrir la app después de un deploy — riesgo acumulado sin detectar; no existe ningún chequeo automático de `/_stcore/health`.

---

## 4. Síntesis — Informe de premortem

### El fallo más probable: F2 + F3 en tándem (abandono por fricción, rematado por KPIs rotos en enero)
La evidencia ya está en los datos: la copia local quedó congelada el 27/5 y el ritmo de carga bajó. La fricción estructural (cold start del auto_stop + re-login en cada refresh + tipeo manual en mobile) erosiona el hábito de carga, y el 1/1/2027 el dashboard "miente" por diseño (`compute_kpis` sin filtro de año). La combinación de "cargar cuesta" + "lo que veo no es confiable" es la receta exacta del retorno al Excel. El premortem #2 ya había encontrado este patrón ("la app exige MÁS mantenimiento manual que el Excel") y la lección no se aplicó a la app principal.

### El fallo más peligroso: F1 (pérdida total del historial financiero)
La DB y sus 30 backups comparten el mismo volumen físico de Fly, sin réplica ni copia externa automática; la copia local está meses desactualizada y el restore jamás se ensayó. Un único evento (volumen corrupto, cuenta suspendida por tarjeta vencida, máquina eliminada) borra el año financiero completo de Franco de forma irreversible. Probabilidad baja-media; daño máximo. F4 (signup abierto) y F7 (retención por cantidad) son amplificadores directos de este fallo.

### El supuesto oculto
**"Tener backups = estar protegido."** Los 30 backups generan sensación de seguridad, pero: viven en el mismo disco que el original (no protegen contra pérdida del volumen), rotan por cantidad y no por edad (una sesión activa purga todo el historial: ventana real de minutos), y nunca se ensayó un restore (no se sabe si el camino de recuperación funciona). El sistema de backups actual protege casi exclusivamente contra el escenario menos probable (corrupción puntual entre dos escrituras consecutivas) y contra ninguno de los probables.

### El plan revisado (cada cambio mapea a un fallo)

| # | Acción | Fallo que previene | Esfuerzo |
|---|---|---|---|
| R1 | **Backup externo automático**: snapshot diario de `finanzas.db` fuera de Fly (Tigris/S3/B2 desde la propia app con un cron simple, o `fly ssh sftp get` programado desde la PC) + verificar `fly volumes snapshots list` hoy | F1, F7 | 1-2 hs |
| R2 | **Retención por edad, no por cantidad**: en `_purge_old_backups`, conservar 1 backup por día por 30 días (+ los últimos 10 inmediatos), en lugar de "los 30 últimos" | F7, F4 | 30 min |
| R3 | **Arreglar la regla dual en Mensual**: `comparativa_mes` debe clasificar con `efective_grupo` (mismo motor que Dashboard/Diario) + test con fixture de venta de inversiones | F6 | 2-3 hs |
| R4 | **Selector de año en Dashboard + KPIs filtrados por año** + test con fixture de dos años calendario. Fecha límite dura: antes del 1/1/2027 | F3 | 2-4 hs |
| R5 | **Cerrar o proteger el signup** (`SIGNUP_ENABLED=False` o código de invitación) + rate-limit básico en login (delay incremental por intentos fallidos) | F4 | 1 h |
| R6 | **Migración M5: quitar `DEFAULT 1` de todas las columnas `user_id`** para que un INSERT sin usuario explote ruidosamente; regla de código: jamás `except` alrededor de `require_current_user_id()` | F5 | 1 h |
| R7 | **Monitoreo mínimo**: uptime check gratuito a `/_stcore/health` con alerta por mail + chequeo semanal de tamaño de `data/` y `COUNT(usuarios)`; verificar estado de tarjeta en Fly hoy | F8, F4, F1 | 30-60 min |
| R8 | **Pin de dependencias**: `pip freeze > requirements.lock` y build de Docker contra el lock | F8 | 30 min |
| R9 | **Reducir fricción de carga**: sesión persistente (cookie firmada) para no re-loguear en cada visita + acceso directo en el home screen del celu; re-priorizar el chatbot WhatsApp por encima de tutorial/CSS como única solución de fondo a la captura | F2 | 2 hs (cookie) / 3-5 días (WhatsApp) |
| R10 | **Ensayar UN restore completo** (bajar backup → levantar app local contra él → verificar saldo) y documentar el paso a paso en DEPLOY.md | F1, F7 | 1 h |

### Lista de verificación pre-"siguiente feature"
1. ☐ `fly volumes snapshots list` ejecutado y retención de snapshots verificada (hoy).
2. ☐ Un restore completo ensayado y documentado de punta a punta.
3. ☐ Existe al menos una copia de `finanzas.db` de hoy fuera de Fly (PC + nube).
4. ☐ Test verde con fixture de DOS años calendario en `compute_kpis`.
5. ☐ Test verde de aislamiento multi-tenant (dos usuarios; el callback sin contextvar lanza error, no cae a user 1).
6. ☐ Tarjeta de crédito vigente en Fly + mail de billing en lista segura.

### Re-priorización del backlog (vs. MEJORAS-UX.md)
El backlog actual prioriza tutorial guiado (4.1.b) y estética (4.2/4.4). Este premortem indica invertir el orden: **primero durabilidad y corrección (R1–R8), después fricción de carga (R9), y recién después tutorial/CSS**. Un tutorial hermoso sobre números que no cuadran y datos que pueden desaparecer no salva el proyecto; lo inverso sí.

---

*Premortem #3 ejecutado el 11/6/2026 con 8 agentes de análisis profundo en paralelo. Premortems previos: #1 inicial (12/5/2026), #2 módulo inversiones (27/5/2026).*
