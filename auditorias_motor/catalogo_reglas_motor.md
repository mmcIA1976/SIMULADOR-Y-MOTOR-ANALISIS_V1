# Catalogo auditable de reglas del motor

Fecha: 2026-07-24
Fase: E1.2
Champion congelado: `rules-v0.12.1-liquidations-readable`
Scoring congelado: `scoring-v0.11-underweighted-risk-cluster`

## 1. Como leer este catalogo

Este documento traduce el codigo ejecutable a reglas humanas. La cobertura
mecanica completa esta en:

- `inventario_reglas_motor_v0_1.json`: codigo, lineas, literales y formulas.
- `matriz_procedencia_funciones_v0_1.json`: procedencia y estado de las 185
  funciones auditadas.

Una fuente que define un dato no valida su uso predictivo. Binance, por ejemplo,
define `fundingRate` y `sumOpenInterest`; no valida que `0.03%`, `0.2%` o un
ajuste de `0.02` sean umbrales correctos para BTC.

Estados:

- `fundamentada`: definicion, aritmetica o proceso respaldado y reproducible.
- `heuristica`: convencion interna no calibrada.
- `empirica_provisional`: nacida de evidencia interna, aun sin validacion
  independiente suficiente.
- `sin_respaldo`: no se localizo fundamento demostrable.

## 2. Semantica real de la salida

### PROB-001 - Salida llamada `tp_probability`

Codigo: `analysis_engine.py:244-329`

Formula previa a calibracion:

```text
TP_score =
  0.50
  + tendencia
  + rating_tecnico
  + precio_vs_entrada
  + volumen
  + order_book
  + momentum
  + regimen
  + fibonacci
  + zona_pendiente
  + taker
  + CVD
  + OI
  + breadth
  - volatilidad
  - liquidez
  - sobreextension
  - funding
  - funding_relativo
  - crowding
  - nivel_intermedio
  - sentimiento
  - HTF_contrario
  - timing
  - barrera
  - contexto_OI
  - contradicciones
```

Se acota primero a `[0.26, 0.74]`. Despues se suman frenos v0.10/v0.11 y se
vuelve a acotar a `[0.22, 0.74]`.

Estado: `incoherente` como probabilidad; `heuristica` como score direccional.

Motivo:

- No se estima mediante frecuencias, likelihood o modelo de primer paso.
- No existe monotonicidad general con la distancia al TP.
- Un bias binario puede dominar diferencias pequenas de alcanzabilidad.
- Los caps ocultan parte de la contribucion acumulada.
- La calibracion fuera de muestra aun no esta demostrada.

Decision: renombrar conceptualmente el champion como score durante la auditoria
y construir en sombra una probabilidad TP-antes-SL calibrable.

### PROB-002 - Caso 872/873 que abrio la auditoria

Codigo: `analysis_engine.py:191`

Para short:

```text
precio_actual >= entrada  -> +0.03
precio_actual <  entrada  -> -0.02
```

El salto discontinuo es de cinco puntos. Fue la unica diferencia material entre
los analisis 872 y 873 y permitio que el TP mas lejano recibiera mayor salida.

Estado: `incoherente`.
Decision: aislar en E1.3 y sustituir por una variable continua de distancia y
alcanzabilidad.

### PROB-003 - Escenario de rango

Codigo: `analysis_engine.py:1849-1855`

```text
compresion o mixto               -> 0.12
contradiccion >= 0.03            -> 0.10
rango reciente < 1.2%            -> 0.08
resto                            -> 0.06
```

Zona pendiente puede sumar hasta `0.04`; calibracion final acota rango a
`[0.04, 0.22]`.

Estado: `heuristica`.
Defecto: mezcla no-resolucion, rango y no-activacion de orden pendiente.

### PROB-004 - Escenario SL

Codigo: `analysis_engine.py:293,329`

```text
SL = max(0.05, 1 - TP - rango)
```

Estado: `heuristica`.
Defecto: SL es el residuo del score TP y no una estimacion independiente de
SL-antes-TP.

### PROB-005 - Intervalos mostrados

Codigo: `analysis_engine.py:1857-1873`

Anchura:

```text
sin contradiccion       -> 0.04
contradiccion < 0.03    -> 0.06
contradiccion >= 0.03   -> 0.08
```

Estado: `sin_respaldo` como intervalo probabilistico. No es intervalo de
confianza, prediccion ni credibilidad; es una banda visual simetrica.

## 3. Fuentes y construccion de datos

| ID | Dato | Fuente real | Construccion | Estado |
|---|---|---|---|---|
| DAT-001 | Precio | Binance USD-M Futures ticker | ultimo precio, cache 12 s; stale maximo 300 s | fundamentada como transporte |
| DAT-002 | Velas | Binance USD-M Futures klines | 240 velas por 5m, 15m, 1h, 4h, 1d, 1w | fundamentada como dato |
| DAT-003 | Profundidad | Binance Futures depth | 20 niveles por lado | fundamentada como dato |
| DAT-004 | Flujo | Binance Futures aggTrades | ultimas 500 operaciones agregadas | fundamentada como dato |
| DAT-005 | Ticker | Binance Futures 24h | cambio, volumen, maximo y minimo | fundamentada como dato |
| DAT-006 | Funding | Binance Futures premium index e historial | ultimo y media de ocho observaciones | fundamentada como dato |
| DAT-007 | OI | Binance Futures OI e historial | cambio primero-ultimo en 5m/1h/1d | fundamentada como dato |
| DAT-008 | Posicionamiento | Binance Futures | long/short global y taker buy/sell | fundamentada como dato |
| DAT-009 | Breadth | CoinGecko top 100 | porcentaje positivo y mediana 1h/24h/7d | heuristica como universo |
| DAT-010 | Mercado global | CoinGecko global | capitalizacion, volumen, dominancias | fundamentada como dato |
| DAT-011 | Sentimiento | Alternative.me | ultimo indice Fear & Greed diario | fundamentada como dato; predictividad no |
| DAT-012 | Liquidaciones | HyperPerps sobre posiciones Hyperliquid | clusters y masa normalizada | heuristica, proveedor tercero |

Regla general: la disponibilidad de una fuente no demuestra que sea fresca,
completa, comparable entre exchanges o predictiva.

## 4. Indicadores y transformaciones

### IND-001 - EMA

Codigo: `data_engine.py:30-37`

```text
alpha = 2 / (periodo + 1)
EMA_t = EMA_(t-1) + alpha * (precio_t - EMA_(t-1))
```

La semilla es el primer cierre de la ventana. Se calculan EMA 9, 21, 50 y 200.
Si faltan 200 velas, EMA200 se sustituye por EMA de hasta 80 cierres.

Estado: `fundamentada` la formula EMA; `heuristica` la ventana, semilla y
sustitucion de EMA200.

### IND-002 - Stack EMA

Codigo: `data_engine.py:326-331`

```text
EMA9 > EMA21 > EMA50 -> bullish
EMA9 < EMA21 < EMA50 -> bearish
resto                -> mixed
```

Estado: `heuristica` como predictor; concepto tecnico reconocido.

### IND-003 - RSI 14

Codigo: `data_engine.py:40-58`

Usa media simple de ganancias y perdidas de los ultimos 14 cambios:

```text
RS = media_ganancias_14 / media_perdidas_14
RSI = 100 - 100 / (1 + RS)
```

Sin datos devuelve 50; sin perdidas devuelve 100.

Estado: `heuristica` como implementacion denominada RSI de Wilder, porque no
mantiene el suavizado recursivo original. Debe renombrarse como variante SMA-RSI
o corregirse.

### IND-004 - ATR 14

Codigo: `data_engine.py:61-71`

```text
TR_t = max(high-low, abs(high-prev_close), abs(low-prev_close))
ATR14 = media_simple de hasta 14 TR
```

Estado: `heuristica` como ATR de Wilder por la misma diferencia de suavizado.

### IND-005 - Rango y volumen

Codigo: `data_engine.py:104-165`

- Maximo/minimo reciente: ultimas 24 velas.
- `recent_range_pct = (high24-low24)/precio * 100`.
- `volume_ratio = ultimo_volumen/media20`.
- Taker buy ratio de vela: suma taker-buy 20 / suma volumen 20.
- Posicion en rango: `(precio-low24)/(high24-low24)`.

