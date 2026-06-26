# Premortem — Módulo de Cartera de Inversiones

**Fecha del análisis:** 27 de mayo de 2026
**Sometido al premortem:** Extender Radar Financiero con un módulo de gestión de
cartera de inversiones que reemplace o complemente el `Inversiones.xlsx` actual
de Franco.
**Audiencia / usuario:** Franco (inversor avanzado argentino, cartera de USD
~14.500 diversificada en bonos USD, CEDEARs, acciones locales, BTC, cauciones,
letras, ONs).
**Criterio de éxito:**
- Franco abandona el Excel de inversiones después de 1 mes de uso de la app.
- El saldo de cartera del app está dentro de ±1-2% del extracto Inviu.
- Cargar movimientos nuevos toma <2 min vs los 10+ min actuales en Excel.
- El cash flow broker ↔ cuenta corriente personal está reconciliado consistentemente.
- El rendimiento (Rto USD anual vs benchmark SPY) es computable y confiable.

---

## Contexto verificado del Inversiones.xlsx

Lectura directa del workbook subido. 16 hojas, 537 movimientos crudos, 609
movimientos procesados, ~25 instrumentos activos. Resumen:

**Estructura:**
- **LEEME** — guía de uso, flujo de actualización en 4 pasos.
- **Cartera** — vista principal: ticker, cantidad, monto USD, %, FIJA/VARIABLE,
  riesgo (VALUE/GROWTH/DISPONIBILIDADES), Px actual, PxPromCompra. KPIs:
  Total Cartera USD = $14.512, Rto USD = 25.7%, Benchmark SPY YTD = 23.8%.
- **Flujo de Fondos** — proyección 13 años de cupones/amortizaciones de bonos
  mes por mes. Total en julio 2026 = $331.788 (vencimiento AE38).
- **Config** — diccionario crítico:
  - Categorías de operación (COMPRA, VENTA, DIVIDENDO, RENTA, AMORTIZACION,
    RETENCION, CAUCION_VTO, CAUCION_COL, DEPOSITO, RETIRO, REMUNERACION, OTROS).
  - Mapping tickers ARS↔USD (GGAL ↔ GGALD; SPY ↔ SPYD; etc.).
  - Per ticker: descripción, categoría (Acciones, Bonos, Cedears, Letras, ONs,
    Cripto), panel de precios, activo en cartera, moneda cotización, divisor USD.
- **Movimientos Crudo** — 537 filas pegadas del broker (Inviu): Operación,
  Concertación, Liquidación, Descripción, Monto, Cantidad, Precio, Moneda.
- **Movimientos Procesado** — parser automático: agrega columnas Categoría,
  Ticker Base, TC MEP, Monto USD, Es Instrumento, Es Espejo, Δ Cantidad, etc.
- **General** — reconciliación anual: Saldo Inicio, Fondeo Neto, Saldo Fin,
  Utilidad USD, Rend %. Año 2025: 12.7% rendimiento. Año 2026 YTD: 6.7%.
- **Apoyo** — TC MEP actual ($1397), TC histórico, inflación, distribución por
  tipo de riesgo, lista de tenencia con costo promedio.
- **PANEL LIDER / CEDEARS / BONOS / LETRAS / ONs / Futuros / PANEL GENERAL** —
  ~150 instrumentos cada panel, datos del addin BYMADATA. **Esto es clave:** el
  Excel ya tiene precios actualizados automáticamente via addin.
- **Resumen Cartera** — tabla analítica complementaria.

**Lo que el sistema hace hoy (en Excel):**
1. Parsea movimientos crudos del broker → categoriza automáticamente.
2. Mantiene mapping ARS↔USD (GGAL en ARS, GGALD su equivalente USD).
3. Computa cantidad neta por instrumento (compras − ventas + amortizaciones).
4. Valoriza posiciones a MTM en USD (precio actual × cantidad × divisor a USD).
5. Computa costo promedio (PxPromCompra).
6. Proyecta cashflows de bonos a futuro.
7. Computa rendimiento anual ajustado por fondeo neto.
8. Reconcilia con extracto del broker.
9. Multi-moneda: ARS, USD, USD/100 (bonos USD cotizan en porcentaje del nominal),
   ARS/100.

---

## ENCUADRE DEL PREMORTEM

Han pasado 6 meses. Estamos en **noviembre de 2026**. El módulo de cartera de
inversiones de Radar Financiero **fue construido, usado algunas semanas, y
abandonado**. Franco volvió al Excel. ¿Por qué?

---

## Razones de fallo (premortem en bruto)

### 1. Parser del broker se rompe
Inviu cambia el formato de su export CSV (o sus etiquetas de operación). Lo que
parseaba ayer hoy tira NaN. Franco pasa una semana intentando ajustar regex y
mappings, no logra que las 600 filas históricas + las nuevas entren limpias,
se frustra, y vuelve al Excel donde "por lo menos el copy-paste anda".

