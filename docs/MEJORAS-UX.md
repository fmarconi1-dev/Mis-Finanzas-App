# Mejoras de estilo y experiencia (UX) — Radar Financiero

Documento de trabajo. Análisis del estado visual/UX actual de la app y un
backlog priorizado de mejoras. Nada de esto toca la lógica de negocio ni los
datos: es todo capa de presentación y experiencia.

Fecha del análisis: mayo 2026 · Estado base: app funcional en producción (Fly.io).

---

## 0. Estado actual del backlog (actualizado junio 2026)

**Hecho ✅:**
- 2.1 Tema de marca (`.streamlit/config.toml` con verde menta y dark).
- 2.2 Colores semánticos (`ui/_theme.py`).
- 2.3 Números abreviados (`fmt_ars_corto` en `_format.py`).
- 2.4 `st.toast` en confirmaciones (transacciones, configuración).
- 2.5 Logo + título "Radar Financiero" + favicon SVG + identidad unificada.
- 2.6 Iconos en pestañas.
- 3.1 Containers / jerarquía visual en Dashboard.
- 3.2 Tablas con column_config (ProgressColumn en Mensual).
- 3.3 Template Plotly unificado.
- 3.4 Estados vacíos amables (Dashboard, Mensual, Diario).
- 3.5 Color en deltas (signed format).
- 3.6 Revisión mobile (`ui/_responsive.py` con CSS media queries).
- 4.1.a Onboarding cálido (hero + 3 feature cards + form).
- 4.1.b Tutorial guiado simple (`ui/_tour.py` con 5 pasos contextuales).
- 4.2 Design system CSS custom (`ui/_styles.py` — métricas, botones primarios,
  containers, dividers, inputs).
- 4.3 Flujo de alta rápida (chips de motivos frecuentes + montos recurrentes +
  toggle Modo rápido).
- 4.5 Barras de progreso de presupuesto en Mensual (ProgressColumn).
- **Seguridad (Premortem #3, junio 2026):** rate-limit login (5/15min →
  bloqueo 5min), SIGNUP_CODE gating, session tokens vía `SESSION_SECRET` para
  "recordarme". Ver `premortem-report-2026-06-11.html`.

**Pendiente 📋:**
- 4.4 Toggle claro/oscuro (sección 4). Bajo impacto; choca con el CSS custom
  que asume dark theme. Requeriría reescribir varios selectores.
- Sección 7: Voz consistente (microcopy). Difuso pero valioso si se
  sistematiza (definir 4-5 reglas y aplicar).
- Sección 8: Chatbot WhatsApp. Feature grande (~3-5 días). Requiere premortem
  antes.
- Sección 9: Cartera de Inversiones. La más grande del backlog. Premortem ya
  hecho (`premortem-inversiones-2026-05-27.html`) recomienda scope reducido:
  visualizador + integración con cash flow, no reemplazar el Excel.
- Sección 10: Monetización. Diferida hasta 5-10 usuarios activos. Sin acción
  por ahora; sólo dejar terreno técnico preparado (ya está: multi-tenant +
  auth listos).

**Roadmap natural para próximos meses:**

1. Crecer orgánicamente la base de usuarios (invitar amigos/familia con
   `SIGNUP_CODE`). El tutorial guiado + onboarding cálido reducen fricción.
2. Recolectar feedback real de los 5-10 primeros usuarios.
3. Refinar microcopy (sección 7) según lo que pidan.
4. Considerar WhatsApp chatbot (sección 8) cuando el patrón de carga desde
   celular sea evidente y la fricción de la web sea molesta.
5. Cartera de Inversiones (sección 9) con el scope revisado del premortem, si
   en algún momento Franco quiere unificar gastos + portfolio en un solo lugar.
6. Monetización (sección 10) sólo después de validar valor con base real.

---

---

## 1. Diagnóstico general

Lo que funciona hoy:
- Estructura de 5 pestañas clara y predecible.
- Datos correctos, KPIs que cuadran, gráficos interactivos (Plotly).
- Formato de moneda argentino consistente (`ui/_format.py`).
- Secciones colapsables en el Dashboard.

Las debilidades visuales/UX (oportunidades):
- **Sin identidad visual propia.** Usa el tema oscuro por defecto de Streamlit.
  No hay paleta de marca, ni tipografía, ni logo. Se "siente" como un prototipo,
  no como un producto.