Estado: `heuristica`; ventanas internas.

### IND-006 - Soporte y resistencia

Codigo: `data_engine.py:168-188,320-324`

- Lookback: 120 velas.
- Candidatos: highs por encima y lows por debajo.
- Se toman los 12 mas cercanos.
- El nivel final es la media de los cinco primeros.

Estado: `heuristica`. Existe evidencia externa para el concepto, no para este
detector ni para promediar extremos sin validacion de pivote/volumen.

### IND-007 - Fibonacci

Codigo: `data_engine.py:191-316`

- Lookback 180, minimo 34 velas.
- Pivote unico con tres velas a izquierda y derecha.
- Movimiento minimo:
  `max(ATR_pct*1.35, rango_pct*0.18, 0.35%)`.
- Retrocesos: 0.236, 0.382, 0.5, 0.618, 0.786.
- Extensiones: 1.272, 1.618, 2.0, 2.618.
- Se elige el swing valido opuesto mas reciente.

Estado: `heuristica`. Un estudio automatizado encontro que zonas Fibonacci y
no-Fibonacci no diferian estadisticamente. Mantener solo como contexto hasta
ablation y validacion propia.

### IND-008 - Order book

Codigo: `data_engine.py:334-352`

```text
bid_notional = suma(precio*cantidad) top20 bids
ask_notional = suma(precio*cantidad) top20 asks
imbalance = (bid_notional-ask_notional)/(bid_notional+ask_notional)
spread_pct = (best_ask-best_bid)/mid * 100
```

Estado: `empirica_provisional`. La literatura respalda OFI dinamico en mejor
bid/ask; esta foto estatica top-20 no es ese indicador.

### IND-009 - CVD aproximado

Codigo: `data_engine.py:355-379`

Cada aggTrade suma notional si el comprador no fue maker y resta si lo fue.

```text
CVD_ratio = (buy_notional-sell_notional)/(buy_notional+sell_notional)
```

Estado: `empirica_provisional`. Es una proxy de los ultimos 500 aggTrades, no
un CVD historico persistente.

### IND-010 - OI, breadth y sentimiento

- OI: cambio porcentual primero-ultimo de 30x5m, 24x1h o 30x1d.
- Breadth: top 100 por capitalizacion de CoinGecko; umbrales predictivos 58/42.
- Fear & Greed: valor diario 0-100; umbrales predictivos 75/25.

Estado: datos fundamentados, ventanas y umbrales `heuristica`.

## 5. Horizonte y pesos temporales

Codigo: `analysis_engine.py:18-82`

| Horizonte | Tendencia 5m/15m/1h/4h/1d | micro | derivados | macro | HTF | funding |
|---|---|---:|---:|---:|---:|---:|
| intraday_short | 1.25 / 1.35 / 1.00 / 0.45 / 0.15 | 1.00 | 0.85 | 0.15 | 0.60 | 0.35 |
| intraday_wide | 0.35 / 1.10 / 1.35 / 1.00 / 0.35 | 0.55 | 1.00 | 0.35 | 1.00 | 0.75 |
| short_swing | 0.10 / 0.20 / 0.75 / 1.50 / 1.60 | 0.20 | 1.10 | 0.85 | 1.35 | 1.25 |

Estado: `heuristica`. No se encontro manual o estudio que justifique estos
coeficientes exactos.

## 6. Componentes del score direccional

Codigo principal: `analysis_engine.py:174-284,2074-2279`

