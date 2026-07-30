# Contrato maestro de biblioteca de reglas v0.1

Fecha: 2026-07-29
Estado: IMPLEMENTADO; SIN NUEVOS EFECTOS PREDICTIVOS

## 1. Objetivo

Materializar una biblioteca unica y validable para la Fase 1:

- separar operadores base, evidencia predictiva, interacciones, bloqueos y
  reglas economicas;
- documentar las 11 reglas predictivas actuales sin presentarlas como
  validadas;
- registrar hipotesis recuperables del motor antiguo y de la revision externa;
- impedir que una candidata incompleta o sin aprobacion afecte TP/SL;
- preparar atribucion por regla y por familia para el aprendizaje futuro.

## 2. Catalogo resultante

Version:

```text
TP-SL-RULE-LIBRARY-v0.1
```

Composicion:

| Estado | Cantidad |
|---|---:|
| Operadores base activos | 5 |
| Reglas predictivas activas provisionales | 11 |
| Gates deterministas de calidad activos | 2 |
| Reglas economicas de ejecucion activas | 2 |
| Reglas implementadas en observacion | 16 |
| Reglas bloqueadas por datos | 2 |
| Total de fichas | 38 |

El catalogo estructurado se encuentra en:

```text
auditorias_motor/catalogo_maestro_biblioteca_predictiva_v0_1.json
```

Su SHA-256 canonico es:

```text
c31778be090469de4390a3a89bcadc2bcce2c0dd9e5b7ca6ef183be2d0460cfa
```

## 3. Cinco operadores base

No se cuentan como senales independientes:

1. muestreo exacto del horizonte;
2. geometria long/short del plan;
3. retornos logaritmicos pre-trade;
4. volatilidad realizada;
5. barreras normalizadas por volatilidad.

Su traza se incorpora al registro estructurado de aprendizaje como baseline,
pero no recibe puntos ni peso aditivo.

## 4. Once reglas predictivas actuales

Se migraron sin cambiar su efecto numerico:

1. estructura de trayectoria;
2. extremo previo entre entrada y TP;
3. percentil de volatilidad;
4. jerarquia multi-timeframe;
5. regimen continuo;
6. desequilibrio agresor;
7. cambio de open interest;
8. estado precio-OI;
9. basis Spot-Futures;
10. prima mark-index;
11. funding.

Las tres familias ajustadas historicamente conservan sus coeficientes. Los
ocho pesos manuales quedan declarados como:

```text
origin = project_hypothesis
status = unvalidated_provisional
```

Ninguna fuente publicada se atribuye esos pesos.

## 5. Veintidos fichas sin efecto probabilistico directo

Se registraron sin efecto probabilistico. Dieciseis son observaciones, dos
son gates activos de calidad, dos son reglas economicas activas y dos
permanecen bloqueadas:

- tendencia EMA y pendiente normalizada;
- RSI de Wilder;
- extension EMA/ATR;
- volumen relativo estacional;
- imbalance visible del libro;
- trayectoria CVD de ventana exacta;
- breadth;
- distancia y confluencia Fibonacci;
- distancia a niveles estructurales;
- percentil y robust z de funding;
- crowding;
- sentimiento;
- compresion;
- shock;
- absorcion flujo-volumen-precio;
- contexto de pullback;
- zonas observadas de liquidacion;
- frescura de datos;
- integridad de velas;
- divergencia sincronizada entre venues;
- spread cotizado;
- barrido visible de profundidad.

`shock` queda bloqueada hasta disponer de una serie fiable de liquidaciones
realizadas. `liquidation-zone` conserva evidencia historica limitada:
107 analisis, 104 observaciones disponibles y 24 operaciones cerradas
resueltas. La divergencia entre venues queda bloqueada hasta aprobar y
sincronizar fuentes.

## 6. Formulas corregidas

El catalogo conserva las expresiones en direccion canonica:

```text
spread_fraction = (ask-bid)/mid
fill_ratio = filled_qty/requested_qty
VWAP_filled = sum(price_i*filled_qty_i)/filled_qty
IS_filled_quote = D*(sum(price_i*filled_qty_i)-arrival_mid*filled_qty)
IS_filled_fraction = IS_filled_quote/(arrival_mid*filled_qty)
complete_VWAP = VWAP_filled iff fill_ratio=1
ATRNorm = ATR14/price
efficiency = abs(net_displacement)/total_path_variation
extension = (close-EMA20)/ATR14
relative_volume_H = volume_H/median(previous_60_non_overlapping_volume_H)
taker_imbalance = (buy_taker-sell_taker)/(buy_taker+sell_taker)
delta_i = buy_taker_volume_i-sell_taker_volume_i
CVD_t = cumsum(delta_i)
cvd_slope = TheilSenSlope(CVD_t)
obi_D = (bid_notional_D-ask_notional_D)/(bid_notional_D+ask_notional_D)
pivot_high_i = unique_max(high[i-3:i+4])
pivot_low_i = unique_min(low[i-3:i+4])
level_distance_sigma = log(level_price/entry)/sigma_h
retracement_r = start+direction*(1-r)*abs(end-start)
extension_r = start+direction*r*abs(end-start)
confluence_sigma = abs(log(pivot_price/fib_level))/sigma_h
funding_midrank_60 = (count(r_i<current)+0.5*count(r_i=current))/60
funding_robust_z_60 = (current-median(r_i))/(1.4826*MAD(r_i))
log_crowding_ratio = log(long_account_count/short_account_count)
crowding_midrank_60 = (count(x_i<current)+0.5*count(x_i=current))/60
breadth_w = count(return_i_w>0)/count(valid_return_i_w)
median_return_w = median(valid_return_i_w)
sentiment_midrank_60 = (count(v_i<current)+0.5*count(v_i=current))/60
sentiment_robust_z_60 = (current-median(v_i))/(1.4826*MAD(v_i))
liquidation_distance_sigma = log(cluster_price/entry)/sigma_h
liquidation_path_mass_b = sum(notional_j between entry and barrier_b)
liquidation_target_fraction = target_mass/(target_mass+adverse_mass)
bb_width_20_2sigma = 4*population_std(close_20)/SMA20
compression_vector = (atr_rank_60,bb_width_midrank_60,relative_volume,volume_midrank_60)
absorption_vector = (ATI_H,relative_volume,log(C_H/O_H)/(ATR14/C_H),flow_opposing_wick)
pullback_vector = (EMA_state,EMA_slope,extension,volume,ATI,structural_levels)
age_ms = analysis_at-latest_closed_candle_timestamp
freshness_limit_ms = selected_interval_ms+60000
fresh = 0<=age_ms<=freshness_limit_ms
gap_count = count(delta_close_time!=selected_interval_ms)
```