### 2. Precios no se actualizan automáticamente
No conseguimos un API gratuito confiable para precios BYMA + Wall Street + bonos
argentinos en simultáneo. Franco termina cargando 25 precios a mano todos los
días. El Excel actual, vía el addin BYMADATA, los chupa solos. La app empeora
el flujo en lugar de mejorarlo.

### 3. TC MEP y multi-moneda mal calibrados
El sistema asume un único TC por día, pero en realidad hay TC A3500, MEP, CCL,
oficial, blue. Si la conversión a USD usa el TC equivocado en un movimiento
histórico (ej. usó MEP cuando era A3500 en bonos USD), el costo USD calculado
diverge del extracto. Cuando Franco lo nota, no puede confiar en ningún número.

### 4. Bonos no cuadran (cupones + amortizaciones)
Un bono como AE38D tiene cupones semestrales irregulares + amortizaciones
programadas que reducen la cantidad nominal en el tiempo. Si el sistema no
proyecta esos cashflows (como la hoja "Flujo de Fondos" del Excel) y no
recalcula correctamente el costo después de cada amortización, el rendimiento
del bono queda mal. Bonos = 60% del valor de la cartera de Franco → si fallan,
falla todo.

### 5. Cauciones se tratan mal
La caución es un instrumento técnico de muy corto plazo (días): COLOCAR → VTO
con intereses. Si la app las trata como una posición persistente (como cualquier
acción), o no contempla el cierre automático en el vencimiento, infla la
cartera con falsos activos y duplica cash.

### 6. Reconciliación con extracto del broker no cuadra
Saldo cartera app vs saldo cartera Inviu difiere 3-5% por causas que se acumulan
silenciosamente: precios desactualizados, parser perdió un movimiento, conversión
USD distinta, no contempló retención impositiva, no contempló comisión del 0.25%
y derecho de mercado 0.05%. Franco no puede explicar la diferencia. Pierde
confianza el día que abre Inviu y compara.

### 7. Scope creep / nunca termina
16 hojas de Excel a reemplazar, 600 movimientos históricos, 25 instrumentos
activos, 6 clases (acciones, bonos, CEDEARs, letras, ONs, cripto), multi-moneda
con tipos de cambio variables, proyección de cashflows, reconciliación, panel
de precios. Es un proyecto de 3-4 semanas mínimo, probablemente 6-8 si se hace
bien. Franco lo arranca, llega al 60% en 2 semanas, lo deja "para terminar
después", nunca vuelve. Queda media-construido y la app principal pierde foco.

### 8. Doble fuente de verdad: gastos app vs cartera
Hoy Franco registra "Depósito al broker" como transacción en la app principal
(categoría Inversiones). Si ahora el módulo de cartera también registra ese
depósito como "fondeo entrante", ¿cuál es la fuente de verdad? Si no se
sincronizan, doble carga + riesgo de inconsistencia. Si se sincronizan
automáticamente, lógica compleja con potencial de borrar/duplicar.

### 9. Performance vs benchmark mal calculado
Calcular Rto USD anual ajustado por fondeos (Time-Weighted Return) es
matemática no trivial. Si el sistema muestra 25% anual cuando en realidad es
12% (porque no descontó nuevos aportes), Franco confía en un número falso y
toma decisiones de cartera malas. Si lo descubre, pierde confianza para
siempre.

### 10. El Excel actual es "lo bastante bueno"
Después de 1 mes de fricción con la app nueva (parseo, precios, reconciliación,
bugs), Franco se da cuenta que su Excel le toma 30 min al mes para mantener
y ya lo conoce de memoria. La app le toma 45 min porque la curva de aprendizaje
+ bugs iniciales + cargar precios a mano. ROI negativo de mudarse → vuelve.

### 11. Acoplamiento con la app principal la rompe
Si el módulo de cartera es un add-on dentro de Radar Financiero, complica deploy,
tests, schema. Si se rompe la cartera por un bug, ¿se rompe también la app de
gastos que hoy anda? Si tienen schemas separados pero acoplados, los cambios
en uno afectan al otro. La complejidad técnica degrada la calidad de la app de
gastos que ya estaba estable.

### 12. Pricing API costos o rate limits
Si usamos API paga (TwelveData, Polygon, Alpha Vantage), costos no anticipados o
rate limits cortan el flujo. Free tiers son muy limitados (5-25 requests/min).
Una sola actualización de 25 tickers, varias veces por día, supera los free
tiers. Pagar $10-30/mes una app personal puede ser inaceptable.

---

## Síntesis

### Fallo más probable: combinación de #2 (precios manuales) + #10 (Excel es suficiente)
La app termina exigiendo MÁS mantenimiento manual que el Excel actual (que ya
tiene addin BYMADATA tirando precios solo). Franco lo nota a las 4 semanas y
vuelve.

