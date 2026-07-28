# Correccion auditable de la integracion M5-M6 v0.3

Fecha: 2026-07-28

## Objeto

Corregir el desacoplamiento por el que el motor probabilistico M6 recibia
directamente solo un subconjunto reducido de variables, mientras que la
ejecucion completa de las 27 reglas M5 no estaba integrada en el analisis
servido al usuario.

Esta correccion no cambia formulas historicas ni inventa coeficientes. Hace
que cada analisis:

1. adquiera los datos publicos disponibles antes del corte temporal;
2. ensamble las entradas de las 27 reglas;
3. ejecute y registre las 27 trazas M5;
4. derive las covariables autorizadas exclusivamente desde dichas trazas;
5. calcule M6;
6. complete la segunda pasada economica M5 con las probabilidades M6;
7. exponga estados, motivos, dependencias y efectos en la traza final.

## Versiones activas

- Aplicacion: `app-v0.21.0-m5-integrated`
- Motor servido: `M6-M5-INTEGRATED-v0.3`
- Calculo probabilistico: `M6-calibrated-competing-risks-v0.3-m5-integrated`
- Artefacto de coeficientes conservado: `M6-CANDIDATE-NO-H-RIDGE-10-v0.2`
- Fuentes: `data-sources-v0.13-binance-public-m5-context`
- Contrato: `data-contract-v0.6-m5-live-context`

La version del motor y la del artefacto estadistico se registran por
separado. El artefacto no se renombra ni se presenta como recalibrado.

## Fuentes incorporadas

Todas son consultas publicas de Binance y se capturan con un mismo corte
preanalisis:

- velas cerradas USD-M Futures;
- libro de ordenes USD-M Futures;
- mejor bid/ask USD-M Futures;
- mejor bid/ask Spot;
- estado del simbolo Spot;
- mark price, index price, funding actual y proximo evento;
- configuracion del intervalo de funding;
- historial realizado de funding;
- historial de open interest;
- historial de taker buy/sell.

Una fuente ausente produce `blocked`, `deferred` o `not_applicable`. No se
rellenan comisiones, alfa, funding futuro ni valores neutrales ficticios.

## Funcion efectiva de las 27 reglas

| Regla | Funcion en el motor integrado | Efecto probabilistico |
|---|---|---|
| 01 Horizon sampling | Seleccion exacta de intervalo y muestras | Entrada base |
| 02 Plan geometry | Distancias logaritmicas TP/SL | Entrada base |
| 03 Log returns | Serie de retornos cerrados | Entrada base |
| 04 Realized volatility | Volatilidad realizada del horizonte | Entrada base |
| 05 Normalized barrier geometry | Barreras normalizadas por volatilidad | Entrada base |
| 06 Pending activation | Compuerta de aplicabilidad | Solo entrada MARKET |
| 07 Exponential smoother | Suavizado, condicionado a alfa aprobada | Ninguno mientras no exista alfa aprobada |
| 08 Path structure | Eficiencia direccional H | Coeficiente ajustado igual a cero |
| 09 Prior extrema | Extremo previo entre entrada y TP | Covariable ajustada activa |
| 10 Volatility rank | Percentil frente a 60 ventanas | Covariable ajustada activa |
| 11 MTF hierarchy | Eficiencia direccional 2H y 4H | Covariables ajustadas activas |
| 12 Continuous regime | Contexto continuo de regimen | Cero: sin coeficiente validado |
| 13 Aggressor imbalance | Desequilibrio taker buy/sell | Cero: sin coeficiente validado |
| 14 Open interest change | Variacion exacta de OI en H | Cero: sin coeficiente validado |
| 15 Price-OI state | Estado conjunto precio/OI | Cero: sin coeficiente validado |
| 16 Spot-futures basis | Base Spot/Futures sincronizada | Cero: sin coeficiente validado |
| 17 Mark-index premium | Prima mark/index | Cero: sin coeficiente validado |
| 18 Funding state | Estado y carga realizada de funding | Cero: sin coeficiente validado |
| 19 Derivatives context | Contenedor trazable de derivados | Cero: sin coeficiente validado |
| 20 Quoted spread | Spread observable | Capa economica |
| 21 Depth sweep | VWAP e impacto de ejecucion | Capa economica |
| 22 Fee scenarios | Comisiones autenticadas por rol | Capa economica |
| 23 Funding cashflow | Flujo de funding dentro del horizonte | Capa economica |
| 24 Plan exposure | Notional, cantidad, riesgo y recompensa | Capa economica |
| 25 Net payoffs | Resultados netos por desenlace | Capa economica |
| 26 Expected value | Valor esperado con probabilidades M6 | Capa economica |
| 27 Evaluation readiness | Estado de disponibilidad economica | Capa economica |

Las reglas 12-19 funcionan, calculan y quedan trazadas, pero todavia no
alteran TP/SL porque el artefacto activo no contiene coeficientes validados
para ellas. Asignarles pesos manuales violaria el contrato de rigor.

Las reglas 20-27 no deben alterar la probabilidad fisica de tocar TP o SL.
Calculan viabilidad, costes y valor esperado en una capa economica separada.

## Verificacion real

Analisis BTCUSDT realizado contra Binance el 2026-07-28:

- trazas M5: `27`;
- `evaluated`: `23`;
- `not_applicable`: `1`;
- `blocked`: `3`;
- errores: `0`;
- probabilidades: TP `0.178978`, SL `0.322198`, vencimiento `0.498824`;
- suma probabilistica: `1.0`.

Estados no evaluados en esa captura:

- regla 07: `alpha_not_approved`;
- regla 22: `missing_commission_rate`;
- regla 25: `dependency_not_evaluated`, por la regla 22;
- regla 26: `dependency_not_evaluated`, por la regla 25.

La regla 23 se evaluo a cero porque no habia un evento de funding dentro del
horizonte. Si existe un evento y su tasa futura aun no se conoce, queda
`deferred` en vez de reutilizar indebidamente la tasa anterior.

## Pruebas

- pruebas especificas M5/M6: `45/45`;
- suite completa: `615/615`;
- compilacion Python: correcta;
- sintaxis de `app.js`: correcta;
- consulta real a Binance: correcta.

## Limite pendiente

La integracion funcional queda corregida. Para que las reglas 12-19 puedan
modificar TP/SL hace falta un nuevo conjunto de coeficientes estimado y
validado con observaciones preoperacion comparables. Esta correccion prepara
y registra exactamente esos datos; no declara una calibracion que aun no se
ha realizado.

No se ha modificado el motor de aprendizaje, no se ha desplegado online y no
se han alterado los artefactos historicos congelados de M8.