| ID | Regla exacta | Efecto maximo TP | Estado |
|---|---|---:|---|
| SCO-001 | Tendencia EMA ponderada normalizada >=.55/.20 o <=-.55/-.20 | +.10 / -.09 | heuristica |
| SCO-002 | Rating tecnico normalizado >=.45/.15 o <=-.45/-.15 | +.035 / -.040 | heuristica |
| SCO-003 | Precio actual favorable respecto a entrada | +.030 o -.020 | incoherente |
| SCO-004 | Volumen ratio >1.25 o <0.65 | +.025 o -.015, ponderado | heuristica |
| SCO-005 | Imbalance top20 supera +/-0.12 | +/-0.016, ponderado | empirica_provisional |
| SCO-006 | RSI timing por lado | +.020 o -.025, ponderado | heuristica |
| SCO-007 | Regimen alineado/contrario | aprox. +.020 a -.043 | empirica_provisional |
| SCO-008 | Fibonacci desfavorable/alerta | 0 a -.020 | heuristica |
| SCO-009 | Zona pendiente | cap +.025 / -.035 | empirica_provisional |
| SCO-010 | Taker ratio >1.12 o <0.88 | +/-0.020, ponderado | heuristica |
| SCO-011 | CVD ratio >.12 o <-.12 | +/-0.018, ponderado | empirica_provisional |
| SCO-012 | OI >=.2% y signo precio 24h | +/-0.020, ponderado | heuristica |
| SCO-013 | Breadth 58/42 y mediana concordante | +/-0.020, ponderado | heuristica |
| SCO-014 | SL dentro de 35% de max(rango, ATR) | -.070 | heuristica |
| SCO-015 | Spread >.04% | -.030 | heuristica |
| SCO-016 | Distancia a EMA21 >max(.5%, ATR*1.8) | -.025 | heuristica |
| SCO-017 | Funding long >.03% o short <-.03% | -.025 por peso | heuristica |
| SCO-018 | Funding actual >=1.8x media y signo saturado | -.010 por peso | heuristica |
| SCO-019 | Ratio cuentas long >2 o short <.5 | -.015 | heuristica |
| SCO-020 | Barrera S/R antes de max(.25%, 35% TP) | -.025 | heuristica |
| SCO-021 | Fear/Greed long >=75 o short <=25 | -.015 | heuristica |
| SCO-022 | Stack EMA de confirmacion contrario | -.018 por peso HTF | heuristica |
| SCO-023 | RSI extremo y precio extendido | -.020 | heuristica |
| SCO-024 | Barrera antes de 55%/85% del TP | -.025 / -.012 | heuristica |
| SCO-025 | Precio 24h acompana pero OI cae <-.2% | -.012 por peso | heuristica |
| SCO-026 | 2/3/4 contradicciones | -.018/-.032/-.045 | heuristica |

Ningun peso de esta tabla queda clasificado como externamente validado.

## 7. Rating tecnico interno

Codigo: `analysis_engine.py:2179-2279`

Por temporalidad:

```text
stack EMA bullish/bearish       +0.55 / -0.55
precio vs EMA21 +/-0.08%        +0.25 / -0.25
RSI 45-65                       +0.20
RSI >75                         -0.25
RSI <25                         +0.10
RSI 35-45                       +0.05
short                           multiplica todo por -1
cap                             [-1,1]
```

La inversion completa para short tambien invierte la interpretacion de cada
tramo RSI. Estado: `heuristica`; revisar semantica en E1.3.

## 8. Fibonacci aplicado al plan

Codigo: `analysis_engine.py:619-726`

Score base 50:

| Condicion | Puntos |
|---|---:|
| Swing alineado / contrario | +10 / -14 |
| Entrada 0.5-0.618 | +14 |
| Retroceso superficial | +6 |
| Extension o entrada tardia | -8 |
| Retroceso extremo/estructura rota | -12 |
| Entrada cerca de nivel | +4 |
| TP cerca de extension | +5 |
| TP en extension sin nivel | -5 |
| SL cerca de nivel Fib | -4 |
| Confluencia S/R | +6 |

Score acotado a `[18,88]`. Solo score <=46 resta TP; Fibonacci favorable no
suma TP desde v0.10. Puede sumar riesgo 0.02/0.04 y riesgo de ejecucion 5/8.

Estado: `heuristica`; decision: contexto secundario y prueba de retirada.

## 9. Ordenes pendientes y zonas

Codigo: `analysis_engine.py:1146-1425`

### ZON-001 - Confluencia

Base 50:

- Fibonacci favorable +14; alerta/desfavorable -10.
- Nivel deseado dentro de tolerancia +13; cercano +6; lejano -5.
- Rating tecnico >=62 +8; <=42 -8.
- Regimen alineado +8; rebote contra tendencia -7.
- Tolerancia `max(.18%, min(.75%, ATR*0.8))`.