### Fallo más peligroso: combinación de #6 (reconciliación no cuadra) + #4 (bonos mal calculados)
Una vez que los números del app difieren del extracto Inviu sin explicación
clara, la confianza está rota. **No se reconstruye**. Para inversiones, la
confianza en los números es ABSOLUTA — un Excel medio mal te alerta porque
mirás las celdas; una app medio mal te miente y no te avisás.

### El supuesto oculto
**Que el Excel actual es "manual" y la app sería "automática"**. **FALSO**. El
Excel ya tiene:
- Addin BYMADATA que actualiza precios solo.
- Fórmulas que computan TC, MTM, %, rendimiento.
- Vlookups que mapean tickers automáticamente.
- Flujo aceitado de "pegar movimientos del broker → todo se actualiza".

Para que la app sea una mejora real, no alcanza con replicar; tiene que ser
MEJOR. Y "mejor" en finanzas personales significa: más confiable, no más linda.

### Plan revisado

1. **NO reemplazar el Excel. Visualizar/integrar.** En lugar de matar el Excel,
   construir un módulo en la app que **importa** el "Movimientos Procesado" del
   Excel (CSV export). El Excel sigue siendo la fuente de verdad para la
   cartera; la app agrega dashboards integrados con la pestaña de gastos y un
   panel de "fondeo broker ↔ cuenta corriente" que reconcilia los dos sistemas.
   Esto reduce el scope ~70% sin perder el valor de "ver todo junto".

2. **Acoplamiento crítico único: el flujo de fondos broker ↔ CC personal.**
   Cuando Franco hace un depósito al broker, hoy ya es una transacción en la app
   (motivo "Inversiones" o similar). El módulo de cartera lo cruza con el
   extracto del broker para mostrar "te fondaste $X este mes, tu cartera creció
   $Y, rendimiento real = (Y − X) / X". Esa es la métrica que importa.

3. **MVP estricto: SOLO read-only + integración cash flow.** El primer release:
   - Importás "Movimientos Procesado" del Excel como CSV.
   - La app muestra: composición de cartera, evolución del MTM USD, fondeo neto
     del año, rendimiento ajustado por fondeo.
   - NO permite cargar/editar movimientos individuales.
   - NO maneja precios (los toma del CSV importado).
   - NO maneja bonos complejos ni cauciones (los visualiza tal como vienen, no
     intenta calcularlos él).
   - Reconciliación obligatoria: saldo app vs saldo Excel ±1%.

4. **Plazo y MVP estricto: 1 fin de semana, no 3 semanas.** Si el MVP no se
   arma en 2 días, el scope sigue siendo muy grande. Cortar más.

5. **Premortem antes de avanzar a V2.** Una vez que el MVP read-only está
   funcionando 1 mes y Franco lo usa de verdad, **otro premortem** antes de
   sumar features como "alta de movimientos desde la app" o "cálculo propio de
   precios". La complejidad crece superlinealmente.

6. **Si en algún momento se considera reemplazar al Excel del todo:** atacar
   PRIMERO el problema de precios (que es lo que el Excel hace mejor que la
   app). Sin un mecanismo confiable y automático de actualización de precios, la
   app NUNCA va a ganarle al Excel.

### Checklist pre-lanzamiento

1. ✅ El "Movimientos Procesado" del Excel se importa como CSV en <30 segundos
   sin errores.
2. ✅ Reconciliación: saldo cartera app === saldo cartera Excel ±1%, verificado
   en 3 días distintos.
3. ✅ El "depósito al broker" (transacción en app) y "fondeo entrante"
   (registro en cartera) coinciden al peso, sin doble carga.
4. ✅ Cálculo de rendimiento del año coincide con cálculo manual del Excel para
   2025 cerrado y 2026 YTD.
5. ✅ MVP cubre SÓLO importación + visualización. Edición, alta, precios,
   bonos complejos = OUT del V1, documentado explícitamente.
6. ✅ Documento "Cómo cargar el CSV y mantener sincronizada la cartera" claro,
   <1 página, escrito para Franco-mismo dentro de 6 meses.

---

## Recomendación final

**No empezar a construir esto en la próxima sesión.** Es la feature más grande
que considerás y la que más riesgo tiene de salir mal con costo emocional alto
(perder confianza en tus números de inversión te lastima más que cualquier bug
de la app de gastos).

**Sí dejarlo anotado como Fase 4** en el roadmap, con la versión revisada
"visualizar + integrar, no reemplazar". El scope correcto es 1 fin de semana
de trabajo, no 1 mes. Y se ejecuta sólo después de un segundo premortem cuando
el MVP esté armado.

**Prioridad sugerida del backlog actual:**
1. Bloque 4 de UX (alta rápida, CSS custom, toggle claro/oscuro) — semanas.
2. Chatbot WhatsApp — 1 a 3 días según fase.
3. **Cartera de inversiones (MVP visualizador)** — sólo cuando esté la confianza
   y el tiempo. No antes.