No se incorporaron los puntos `+6`, `-10`, los scores `70/20` ni los
horizontes 3-60 h. Las 38 fichas declaran los tres horizontes vigentes.

## 7. Atribucion por regla

Para cada una de las 11 reglas activas se conserva ahora:

- senal y formula aplicada;
- coeficiente o peso y su procedencia;
- log-efecto TP, SL y expiracion cuando existe;
- probabilidades completas;
- probabilidades recalculadas retirando la regla;
- delta de ablacion para TP, SL y expiracion;
- familia, padres, fuentes, formula y hash de traza.

El delta de ablacion sustituye como medida analitica al delta secuencial
dependiente del orden. El delta secuencial se conserva solo por compatibilidad
y explicacion del recorrido ejecutado.

## 8. Atribucion por familia

Cada analisis recalcula tambien el resultado retirando familias completas:

- trayectoria y MTF;
- niveles estructurales;
- volatilidad;
- interaccion trayectoria-volatilidad;
- flujo ejecutado;
- OI y precio-OI;
- dislocacion perpetua: basis, premium y funding.

Esto permite detectar doble conteo y medir valor incremental familiar.

## 9. Aprendizaje

El registro estructurado de cierre enlaza:

- operadores base;
- reglas activas;
- valores brutos y estandarizados;
- formulas, fuentes y hashes;
- ablacion individual;
- ablacion familiar;
- outcome TP, SL o expiracion/censura.

El aprendizaje no puede modificar produccion automaticamente.

Versiones:

```text
app-v0.23.10-execution-economics
learning-v0.13-execution-economics
learning-schema-v0.16-execution-economics
data-sources-v0.22-execution-economics
data-contract-v0.18-execution-economics
tp-sl-rule-library-runtime-v0.14
```

## 10. Limites

- Dieciseis reglas candidatas estan implementadas en observacion sin efecto
  probabilistico: EMA/tendencia, RSI Wilder, extension EMA/ATR, volumen
  relativo, CVD de ventana exacta, imbalance visible del libro, niveles
  estructurales confirmados, Fibonacci reproducible, funding relativo y
  crowding relativo, breadth transversal, sentimiento relativo y
  liquidaciones observadas de Hyperliquid, compresion, absorcion y contexto
  de pullback.
- Dos gates deterministas estan activos: frescura de la ultima vela cerrada e
  integridad de la rejilla temporal. Se ejecutan juntos una vez antes de las
  reglas y no alteran TP, SL ni expiracion.
- Dos reglas economicas estan activas: spread cotizado y barrido de
  profundidad. No alteran las probabilidades de mercado; miden la viabilidad
  y el coste visible de entrada.
- Las fichas candidatas duplicadas de spread y cobertura se sustituyeron por
  las reglas canonicas que realmente ejecuta el motor.
- Las otras dos reglas permanecen bloqueadas por datos.
- La regla de shock continua bloqueada: el mapa de exposicion potencial no
  sustituye una serie de liquidaciones realizadas ni la historia del spread.
- Se preservaron 718 observaciones antiguas de breadth y 874 de sentimiento;
  no son directamente comparables con las formulas nuevas.
- Los 154 cierres historicos con Fibonacci antiguo quedan preservados, pero
  deberan recalcularse; no se reutilizan sus scores ni ajustes manuales.
- No se han modificado los pesos ni probabilidades de las 11 actuales.
- No se ha resuelto todavia la doble utilizacion de evidencia; ahora queda
  identificada y medible mediante ablacion familiar.
- No se ha validado financieramente ninguna candidata.
- No se han mezclado reglas de ejecucion o riesgo con probabilidad de mercado.
- No se ha reanudado el aprendizaje automatico.

## 11. Verificacion

```text
677 pruebas ejecutadas
677 correctas
0 fallos
```

La suite cubre catalogo, contratos, reglas, motor probabilistico, ablacion
individual, ablacion familiar, cierre de aprendizaje y compatibilidad de la
aplicacion.

## 12. Siguiente trabajo

Las dos fichas no implementadas requieren datos que todavia no estan
disponibles:

1. shock: historia de spread y liquidaciones realizadas;
2. divergencia entre venues: precios sincronizados de fuentes aprobadas.

No deben implementarse mediante sustitutos. El resto de la biblioteca ya
dispone de formula, captura, traza, invariantes o estado de observacion
explicito.