Estado: `heuristica`.

### ZON-002 - Activacion

Base 0.50:

- Distancia <=0.75 ATR: +0.18.
- Distancia <=1.5 ATR: +0.10.
- Distancia >max(rango,2.5 ATR): -0.16.
- Regimen en direccion de activacion: +/-0.06.
- Volumen ratio >=1.25: +0.04.
- Cap `[0.05,0.90]`.

Estado: `sin_respaldo` como probabilidad calibrada.

### ZON-003 - Barrida

Base 45:

- SL dentro del ruido `max(ATR, rango*0.35)`: +28.
- SL dentro de 1.6 veces ruido: +12.
- SL fuera: -8.
- Imbalance adverso en limit pullback: +8.
- Alto >=68; medio >=42; bajo <42.

Estado: `heuristica`.

### ZON-004 - Reaccion

Pullback:

```text
rechazo = .34 + (confluencia-50)/130 - (barrida-45)/220
ruptura = .28 + (barrida-45)/180 - (confluencia-50)/170
```

Breakout:

```text
ruptura = .35 + (tecnico-50)/140 + (volumen-1)*.08 - (barrida-45)/260
rechazo = .30 + (barrida-45)/180 - (tecnico-50)/180
```

Estado: `sin_respaldo` como probabilidad; formulas de diseno interno.

### ZON-005 - Ajuste final

- Pullback favorable: +0.018.
- Pullback de barrida: -0.025 y riesgo +0.035.
- Ruptura favorable: +0.014.
- Falsa ruptura/barrida: -0.025 y riesgo +0.035.
- Confluencia excepcional: +0.007.
- Confluencia, camino o invalidacion debiles: -0.012 cada uno.
- Activacion <.28/.42: rango +.04/+.02.
- Caps TP `[-.035,+.025]`, rango `[0,.04]`, riesgo `[0,.06]`.

Estado: `empirica_provisional`; auditoria interna v0.9, sin holdout.

## 10. Frenos de riesgo v0.10 y v0.11

Codigo: `analysis_engine.py:729-1056`

Todos los deltas se acumulan. Caps globales: TP minimo -0.16, riesgo +0.28,
calidad -35, confianza -28, EV score -30 y ejecucion +32.

| Flag | Disparador | TP | Riesgo | Cap/decision |
|---|---|---:|---:|---|
| CAL-001 | SL >=.55 | -.045 | +.10 | D y observar |
| CAL-002 | SL >=.50 | -.025 | +.06 | C |
| CAL-003 | TP <.40 | -.025 | +.07 | D y observar |
| CAL-004 | tecnico <40 | -.020 | +.07 | C |
| CAL-005 | R/R >=3 | -.020 o -.035 | +.08 | C |
| CAL-006 | TP distante >=3% | -.025 | +.07 | C |
| CAL-007 | SL <.25% | -.025 | +.10 | C |
| CAL-008 | SL >=3% | 0 | +.08 | C |
| CAL-009 | precio 24h contrario >=.25% | -.025 | +.05 | C |
| CAL-010 | stack EMA 15m contrario | -.020 | +.04 | C |
| CAL-011 | precio vs EMA21 1h contrario >.08% | -.020 | +.04 | C |
| CAL-012 | zona pendiente ya negativa | -.015 | +.04 | C |
| CAL-013 | stop breakdown | -.030 | +.08 | D y observar |
| CAL-014 | barrida alta | -.020 | +.05 | C |
| CAL-015 | falsa ruptura | -.020 | +.05 | C |
| CAL-016 | Fib extremo + sentimiento extremo | -.035 | +.08 | C |
| CAL-017 | anterior + CVD contrario | -.015 | +.03 | C |
| CAL-018 | RSI extremo + >=2 riesgos | -.012 | +.025 | C |
| CAL-019 | anterior dentro de Fib+sentimiento | -.008 | +.015 | C |

Estado:

- CAL-001 a CAL-015: `empirica_provisional` sobre auditoria v0.9, sin
  validacion temporal independiente.
- CAL-016 a CAL-019: `empirica_provisional` con muestra especialmente pequena;
  el cluster principal procedia de tres fallos.

