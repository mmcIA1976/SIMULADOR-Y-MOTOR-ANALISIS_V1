# M3 - Contrato y auditoria de datos pre-trade

Fecha: 2026-07-27
Estado: COMPLETADA Y APROBADA EL 2026-07-27

## 1. Limite de la fase

M3 certifica significado, origen, mercado, campos, unidades, tiempo,
frescura, cobertura, retencion y politica de ausencia de los datos P0.
No define reglas predictivas, indicadores, pesos ni modelo probabilistico.
No modifica la aplicacion productiva y M4 no se ha iniciado.

La documentacion oficial acredita que el dato existe y que significan
sus campos. No acredita que el dato prediga TP o SL; esa hipotesis
debera formularse en M4 y verificarse despues.

## 2. Universo comprobado

Pares: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `INJUSDT`.

Marcos: `intraday_short`, `intraday_wide`, `short_swing`.

Mercados: Binance USD-M Futures perpetuos y Binance Spot.

La auditoria viva fechada paso **76/76** comprobaciones
publicas de esquema y cobertura. La comision de usuario no se consulto
porque exige credenciales y firma; su fuente queda aprobada de forma
condicional, no fingida como dato anonimo.

Liquidaciones HyperPerps/Hyperliquid quedan fuera de M3 porque el bloque
12 es P1. Su integracion actual no se usa para certificar el nucleo P0.

Aclaracion posterior al cierre `M3-CLARIFICATION-001`: M4.2 detecto
que `trigger_condition` ya era recibido por `POST /api/analyze` pero
faltaba en la lista de campos de `M3-DATA-001`. Se incorpora para
reconstruir entradas pendientes. No cambia proveedor, endpoint,
conclusiones ni produccion.

Aclaracion posterior al cierre `M3-CLARIFICATION-002`: M4.5 detecto
que `margin` y `leverage` ya eran recibidos por `POST /api/analyze`
pero faltaban en `M3-DATA-001`. Se incorporan para separar geometria
de mercado, exposicion y perdida sobre margen. No cambia proveedor,
endpoint, conclusiones ni produccion.

## 3. Contratos de datos

Se definen **18 contratos**:

| ID | Dato | Endpoint | Fuente | Estado actual |
|---|---|---|---|---|
| `M3-DATA-001` | Plan propuesto por el usuario | `POST /api/analyze` | `approved_internal_source` | `implemented_noncompliant` |
| `M3-DATA-002` | Reglas y metadatos USD-M Futures | `GET /fapi/v1/exchangeInfo` | `approved_public_source` | `not_implemented` |
| `M3-DATA-003` | Reloj del proveedor USD-M Futures | `GET /fapi/v1/time` | `approved_public_source` | `not_implemented` |
| `M3-DATA-004` | Ultimo precio USD-M Futures | `GET /fapi/v2/ticker/price` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-005` | Velas USD-M Futures | `GET /fapi/v1/klines` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-006` | Profundidad USD-M Futures | `GET /fapi/v1/depth` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-007` | Operaciones agregadas USD-M Futures | `GET /fapi/v1/aggTrades` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-008` | Mejor bid/ask USD-M Futures | `GET /fapi/v1/ticker/bookTicker` | `approved_public_source` | `not_implemented` |
| `M3-DATA-009` | Estadistica movil 24h USD-M Futures | `GET /fapi/v1/ticker/24hr` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-010` | Mark, indice y funding actual USD-M Futures | `GET /fapi/v1/premiumIndex` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-011` | Historial de funding USD-M Futures | `GET /fapi/v1/fundingRate` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-012` | Configuracion del intervalo de funding | `GET /fapi/v1/fundingInfo` | `approved_public_source` | `not_implemented` |
| `M3-DATA-013` | Open interest actual USD-M Futures | `GET /fapi/v1/openInterest` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-014` | Historial de open interest USD-M Futures | `GET /futures/data/openInterestHist` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-015` | Volumen taker buy/sell USD-M Futures | `GET /futures/data/takerlongshortRatio` | `approved_public_source` | `implemented_noncompliant` |
| `M3-DATA-016` | Reglas y metadatos Binance Spot | `GET /api/v3/exchangeInfo` | `approved_public_source` | `not_implemented` |
| `M3-DATA-017` | Mejor bid/ask Binance Spot | `GET /api/v3/ticker/bookTicker` | `approved_public_source` | `not_implemented` |
| `M3-DATA-018` | Comision efectiva del usuario USD-M Futures | `GET /fapi/v1/commissionRate` | `approved_conditional_auth_source` | `not_implemented` |

Las fuentes son viables; eso no significa que la ruta productiva
actual las capture con el contrato exigido. Ningun dato incompleto
queda autorizado por defecto para M4.

## 4. Politica temporal

- Cada consulta registra `requested_at` y `received_at`.
- Cada timestamp del proveedor se conserva sin sustituirlo.
- Todo timestamp predictivo debe ser anterior o igual a `analysis_at`.
- Datos de tiempo real: antiguedad maxima de 30 s.
- Captura completa del snapshot: maximo 15 s.
- Latencia maxima por consulta: 10 s.
- Las velas abiertas se separan; solo una vela cuyo cierre sea
  anterior a `analysis_at` cumple el contrato de vela cerrada.
- OI y taker periodicos conservan timestamp y periodo exactos.
- Los limites anteriores son politica operativa del proyecto, no
  promesas de latencia atribuidas a Binance.

## 5. Ausencia y degradacion

- Dato obligatorio ausente, stale, futuro, invalido o no soportado:
  bloquea el bloque o produce evidencia insuficiente.
- Dato condicional ausente: la regla futura no se evalua.
- Nunca se crean RSI=50, volumen=1, cambio=0 u otra evidencia neutral.
- Comision exacta ausente: puede mantenerse separada la probabilidad
  de mercado, pero no se publica EV ni decision exacta de ejecucion.
- La calidad y el motivo de bloqueo forman parte de la traza.

## 6. Reconstruccion historica

La API no equivale a un archivo historico propio:

- `aggTrades` USD-M: solo las ultimas 24 horas;
- historial de OI: aproximadamente un mes;
- volumen taker: 30 dias;
- profundidad, book ticker, precio y configuraciones: estado actual;
- velas y funding permiten consulta historica, pero Binance no
  compromete en estas fichas una retencion ilimitada.

Para reproducir exactamente un analisis futuro, M5 debera almacenar
el payload bruto, sus timestamps, parametros, version y hash al
momento del analisis. No se declarara reconstruible lo que no lo sea.

## 7. Matriz P0

La matriz contiene **216 filas**:
12 bloques x
6 pares x
3 marcos.

M3 vincula datos con bloques. Los identificadores de reglas exactas
siguen como `not_defined_until_M4`; inventarlos en esta fase violaria
la hoja de ruta. Actualmente hay **0** filas listas para una
revision rigurosa porque las rutas actuales no cumplen aun los
contratos temporales y de ausencia.

## 8. Fallos del pipeline actual

Se reproducen **15 fallos**,
**10 criticos** y
**5 altos**:

| ID | Severidad | Hallazgo |
|---|---|---|
| `M3-CURRENT-FAIL-01` | `critical` | analysis_at is stamped after analyze_trade finishes and no analysis_started_at or source-level data_cutoff is recorded. |
| `M3-CURRENT-FAIL-02` | `critical` | P0 Binance observations do not retain requested_at, received_at and provider timestamps in the snapshot. |
| `M3-CURRENT-FAIL-03` | `critical` | The current open candle is not distinguished from closed candles before indicators are calculated. |
| `M3-CURRENT-FAIL-04` | `critical` | Missing candles become neutral-looking EMA, RSI, ATR and volume values instead of blocking evidence. |
| `M3-CURRENT-FAIL-05` | `critical` | Optional HTTP helpers and future_value suppress provider errors into None, empty objects or empty arrays without a field-level failure reason. |
| `M3-CURRENT-FAIL-06` | `high` | Order flow uses the latest 500 aggregate trades, so its elapsed time changes with market activity. |
| `M3-CURRENT-FAIL-07` | `critical` | OI and taker period timestamps are discarded, so freshness and completed-period status cannot be proved. |
| `M3-CURRENT-FAIL-08` | `high` | OI and taker history are provider-limited to about one month and no immutable local raw archive exists. |
| `M3-CURRENT-FAIL-09` | `high` | Funding history is averaged over eight rows without funding interval metadata or retained event times. |
| `M3-CURRENT-FAIL-10` | `critical` | The P0 spot-versus-futures block has no Binance Spot source in the current market snapshot. |
| `M3-CURRENT-FAIL-11` | `critical` | Commission and minimum slippage are hardcoded rather than captured from account and market data. |
| `M3-CURRENT-FAIL-12` | `high` | Symbol status, contract type, quote asset and exchange precision are not validated through exchangeInfo. |
| `M3-CURRENT-FAIL-13` | `high` | The current price route is deprecated v1 instead of the documented v2 route and its time field is discarded. |
| `M3-CURRENT-FAIL-14` | `critical` | A missing 24h ticker becomes zero change, zero volume and zero barriers while analysis continues. |
| `M3-CURRENT-FAIL-15` | `critical` | No field-level quality, capture span or blocking-reason contract exists for the assembled snapshot. |

Los fallos no significan que Binance carezca de los datos. Significan
que el snapshot actual no conserva pruebas suficientes sobre su
tiempo, calidad, cobertura o ausencia para un motor riguroso.

## 9. Decisiones principales

1. Binance oficial cubre gratuitamente el nucleo P0 de mercado.
2. Los seis pares existen hoy en Futures y Spot.
3. Spot-futuros es viable pero aun no esta implementado.
4. La comision exacta requiere autenticacion o configuracion explicita.
5. OI, taker y trades requieren captura local para superar su retencion.
6. El snapshot productivo debe reconstruirse en M5; M3 no lo modifica.
7. HyperPerps/liquidaciones permanecen P1 y fuera de esta fase.

## 10. Fuentes oficiales

- Binance USD-M Futures - public market data and exchange metadata: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
- Binance USD-M Futures - signed user commission rate: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account
- Binance Spot - public spot market data: https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market
- Binance Spot - spot exchange metadata and server time: https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/general

## 11. Estado y siguiente fase

SHA-256 del catalogo: `a2bc0b4facd0801a63a6c39b2cd7f8448561c7eb8c22b6c0d170a3fe78e537dd`.
SHA-256 de la matriz: `fe1f471dd375049347990ec1d01c2830b3eccd9db7eab06f26dc5d3fadad009b`.

M3 queda completada y aprobada expresamente por el propietario el
2026-07-27. Produccion no ha cambiado. M4 no se ha iniciado; sera
la definicion formal de reglas y combinaciones P0.