- **Sin colores semánticos.** Ingresos, gastos, inversión y desahorro no tienen
  un color consistente que el ojo aprenda. Hoy los `st.metric` son todos del
  mismo gris.
- **Números difíciles de escanear.** `$15.014.431,00` en una card es correcto
  pero pesado. Un `$15,0 M` con el detalle en hover se lee de un vistazo.
- **Jerarquía plana.** 12+ métricas en filas sucesivas sin agrupación visual
  (cajas, bordes, fondos). Todo compite por la misma atención.
- **Gráficos sin tema unificado.** Cada gráfico define sus colores a mano
  (`#60a5fa`, `#f87171`, etc.) sin una paleta central; los fondos no combinan
  con un tema de marca.
- **Estados vacíos pobres.** Un usuario nuevo ve `st.info("No hay datos...")`.
  Funcional pero frío; es el primer contacto y no guía ni motiva.
- **Feedback básico.** Se usa `st.success` (banner que ocupa espacio). `st.toast`
  (notificación efímera) es más prolijo para confirmaciones.
- **Mobile sin optimizar.** Franco carga gastos desde el celular. El layout
  `wide` y las tablas anchas no están pensados para pantalla chica.
- **El flujo más usado (alta de transacción) es genérico.** Podría tener
  atajos: montos rápidos, motivos recientes como chips, foco automático.

---

## 2. Quick wins (alto impacto, bajo esfuerzo)

### 2.1. Tema de marca (`.streamlit/config.toml`) — ⭐ el de mayor impacto/esfuerzo
Hoy no existe este archivo. Crearlo cambia toda la app de golpe.

```toml
# .streamlit/config.toml
[theme]
primaryColor = "#6ee7b7"            # verde menta (acciones, acentos)
backgroundColor = "#0e1117"         # fondo principal
secondaryBackgroundColor = "#1a2030" # cards, inputs
textColor = "#e8ecf4"
font = "sans serif"
```
Esfuerzo: 10 min. Impacto: transforma la sensación general. Después se afina
la paleta a gusto.

### 2.2. Colores semánticos consistentes
Definir en `ui/_format.py` (o un nuevo `ui/_theme.py`) una paleta central y
usarla en TODOS los gráficos y, vía CSS, en las métricas:

```python
COLOR_INGRESO   = "#60a5fa"   # azul
COLOR_GASTO     = "#f87171"   # rojo/coral
COLOR_INVERSION = "#34d399"   # verde
COLOR_DESAHORRO = "#fbbf24"   # ámbar
COLOR_NEUTRO    = "#9aa3b8"
```
Reemplazar los hex hardcodeados en `dashboard.py`, `mensual.py`. Que el azul
SIEMPRE sea ingreso, el rojo SIEMPRE gasto. El ojo lo aprende en 2 usos.

### 2.3. Números abreviados en las cards
Agregar a `ui/_format.py` un `fmt_ars_corto()`:

```python
def fmt_ars_corto(v):
    a = abs(v)
    if a >= 1_000_000: return f"${v/1_000_000:.1f}M".replace(".", ",")
    if a >= 1_000:     return f"${v/1_000:.0f}K"
    return fmt_ars(v)
```
Usarlo en los `st.metric` del Dashboard (valor corto) y dejar el número completo
en el `help=`. `$15,0M` se escanea mucho más rápido que `$15.014.431,00`.

### 2.4. `st.toast` en vez de `st.success` para confirmaciones
En `transacciones.py` y `configuracion.py`, cambiar los `st.success(...)` de
operaciones (alta, borrado, guardado) por `st.toast("✅ Transacción agregada")`.
Es una notificación flotante que no empuja el layout.

### 2.5. Logo + título de marca
- Crear/usar un logo simple (puede ser emoji estilizado o un SVG chico).
- `st.logo("assets/logo.png")` (Streamlit ≥1.34) lo fija arriba de la sidebar.
- Renombrar visualmente a "Radar Financiero" (ya es el nombre del deploy) para
  unificar identidad.

### 2.6. Iconos consistentes en las pestañas
Hoy las tabs son texto plano. Pasar a:
`["📊 Dashboard", "➕ Transacciones", "📒 Diario", "🎯 Mensual", "⚙️ Configuración"]`
en `app.py`. Coherente con los emojis que ya usás en los expanders.

---

## 3. Mejoras medias (impacto alto, esfuerzo medio)