No deben considerarse reglas fiables solo por estar desplegadas.

## 11. Riesgo, calidad, confianza y decision

### OUT-001 - `risk_score`

Codigo: `analysis_engine.py:357-379`

Suma fija de banderas:

```text
stop estrecho .20; R/R<1.2 .12; rango>2.5 .08; spread .06;
sobreextension .05; funding .06; funding relativo .04;
crowding .04; nivel .05; sentimiento .03; HTF .07;
timing .05; barrera .05; contradiccion fuerte .08;
mas Fibonacci, zona y calibracion.
```

Niveles: alto >=.42, medio-alto >=.24, medio >=.12, bajo <.12.
Estado: `heuristica`.

### OUT-002 - Calidad de operacion

Codigo: `analysis_engine.py:1929-1945`

```text
42
+ 16% del score R/R mapeado 0.8..3.2
+ 22% del score EV mapeado -0.8%..1.2% notional
+ 12% de desviacion Fibonacci frente a 50
- min(22, riesgo_precio_pct*4.5)
- frenos de calibracion
```

Estado: `heuristica`.

### OUT-003 - Riesgo de ejecucion

Base 30 mas volatilidad*220, nivel*300, liquidez*250, spread mapeado*0.35,
Fibonacci y calibracion. Cap 0-100.

Estado: `heuristica`.

### OUT-004 - Confianza

Base 70:

- contradiccion `-penalizacion*700`;
- HTF -12;
- regimen `+bias*420`;
- taker y CVD opuestos -12;
- ajuste tecnico entre -16 y +6;
- freno v0.10/v0.11.

Cap 15-95. Alta >=76, media >=61, media-baja >=46, baja <46.

Estado: `heuristica`; no es confianza estadistica.

### OUT-005 - Setup

- A: TP >=.62, riesgo <.20, EV score >=58.
- B: TP >=.52, riesgo <.36, EV score >=50.
- C: TP >=.44, EV score >=42.
- D: resto.

Los caps de calibracion pueden degradar la nota.
Estado: `heuristica`.

### OUT-006 - Decision

Orden:

1. `force_observar` -> observar.
2. EV monetaria negativa -> observar.
3. A/B, riesgo no alto y confianza alta/media -> simular.
4. B/C y riesgo no alto -> simular con tamano prudente.
5. Resto -> observar.

Estado: `heuristica`. Es regla de decision, no estimacion de mercado.

## 12. Esperanza matematica

Codigo: `analysis_engine.py:1876-1907`

```text
notional = margen * leverage
gross_win = notional * distancia_TP
gross_loss = notional * distancia_SL
fees = notional * 0.0008
slippage = notional * max(spread, 0.0002)
funding = notional * abs(funding_actual)
coste = fees + slippage + funding
EV = TP*net_win - SL*net_loss - rango*coste
```

Estado:

- Estructura de esperanza: `fundamentada`.
- Inputs TP/SL/rango: `incoherente` como probabilidades.
- Fee 0.08%, un funding y suelo de slippage: `heuristica`; no consulta el tier
  real del usuario, tiempo hasta cierre ni numero de periodos de funding.

Por tanto la EV actual es orientativa, no una esperanza monetaria calibrada.

## 13. Heatmap de liquidaciones

Codigo: `analysis_engine.py:1471-1632`, `liquidation_data.py`

- Fuente: HyperPerps, alcance Hyperliquid.
- Para short: longs debajo son masa objetivo; shorts encima son masa adversa.
- Para long: shorts encima son masa objetivo; longs debajo son masa adversa.
- Tolerancia: `max(.2%, ATR*.5)` acotada a `.2-.75%`.
- Lectura desfavorable si masa adversa/objetivo >=1.5; favorable <=1/1.5.
- Squeeze alto >=3; medio >=1.25 o cluster adverso antes del SL.

Estado: `heuristica`, observacional.
Invariante actual: `affects_scoring = false`. No modifica TP, SL, riesgo, grado,
confianza ni decision.

## 14. Motor de aprendizaje

Codigo: `app.py:2358-3665`, `learning_evidence.py`, `economic_metrics.py`