### 3.1. Jerarquía visual con contenedores
Envolver cada grupo de métricas en `st.container(border=True)` (Streamlit ≥1.29)
para que "Liquidez", "KPIs" y "Distribución" se lean como tarjetas separadas, no
como una lista continua. En `dashboard.py`, envolver cada bloque de `st.columns`.

### 3.2. Tablas con formato nativo (`column_config`)
Hoy en `transacciones.py`, `mensual.py` y `diario.py` se formatea a mano y se
pasan strings. Usar `st.column_config` da formato + color + barras:

```python
st.dataframe(df, column_config={
    "Importe": st.column_config.NumberColumn(format="$ %.2f"),
    "Desvío %": st.column_config.NumberColumn(format="%.1f%%"),
})
```
En la tabla Mensual, una `ProgressColumn` para el desvío vs presupuesto sería
muy visual (barra que se llena, roja si te pasaste).

### 3.3. Template Plotly unificado
Definir un template propio una sola vez y aplicarlo a todos los gráficos:

```python
import plotly.io as pio
pio.templates["radar"] = pio.templates["plotly_dark"]
# tunear fuentes, grid, colores de fondo para que combinen con el tema
pio.templates.default = "radar"
```
Saca el trabajo de tunear `update_layout` en cada gráfico y los unifica.

### 3.4. Estados vacíos amables
Para usuarios nuevos (Dashboard/Diario/Mensual vacíos), en vez de
`st.info("No hay datos")`, mostrar una mini-guía:
> 🌱 **Tu radar está vacío todavía.** Cargá tu primera transacción desde la
> pestaña ➕ Transacciones y los números van a aparecer acá.
Con un botón que lleve a la pestaña correspondiente.

### 3.5. Color en los deltas de métricas
`st.metric` soporta `delta` con color automático (verde/rojo). Hoy se usa poco.
Ej: en "Resultado mensual" mostrar el delta vs mes anterior; en gastos, usar
`delta_color="inverse"` (gastar menos = verde). Ya lo hacés en Mensual; llevarlo
al Dashboard.

### 3.6. Revisión mobile
- Probar la app en el celular y ajustar: las filas de 4 columnas se ven
  apretadas. Considerar detectar ancho o usar menos columnas por fila.
- El form de alta debería ser cómodo con una mano: campos grandes, teclado
  numérico para el importe (`st.number_input` ya lo hace en mobile).

---

## 4. Mejoras grandes (alto impacto, esfuerzo mayor)

### 4.1. Rediseño del onboarding + tutorial guiado
Dos mejoras complementarias:

**a) Pantalla de onboarding más cálida.** Hoy es un form plano (saldo inicial +
fondo USD). Convertirlo en una bienvenida de 2-3 pasos con progreso visual,
copy cálido, y quizás un ejemplo precargado opcional ("¿Querés ver la app con
datos de ejemplo primero?"). Es el primer contacto de tus amigos con la app.

**b) Tutorial guiado post-onboarding (con flechas/diálogos contextuales).**
Para que un usuario nuevo entienda las 5 pestañas sin tener que adivinar.
Dos opciones técnicas:

- **Versión simple** (~3-4 horas): `st.session_state.tour_activo = True` al
  terminar onboarding. Cada pestaña, en la primera visita, muestra un panel
  arriba con la explicación del paso ("Acá vas a ver tus KPIs anuales y
  mensuales en vivo. Hace clic en 'Siguiente' para ir a Transacciones") + botón
  "Siguiente paso" y "Saltar tutorial". Sin flechas reales que apunten a
  elementos, pero con copy orientativo. Lo que usan la mayoría de los apps de
  finanzas (YNAB, Lunch Money) en su onboarding.
- **Versión fancy** (~1-2 días): integrar `driver.js` o `intro.js` vía un
  componente custom de Streamlit (`st.html` + JS embebido). Esto SÍ permite
  flechas reales señalando elementos, popovers contextuales, y highlights
  visuales. Más lindo pero requiere JS y cuidado entre versiones de Streamlit
  (los selectores CSS internos cambian).

Recomendación: empezar por la versión simple. Si el feedback de usuarios
nuevos lo pide, escalar a fancy.

### 4.2. Design system con CSS custom
Inyectar CSS (`st.markdown(..., unsafe_allow_html=True)` o `st.html`) para:
- Tarjetas de métrica con fondo, borde redondeado, ícono y color de acento por
  tipo (ingreso/gasto/inversión).
- Tipografía con jerarquía real (títulos más grandes, números destacados).
- Espaciados consistentes.
Es lo que más "sube el nivel" visual, pero requiere cuidado para no pelear con
los updates de Streamlit. Hacerlo modular en un `ui/_styles.py`.

### 4.3. Flujo de alta "rápida"
Rediseñar `transacciones.py` para el caso 80%: cargar un gasto en 3 toques.
- Chips de motivos más usados (botones rápidos en vez de dropdown).
- Botones de montos frecuentes.
- Fecha = hoy por defecto (ya está), foco automático en importe.
- Quizás un modo "carga rápida" vs "carga detallada".

### 4.4. Toggle claro/oscuro
Algunos usuarios prefieren tema claro. Ofrecer un switch (se puede con
`st.session_state` + reinyectar CSS, o con la config de tema de Streamlit).

### 4.5. Barras de progreso de presupuesto en Mensual
En la vista Mensual, por cada categoría mostrar una barra "gastado vs
presupuestado" con color (verde dentro, ámbar cerca del límite, rojo pasado).
Mucho más intuitivo que leer la columna de desvío %.

---

## 5. Matriz de priorización

| Mejora                                   | Impacto | Esfuerzo | Orden sugerido |
|------------------------------------------|---------|----------|----------------|
| 2.1 Tema de marca (config.toml)          | Alto    | Muy bajo | 1              |
| 2.2 Colores semánticos                   | Alto    | Bajo     | 2              |
| 2.3 Números abreviados                   | Medio   | Bajo     | 3              |
| 2.6 Iconos en tabs                       | Bajo    | Muy bajo | 4              |
| 2.4 st.toast                             | Bajo    | Bajo     | 5              |
| 3.1 Contenedores / jerarquía             | Alto    | Medio    | 6              |
| 3.3 Template Plotly unificado            | Medio   | Bajo     | 7              |
| 3.2 Tablas con column_config             | Medio   | Medio    | 8              |
| 3.4 Estados vacíos amables               | Medio   | Bajo     | 9              |
| 4.5 Barras de progreso presupuesto       | Alto    | Medio    | 10             |
| 3.6 Revisión mobile                      | Alto    | Medio    | 11             |
| 4.2 Design system CSS                    | Muy alto| Alto     | 12             |
| 4.1 Rediseño onboarding                  | Medio   | Alto     | 13             |
| 4.3 Flujo de alta rápida                 | Alto    | Alto     | 14             |
| 4.4 Toggle claro/oscuro                  | Bajo    | Medio    | 15             |

**Plan recomendado para la próxima sesión:** arrancar por el bloque 2 completo
(quick wins 1-5). En ~1-2 horas la app cambia de cara por completo y bajo riesgo.
Después el bloque 3. El bloque 4 (CSS custom, onboarding, alta rápida) se encara
cuando quieras invertir en pulido fino.

---

## 6. Notas técnicas / checklist al implementar

- **Versión de Streamlit**: confirmar que sea ≥1.34 para `st.logo`, ≥1.29 para
  `st.container(border=True)`, ≥1.27 para `column_config` avanzado. Si no,
  `pip install -U streamlit` + actualizar `requirements.txt` + redeploy.
- **CSS custom es frágil** entre versiones de Streamlit (depende de clases
  internas). Aislarlo en `ui/_styles.py` y documentar qué selector toca qué,
  para repararlo rápido si un update lo rompe.
- **Tests**: ninguna de estas mejoras debería romper `pytest tests/` porque son
  capa de presentación. Igual, correrlos después de cada bloque.
- **No tocar la lógica de KPIs ni el schema** en estas mejoras — son puramente
  visuales. Si una mejora pide datos nuevos (ej. delta vs mes anterior), eso sí
  es lógica y conviene un mini-premortem antes.
- **Mobile**: probar en el celular real después de cada bloque visual, no sólo
  en desktop.
- **Deploy**: el ciclo sigue siendo `streamlit run app.py` (local) →
  `pytest tests/` → `fly deploy`.

---

## 7. Idea transversal: consistencia de "voz"

Más allá de lo visual, la app puede sentirse más amigable con microcopy cálido y
consistente: mensajes en segunda persona ("Cargá tu primer gasto"), tono
alentador en los estados vacíos, y celebrar hitos ("¡Primer mes completo!").
Pequeño esfuerzo, mucha calidez. Conviene definir 4-5 reglas de voz y aplicarlas
en todos los textos de la UI.

---

## 8. Visión futura — Chatbot de WhatsApp complementario

> Versión anterior: este bloque se pensó originalmente para Telegram. Se
> reemplazó por WhatsApp porque en Argentina WhatsApp tiene adopción casi
> universal mientras Telegram es minoritario. La idea conceptual es la misma;
> cambian las herramientas y algunos detalles operativos.

**Concepto.** Un bot de WhatsApp que viva en paralelo a la app web y permita:
1. **Cargar gastos/ingresos por chat**, sin abrir el navegador. Ej: el momento
   "acabo de pagar $8.500 en el supermercado" se resuelve mandando un mensaje
   desde el celular, en 5 segundos. Ventaja de WhatsApp: ya lo tenés abierto
   todo el día — fricción cero.
2. **Pedir reportes a demanda**: saldo actual, gasto del mes en una categoría,
   evolución, "cuánto invertí este trimestre", etc.
3. **Cuenta compartida**: que varios números de WhatsApp (vos + tu pareja, o
   un grupo familiar) puedan cargar movimientos en la MISMA cuenta de la app.
   El chat queda como un libro de movimientos colaborativo en tiempo real.

El bot NO reemplaza a la app — la complementa. La app sigue siendo donde mirás
los KPIs, presupuesto, dashboard. El bot es la entrada rápida y la consulta
puntual sin fricción.

### Alcance por fases

**MVP (~2-3 días — más que Telegram por la configuración de Meta):**
- Cuenta de Meta Business + WhatsApp Business Cloud API activada para un
  número dedicado al bot (separado del personal).
- Webhook configurado contra una URL HTTPS de la app (Fly nos da HTTPS gratis,
  ya está cubierto).
- Comandos estructurados, formato simple para que se tipee rápido:
  - `gasto 8500 compras` (importe + motivo + comentario opcional)
  - `ingreso 50000 sueldo`
  - `saldo` — devuelve Saldo CC actual
  - `mes` — resumen del mes en curso
  - `ayuda` — lista de comandos
- WhatsApp no usa slash-commands (`/`) como convención; los mensajes son
  texto libre. Mejor: primer palabra = comando.
- Linking: un único número de WhatsApp ↔ un usuario de la app, vinculado vía
  código que se genera desde Configuración en la web.

**Versión completa (~+2 días):**
- Soporte multi-usuario por cuenta (varios números → mismo `user_id` app).
- Columna `creado_por` en transacciones para saber quién cargó cada movimiento
  (te + pareja en el log).
- Comandos enriquecidos:
  - `categoria compras 30d` — gasto por categoría en período
  - `grafico mes` — devuelve imagen (PNG) con el donut o evolución
  - `editar` — permite corregir la última transacción
- Aceptar formato libre además de comandos ("gasté 5000 en uber"
  → parser intenta interpretar).
- Plantillas de mensaje aprobadas en Meta para notificaciones proactivas
  (necesarias fuera de la ventana de 24h, ver "riesgos" abajo).

**Versión avanzada (~+1-2 días por cada):**
- NLP real con un modelo chico (regex + diccionario primero; LLM como fallback).
- Notificaciones proactivas: "vas 40% por encima del presupuesto de Salidas este
  mes", "tu sueldo todavía no entró". Requiere plantillas pre-aprobadas
  porque WhatsApp tiene la regla de ventana de 24h (no podés iniciar
  conversación a un usuario que no te escribió en las últimas 24h sin usar
  plantillas).
- Webhooks de alertas configurables.

### Arquitectura propuesta

A diferencia de Telegram (que ofrece long-polling como alternativa cómoda),
WhatsApp **requiere webhook HTTPS** — Meta manda POSTs a una URL nuestra cada
vez que entra un mensaje. Eso simplifica una cosa (no necesitamos un proceso
persistente "escuchando") y complica otra (la URL tiene que estar siempre
levantada y accesible).

Tres opciones, ordenadas de más simple a más sofisticada:

**Opción A — endpoint webhook embebido en la misma app Streamlit** (no
recomendada):
- Streamlit no expone fácilmente rutas HTTP custom. Se podría hackear con
  algún wrapper, pero queda frágil. Evitar.

**Opción B — proceso FastAPI separado en la misma máquina Fly** (recomendada):
- Junto a `streamlit run app.py` corre un `uvicorn bot_webhook:app` en otro
  puerto interno (ej. 8502). FastAPI recibe el webhook de Meta, parsea, llama
  a `core/transactions.py` para insertar, y responde con un mensaje vía
  WhatsApp Cloud API.
- Configuramos Fly para exponer ambos puertos (Streamlit en 8501 → dominio
  principal; FastAPI en 8502 → ruta `/webhook` o subdominio).
- En `fly.toml` se agrega un segundo "process group" o se usa `supervisord`
  para correr ambos en el mismo container.
- Pros: comparte DB SQLite directo, una sola infra a mantener, simple de
  debuggear, cero costo extra.
- Cons: si la máquina duerme (auto_stop), un mensaje entrante despierta la
  máquina pero puede tardar 5-10s en responder (Meta reintentará si no
  recibe 200 OK rápido). Forzar `min_machines_running = 1` lo evita.

**Opción C — webhook serverless (Cloudflare Workers + Fly API)**:
- Worker en Cloudflare recibe el webhook (respuesta instantánea), reenvía a
  una API HTTP en la app Fly que hace la lógica.
- Pros: el webhook responde sub-100ms aunque la app duerma; la app Fly puede
  seguir con auto-stop.
- Cons: más infra; ahora tres piezas (Worker, API Fly, DB). Sólo vale la pena
  si la latencia del cold-start de Fly molesta.

Mi recomendación: **arrancar con B** (FastAPI en el mismo Fly), forzar
`min_machines_running = 1` para que el webhook siempre responda rápido.
Migrar a C si después de usar querés bajar costos o si la cold-start latency
realmente molesta.

### Cambios de schema necesarios

- **Nueva tabla `whatsapp_links`**: `(wa_phone_id PK, app_user_id FK,
  display_name, vinculado_en, rol)`. Permite que un usuario de la app tenga
  varios números de WhatsApp vinculados (cuenta compartida).
- **Columna `creado_por`** en `transacciones`: opcional, guarda el `wa_phone_id`
  o `"web"` para distinguir el origen. Útil para el caso compartido (saber
  quién cargó qué).
- **Tabla `whatsapp_link_codes`**: códigos de un solo uso, generados desde la
  web ("genera código de vinculación", expira en 10 minutos). El usuario manda
  al bot el mensaje `vincular CODIGO123` y queda asociado.

### Linking flow (UX)

1. Usuario logueado en la app va a Configuración → "Conectar WhatsApp".
2. La app genera un código corto (`AB7K9X`), lo muestra junto al número del bot
   y un link `wa.me/541112345678?text=vincular+AB7K9X` que abre WhatsApp con el
   mensaje precargado.
3. Usuario toca el link → WhatsApp se abre con el mensaje listo → toca enviar.
4. El bot valida el código, asocia el número del remitente al `user_id` del
   código, y responde: "✅ Vinculado a la cuenta de Franco. Probá `saldo`".
5. El código se consume (un solo uso) y expira a los 10 min.
6. Para cuentas compartidas: el usuario "dueño" genera un código de invitación
   y se lo manda a quien quiera sumar por WhatsApp (forwardable). Cada nuevo
   número queda linkeado al mismo `app_user_id`.

### Riesgos a contemplar (premortem-light)

- **Seguridad**: alguien con tu WhatsApp ve tus finanzas. El usuario debe
  bloquear WhatsApp con PIN/biométrico o aceptar el riesgo. Mejor: no exponer
  Saldo CC sin un `desbloquear PIN` primero, configurable.
- **Carga ambigua**: "gasto 5000 algo" → ¿"algo" es motivo o comentario?
  Definir gramática estricta. Si el motivo no existe, ofrecer crear o pedir
  selección de los más recientes (WhatsApp soporta listas interactivas vía
  Cloud API).
- **Modo compartido y conflicto de categorías**: dos personas cargando con
  distintos motivos crean ruido en `categorias`. El "dueño" debería poder
  aprobar/normalizar nuevas categorías.
- **Ventana de 24h de WhatsApp**: si vos no le escribiste al bot en las últimas
  24h, el bot no puede iniciar conversación (notificaciones proactivas
  bloqueadas). Solución: registrar plantillas pre-aprobadas en Meta (proceso
  manual de 1-2 días para que las aprueben).
- **Verificación de número y costo del SIM**: Meta exige que el número
  asociado al bot esté activo y verificable por SMS. Eso significa tener un
  número dedicado (chip extra) que no sea tu personal. Costo: el del chip
  prepago.
- **Meta cambia/restringe el Cloud API**: pasa periódicamente. Hay que estar
  atento a deprecation notices. Health check obligatorio.
- **Free tier**: 1000 conversaciones/mes gratis. Cada "conversación" son los
  mensajes intercambiados en una ventana de 24h con un mismo usuario. Para uso
  personal/familiar (2-5 usuarios cargando varios gastos diarios) sobra. Si
  escala más allá, hay que pagar (~USD 0.005 por conversación de servicio
  iniciada por el usuario, casi nada).
- **Costo de Fly al forzar `min_machines_running=1`**: la app deja de dormir,
  consume más allowance. Verificar si entra en el free tier sostenido.

### Esfuerzo estimado

| Fase                                                      | Esfuerzo |
|-----------------------------------------------------------|----------|
| Setup Meta Business + WhatsApp Cloud + número verificado  | 0,5 día  |
| MVP single-user con comandos básicos                      | 1,5 días |
| Multi-user compartido + linking robusto                   | +1 día   |
| Gráficos como PNG en respuestas (Cloud API soporta media) | +1 día   |
| NLP / lenguaje natural                                    | +1-2 días|
| Plantillas Meta + notificaciones proactivas               | +1-2 días|

### Antes de construirlo: premortem obligatorio

Esto es una feature transversal que toca infra, schema y experiencia. Cuando
decidamos arrancar, **conviene correr un premortem completo primero** (como
hicimos al inicio del proyecto), enfocado en:
- ¿Qué pasa si el bot cae y nadie lo nota? ¿Cómo me entero?
- ¿La cuenta compartida genera conflictos entre quien cargó qué?
- ¿La latencia entre "mando el mensaje" y "se ve en la app" rompe la confianza?
- ¿Vale la pena el esfuerzo dado mi patrón real de uso, o termino usando la web igual?

El premortem evita armar la feature completa y descubrir a los 2 meses que no
la usás.

---

## 9. Visión futura — Cartera de Inversiones (premortem aplicado)

**Concepto original:** ampliar la app para que también gestione el seguimiento
de la cartera de inversiones (Bonos, CEDEARs, Letras, ONs, Acciones, Cripto,
Cauciones), reemplazando el `Inversiones.xlsx` actual.

**Resultado del premortem** (ejecutado en mayo 2026, ver `premortem-inversiones-2026-05-27.html`):
identificamos 12 modos de fallo distintos. La conclusión es **fuerte: NO
reemplazar el Excel actual**. El Excel ya está optimizado (addin BYMADATA tira
precios solo, fórmulas calculan TC y MTM, mappings ARS↔USD automáticos). La
probabilidad de que la app termine peor que el Excel es alta, y la consecuencia
(perder confianza en los números de inversión) es terminal.

### Alcance revisado por el premortem

**NO** reemplazar el Excel.
**SÍ** visualizar e integrar.

El módulo:
1. **Importa** el "Movimientos Procesado" del Excel como CSV (no parsea el
   broker, no maneja precios propios, no calcula bonos complejos).
2. **Visualiza**: composición de cartera, evolución del MTM USD, fondeo neto
   del año, rendimiento ajustado por fondeo.
3. **Integra con la app principal**: cruza el "Depósito al broker" (transacción
   en gastos) con el "fondeo entrante" en cartera para mostrar el rendimiento
   real ajustado por aportes.

El Excel queda como **fuente de verdad** para la cartera. La app es un
visualizador integrado.

### Lo que queda OUT del MVP
- Alta/edición de movimientos desde la app.
- Parser del CSV del broker.
- Carga de precios desde APIs externas.
- Cálculo propio de cashflows de bonos.
- Cauciones tratadas como instrumentos persistentes.
- Time-Weighted Return calculado por la app.

### Esfuerzo estimado

| Fase                                                       | Esfuerzo |
|------------------------------------------------------------|----------|
| MVP visualizador (importar CSV + dashboards + integración) | 1 fin de semana |
| V2 (si hay confianza después de 1 mes de uso)              | otro premortem primero |

### Reglas de ejecución
1. Plazo MVP estricto: 2 días. Si no se arma en eso, el scope sigue siendo
   muy grande.
2. Gate de salida: reconciliación saldo cartera app === saldo cartera Excel
   ±1% en 3 días distintos.
3. Premortem #2 obligatorio antes de cualquier feature de "alta manual" o
   "precios propios". La complejidad crece superlinealmente.

### Orden en el roadmap

Esta es la feature **más grande y más riesgosa** del backlog. Va al final, sólo
después de:
- Bloque 4 completo de mejoras UX.
- Decidir si se hace o no el chatbot (sección 8).
- Tener un fin de semana completo dedicado.

Ver el HTML del premortem para los 12 modos de fallo, las señales tempranas y
la checklist pre-lanzamiento detallada.

---

## 10. Monetización — opciones honestas para el día que crezca

> Pregunta del usuario: "¿Se puede poner publicidad para evitar cobrar al
> usuario?" Respuesta corta: **se puede técnicamente, pero es mala idea para
> esta app**. Análisis abajo.

### Por qué la publicidad NO encaja en esta app

1. **Mata la confianza.** Una app de finanzas personales pide confianza
   absoluta — el usuario te entrega su balance, sus gastos, sus inversiones.
   Ver banners de "Mejor tarjeta de crédito 2026" al lado de su saldo es la
   receta para que cierre la pestaña. Los apps de finanzas que sobreviven
   (YNAB, Monarch, Copilot, Lunch Money) NO tienen publicidad por algo.

2. **Privacidad y regulación.** Las redes publicitarias (Google AdSense, Meta
   Audience Network) trackean al usuario. En una app con datos financieros, eso
   choca con la Ley 25.326 de Protección de Datos Personales en Argentina y
   con GDPR si algún usuario está en Europa. También contradice el espíritu del
   proyecto: datos del usuario, en SU control, en su DB.

3. **La matemática no cierra.** AdSense paga aproximadamente $1-3 USD por cada
   1000 vistas (RPM). Para ganar $100/mes necesitás ~50.000 vistas mensuales.
   Una app de finanzas personales nunca tiene ese tráfico orgánico, salvo que
   sea un éxito mainstream — y si lo es, ya hay mejores formas de monetizar
   (ver abajo).

### Modelos de monetización mejores para este nicho

| Modelo | Cómo funciona | Pros | Contras |
|---|---|---|---|
| **Freemium** | Core gratis; features avanzadas pagas (alertas, exports PDF, integración con bancos, multi-cuenta) por ~$2-4 USD/mes | Bajo barrier, escala lineal | Requiere tener features premium reales |
| **Una compra única** | Pagás $20-30 USD una vez, app tuya para siempre | Simple, sin recurrencia que enoje | Ingreso lineal con altas, no creciente |
| **Suscripción** | $1-3 USD/mes por todo | Predecible, alineado con uso continuo | Requiere base grande para que valga la pena |
| **Donaciones / Patreon** | Voluntario | Mantiene gratuidad, alineado con comunidad | Ingreso impredecible y bajo |
| **B2B accidental** | Si un contador o estudio adopta la app para gestionar clientes, cobrás por usuario gestionado | Margen alto | Requiere casi rehacer la app para multi-tenant real |

### Recomendación

**No pensar en monetización todavía.** La prioridad ahora es:
1. Que la app sea sólida y vos la uses con confianza (✅ ya).
2. Crecer orgánicamente a 5-10 amigos/familiares activos (1-3 meses).
3. Pulir según feedback real (no hipotético).
4. **Recién después** de eso, evaluar monetización con datos reales sobre lo
   que la gente valora.

Apurar la monetización mata productos buenos antes de que tengan oportunidad
de encontrar a su gente.

### Para que el día que crezca, el camino esté abierto

Sin invertir en monetización ahora, sí podemos dejar el terreno preparado:
- **Schema multi-tenant ya está** (✅ user_id en todas las queries) — soporta
  paying users diferenciados sin migración futura.
- **Auth ya está** (✅ bcrypt + signup) — la base técnica para "free tier" vs
  "paid tier" está.
- **Backups automáticos** (✅) — si después hay paying users, ya tenés la
  confiabilidad técnica para no perder sus datos.

Cuando llegue el momento, agregar:
- Tabla `subscriptions(user_id, plan, valid_until, payment_provider_id)`.
- Decorador `@requires_plan("premium")` en funciones de core que sean premium.
- Integración con MercadoPago (Argentina) y Stripe (internacional).
- Pricing page + landing.

Pero todo eso es trabajo de Fase 5+. Por ahora, **enfocate en hacer la app
buena, no en monetizarla**.