### LEA-001 - Separacion temporal

Los datos pre-trade, outcomes post-trade y etiquetas diagnosticas se guardan en
secciones distintas y versionadas.

Estado: `fundamentada` como control contra leakage.

### LEA-002 - Resultado del plan

Se reconstruye TP/SL mediante velas Binance 1m y, si ambos limites aparecen en
la misma vela, aggTrades cuando estan disponibles. Casos irresolubles se marcan
ambiguos.

Estado: `fundamentada` como evidencia; desempates `heuristica` auditable.

### LEA-003 - Veredicto del analisis

Un analisis se considera advertido si ocurre cualquiera:

- setup D/E o confianza baja/media-baja;
- decision observar;
- TP < SL;
- EV negativa;
- Fibonacci alerta/desfavorable;
- zona negativa, riesgo de zona >=.02 o barrida alta.

El resultado se etiqueta como exito apoyado, exito contra analisis, riesgo
advertido, riesgo advertido pero subponderado o riesgo no detectado.

Estado: `heuristica` retrospectiva. No puede entrar como feature pre-trade.

### LEA-004 - Riesgo subponderado

Se activa cuando hay al menos tres senales fuertes favorables, tres advertencias
materiales y ademas alta confianza, setup A/B o confianza score >=75.

Estado: `empirica_provisional`. Es diagnostico, no filtro autorizado.

### LEA-005 - Tipo de fallo

Prioridad:

1. Barrida alta de zona.
2. Riesgo de zona >=.02.
3. Camino al TP <=40.
4. Tecnico desfavorable o direccion <=40.
5. R/R <1.15.
6. MFE >.6%.
7. Riesgo no clasificado.

Estado: `heuristica` retrospectiva y dependiente del resultado.

### LEA-006 - Accionabilidad

Cada senal declara:

```text
actionability = aggregate_only
minimum_comparable_cases = 30
```

Treinta casos permiten investigar un patron, no promoverlo. La politica de
promocion acordada exige al menos 50 casos nuevos comparables, con minimo diez
exitos y diez fallos, validacion temporal y challenger.

Estado: `fundamentada` como barrera de gobernanza; el numero 30/50 es politica
prudencial, no teorema estadistico.

### LEA-007 - MFE, MAE y economia

MFE/MAE se reconstruyen con velas 1m cuando la cobertura es completa. La
economia se normaliza a notional, retorno sin apalancar, retorno sobre margen y
R-multiple. Cierres manuales o evidencia incompleta conservan exclusiones.

Estado: `fundamentada` como normalizacion, con calidad declarada.

### LEA-008 - Lo que el aprendizaje no hace

- No cambia automaticamente pesos.
- No reentrena un modelo estadistico.
- No transforma etiquetas retrospectivas en predictors.
- No sobrescribe la recomendacion historica.
- No ha producido una probabilidad calibrada.

Hasta hoy, la modificacion derivada del aprendizaje fue manual y versionada:
los frenos v0.10/v0.11. Siguen clasificados como evidencia provisional.

## 15. Cobertura y deuda declarada

Matriz E1.2:

- 185 funciones clasificadas de 185.
- 105 funciones con reglas o convenciones.
- 72 funciones `fundamentada`.
- 14 funciones `empirica_provisional`.
- 99 funciones `heuristica`.
- 1.528 apariciones de literales numericos preservadas.
- 3.317 fragmentos de formula preservados.

La ausencia de funciones `sin_respaldo` en la matriz no significa que todos los
pesos tengan respaldo. Significa que cada funcion tiene procedencia explicita:
cuando no hay fuente externa, se identifica como heuristica interna. En este
catalogo, las salidas que se presentan como probabilidades sin calibracion se
marcan ademas como incoherentes semanticamente.

## 16. Regla de cierre de E1.2

No se autoriza cambiar el champion con este documento. E1.3 debe probar:

- monotonicidad al alejar/acercar TP y SL;
- continuidad alrededor de cada umbral;
- doble conteo entre tendencia, rating tecnico, regimen y HTF;
- unidades y horizontes;
- caps y zonas muertas;
- separacion entre alcanzabilidad, direccion, ejecucion y EV.
