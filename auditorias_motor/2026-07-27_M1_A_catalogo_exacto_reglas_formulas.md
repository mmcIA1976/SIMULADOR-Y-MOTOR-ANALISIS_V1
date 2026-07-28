# M1-A - Catalogo exacto de reglas y formulas actuales

Fecha: 2026-07-27
Estado: COMPLETADO Y APROBADO EL 2026-07-27

## 1. Alcance y garantia

Este anexo expande las 86 entradas decididas en M1. No identifica solo
su nombre: conserva la definicion ejecutable actual, todas las constantes
y ramas relevantes, su orden o caps cuando aplican, y la enlaza con la
funcion concreta y su SHA-256.

La palabra `exacta` significa exacta respecto al codigo actual. No
significa que la regla sea valida, fiable o autorizada como predictor.
Los contratos de datos se documentan como contratos; no se les inventa
una formula predictiva.

- Entradas: **86 / 86**.
- Motor productivo actual: **82**.
- Infraestructura contractual aislada: **4**.
- Definiciones actuales completas: **86 / 86**.
- Referencias de funcion resueltas: **67**.
- Efectos predictivos autorizados por M1-A: **0**.
- SHA-256 del catalogo: `5fd8c70cae45f2967e0a8f8de9f0d68a973f3cb7ba9576eca6d65eefe944a895`.

M1 permanece cerrada y aprobada. M2 no se ha iniciado y el motor
productivo no ha sido modificado.

## 2. Tipos de definicion

| Tipo | Cantidad |
|---|---:|
| `exact_data_contract` | 7 |
| `exact_executable_aggregate` | 1 |
| `exact_executable_algorithm` | 2 |
| `exact_executable_branch` | 1 |
| `exact_executable_composite` | 1 |
| `exact_executable_constant` | 1 |
| `exact_executable_cost_rule` | 3 |
| `exact_executable_fallback` | 2 |
| `exact_executable_formula` | 5 |
| `exact_executable_gate` | 19 |
| `exact_executable_identity` | 5 |
| `exact_executable_output` | 7 |
| `exact_executable_policy` | 3 |
| `exact_executable_presentation` | 1 |
| `exact_executable_rule` | 1 |
| `exact_executable_score_rule` | 27 |

## 3. Listado exacto 86/86

### 01. DATA-PRICE-KLINES - Precio y velas Binance USD-M

- Origen: `current_production_engine`.
- Capa/tipo actual: `market_data` / `data_definition`.
- Tipo de definicion exacta: `exact_data_contract`.
- Resumen anterior: Campos oficiales de ticker y klines.

Definicion exacta actual:

```text
price = float(provider_ticker_price)
For each Binance kline k: close=float(k[4]); high=float(k[2]); low=float(k[3]); volume=float(k[5]); taker_buy_volume=float(k[9]).
Snapshot intervals = {5m, 15m, 1h, 4h, 1d, 1w}; each request asks for 240 candles.
This entry transports raw market fields. It has no direct TP/SL formula and no direct probability effect.
```

Anclajes ejecutables:

- `market_data.py:234-244` (`get_price`), SHA-256 `9327a7cd216dfa2a39d6d78e2a1af61951fdc2dc9ddb9d406472e787861cddd2`.
- `market_data.py:247-261` (`get_klines`), SHA-256 `b90c3b953f9ff3daf12f791851e668f0b91e5735e8898e2fee5a7881910ef8ec`.
- `data_engine.py:74-82` (`parse_klines`), SHA-256 `b82a083a611827dfb2aba1882a6296e2a3d30891dad6f70ee27d860c527315d1`.
- `data_engine.py:525-610` (`build_market_snapshot`), SHA-256 `6c737d24a9d5c9fff928121f8d93a20af403f37154442f499a2ee9dd48948a2b`.

Respaldo declarado: Define precio, OHLCV e intervalos.

Limite de transferencia: No acredita ninguna senal, ventana o probabilidad TP/SL.

Decision M1: `conservar_como_dato_sin_efecto_predictivo_directo`. Accion inicial `M3`; posible reemplazo `M3`.

### 02. DATA-DEPTH-TRADES - Depth y aggTrades Binance USD-M

- Origen: `current_production_engine`.
- Capa/tipo actual: `market_data` / `data_definition`.
- Tipo de definicion exacta: `exact_data_contract`.
- Resumen anterior: Campos oficiales de depth y operaciones agregadas.

Definicion exacta actual:

```text
Depth rows are converted to (price=float(row[0]), quantity=float(row[1])) for bids and asks.
Each aggTrade transports p=price, q=quantity and m=is_buyer_maker; the derived order-book and CVD formulas are catalogued separately.
The current request limits are 20 depth levels per side and 500 aggregated trades.
This entry has no direct TP/SL formula and no direct probability effect.
```

Anclajes ejecutables:

- `market_data.py:264-267` (`get_depth`), SHA-256 `49ea6b0c5316654547a44c24f7f530a8035146b891520ee1764e3469a1f96078`.
- `market_data.py:276-290` (`get_agg_trades`), SHA-256 `f14e662fccfa13e3c6657321155f180b23c61c898aa78dfa0faa454982ec7151`.

Respaldo declarado: Define bids, asks, cantidades, precios y trades.

Limite de transferencia: No valida imbalance top-20, CVD de 500 trades ni sus pesos.

Decision M1: `conservar_como_dato_sin_efecto_predictivo_directo`. Accion inicial `M3`; posible reemplazo `M3`.

### 03. DATA-DERIVATIVES - Funding, OI y ratios Binance USD-M

- Origen: `current_production_engine`.
- Capa/tipo actual: `market_data` / `data_definition`.
- Tipo de definicion exacta: `exact_data_contract`.
- Resumen anterior: Campos oficiales de funding, open interest y ratios.

Definicion exacta actual:

```text
funding_rate_pct = float(lastFundingRate) * 100.
funding_avg_recent_pct = mean(float(fundingRate_i) * 100) over the last 8 returned funding records; None when no record exists.
open_interest_change_pct = ((last_sumOpenInterest - first_sumOpenInterest) / first_sumOpenInterest) * 100, when at least 2 records exist.
OI windows: 30 x 5m, 24 x 1h and 30 x 1d. The selected window is 5m for intraday_short, 1h for intraday_wide and 1d for short_swing.
Ratios and account percentages are direct float conversions of longShortRatio, longAccount*100, shortAccount*100, buySellRatio, buyVol and sellVol.
This entry has no direct TP/SL formula; derived score rules are catalogued separately.
```

Anclajes ejecutables:

- `data_engine.py:393-454` (`summarize_derivatives`), SHA-256 `5f93f3ccf071152a0ca792e574e530f71170cc3c7093aa82257eda6f1c1fe79e`.
- `analysis_engine.py:112-123` (`derivatives_for_horizon`), SHA-256 `108c3ed9b9e7eb711e7011d2e1b6e175d474746003f0c98bc057fa05ea984b4e`.
- `data_engine.py:382-390` (`open_interest_change`), SHA-256 `f959f6d8b3c120ee0338d326f7b801dfc68cb0dba7481cb24cc2f020ae0e6fbb`.

Respaldo declarado: Define los campos de derivados y sus periodos publicados.

Limite de transferencia: No valida ventanas internas, thresholds, signo predictivo ni pesos.

Decision M1: `conservar_como_dato_sin_efecto_predictivo_directo`. Accion inicial `M3`; posible reemplazo `M3`.

### 04. DATA-BREADTH - Mercados CoinGecko para breadth

- Origen: `current_production_engine`.
- Capa/tipo actual: `market_data` / `data_definition`.
- Tipo de definicion exacta: `exact_data_contract`.
- Resumen anterior: Variaciones publicadas para el universo consultado.

Definicion exacta actual:

```text
Universe = first 100 assets returned by the CoinGecko markets query.
advancers_H_pct = 100 * count(change_H > 0) / count(non-null change_H), for H in {1h, 24h, 7d}.
median_change_H_pct = median(non-null change_H), for H in {1h, 24h, 7d}.
strong_moves_24h_pct = 100 * count(abs(change_24h) >= 5) / count(non-null change_24h).
This entry defines data only and has no direct TP/SL formula or probability effect. The 58/42 directional rule is a separate score entry.
```

Anclajes ejecutables:

- `data_engine.py:471-485` (`summarize_market_breadth`), SHA-256 `7cde5737f701e9505c14804b0d7a7585c12547d5e61456b9eab10506e7807dca`.

Respaldo declarado: Define variaciones y datos de los activos devueltos.

Limite de transferencia: No valida top-100, cortes 58/42 ni efecto sobre un par.

Decision M1: `conservar_como_dato_sin_efecto_predictivo_directo`. Accion inicial `M10`; posible reemplazo `M10`.

### 05. DATA-GLOBAL - Mercado global CoinGecko

- Origen: `current_production_engine`.
- Capa/tipo actual: `market_data` / `data_definition`.
- Tipo de definicion exacta: `exact_data_contract`.
- Resumen anterior: Capitalizacion, volumen y dominancia global.

Definicion exacta actual:

```text
Direct fields: total_market_cap.usd, total_volume.usd, market_cap_percentage.btc, market_cap_percentage.eth, active_cryptocurrencies and markets.
Missing or malformed nested objects produce None for their fields.
This data is displayed/stored but has no direct TP/SL formula in the current engine.
```

Anclajes ejecutables:

- `data_engine.py:457-468` (`summarize_global_market`), SHA-256 `59c4faaf46c76c817e3f2c41a540726f6956148791f33c981cb20585aafa8ccf`.

Respaldo declarado: Define agregados del mercado crypto.

Limite de transferencia: No valida interpretacion direccional.

Decision M1: `conservar_como_dato_sin_efecto_predictivo_directo`. Accion inicial `M3`; posible reemplazo `M3`.

### 06. DATA-SENTIMENT - Fear and Greed de Alternative.me

- Origen: `current_production_engine`.
- Capa/tipo actual: `market_data` / `data_definition`.
- Tipo de definicion exacta: `exact_data_contract`.
- Resumen anterior: Escala y metodologia del indicador externo.

Definicion exacta actual:

```text
fear_greed_value = int(provider.value) only when the value is made entirely of digits; otherwise None.
value_classification, timestamp and time_until_update are transported without a predictive transformation.
This entry has no direct TP/SL formula or probability effect. The 75/25 score rule is catalogued separately.
```

Anclajes ejecutables:

- `data_engine.py:488-496` (`summarize_sentiment`), SHA-256 `f96ddc5ca8ba5f1dee4f15ca1d2732ffc6785bfc7d3e5581ca50d3c8f669f53c`.

Respaldo declarado: Define escala, componentes y API.

Limite de transferencia: El proveedor no valida decisiones de trading ni cortes 75/25.

Decision M1: `conservar_como_dato_sin_efecto_predictivo_directo`. Accion inicial `M10`; posible reemplazo `M10`.

### 07. DATA-LIQUIDATIONS - Mapa Hyperliquid observado

- Origen: `current_production_engine`.
- Capa/tipo actual: `market_data` / `data_definition`.
- Tipo de definicion exacta: `exact_data_contract`.
- Resumen anterior: Posiciones publicas normalizadas como clusters observacionales.

Definicion exacta actual:

```text
age_seconds = max(0, (now_ms-updated_at)/1000) when updated_at exists; otherwise provider meta.age_seconds.
stale = provider_meta.stale OR age_seconds is None OR age_seconds > max_age_seconds; default max_age_seconds=600, environment-clamped to [60,3600].
reference_basis_pct = 100*(reference_price-market_price)/market_price; price_mismatch when missing or abs(reference_basis_pct) exceeds default 1.5%, environment-clamped to [0.25,10].
ratio_2pct = short_mass_within_2pct / long_mass_within_2pct when defined. Dominant side: shorts_above if ratio>=1.2; longs_below if ratio<=1/1.2; otherwise balanced.
Clusters are sorted by notional_usd descending and the first 10 above (shorts) and below (longs) are retained.
mode='observation' and this entry has no direct score or probability effect.
```

Anclajes ejecutables:

- `liquidation_data.py:114-217` (`normalize_heatmap`), SHA-256 `a68f01fc2bcbb77f165fbdef70b35e9c1cc933bb0104511ee03f341638bf0bba`.
- `analysis_engine.py:1517-1632` (`build_liquidation_observation`), SHA-256 `84e1a84a842fc63c34af19e0214898c5a5ed3d2a0b336650bd7d3db439f34b5e`.

Respaldo declarado: Permite conservar una observacion versionada del proveedor gratuito.

Limite de transferencia: No es mapa agregado multi-exchange ni tiene poder predictivo validado.

Decision M1: `conservar_como_dato_sin_efecto_predictivo_directo`. Accion inicial `M10`; posible reemplazo `M10`.

### 08. PLAN-TP-LOG-DISTANCE - Distancia logaritmica de entrada a TP

- Origen: `contract_infrastructure_only`.
- Capa/tipo actual: `feature_transform` / `deterministic_plan_calculation`.
- Tipo de definicion exacta: `exact_executable_identity`.
- Resumen anterior: long: ln(TP/entry); short: ln(entry/TP)

Definicion exacta actual:

```text
long: tp_log_distance = ln(take_profit / entry).
short: tp_log_distance = ln(entry / take_profit).
```

Anclajes ejecutables:

- `challenger_engine.py:122-153` (`derive_plan_features`), SHA-256 `f586e50f202d8b84ac9fb79b8f4bb6fca78aa4d4664a05342d54a524836b7e7d`.

Respaldo declarado: Es una transformacion matematica dimensionless del plan.

Limite de transferencia: La identidad no acredita signo, magnitud ni linealidad predictiva.

Decision M1: `conservar_calculo_contractual_aislado`. Accion inicial `M2`; posible reemplazo `M2`.

### 09. PLAN-SL-LOG-DISTANCE - Distancia logaritmica de entrada a SL

- Origen: `contract_infrastructure_only`.
- Capa/tipo actual: `feature_transform` / `deterministic_plan_calculation`.
- Tipo de definicion exacta: `exact_executable_identity`.
- Resumen anterior: long: ln(entry/SL); short: ln(SL/entry)

Definicion exacta actual:

```text
long: sl_log_distance = ln(entry / stop_loss).
short: sl_log_distance = ln(stop_loss / entry).
```

Anclajes ejecutables:

- `challenger_engine.py:122-153` (`derive_plan_features`), SHA-256 `f586e50f202d8b84ac9fb79b8f4bb6fca78aa4d4664a05342d54a524836b7e7d`.

Respaldo declarado: Es una transformacion matematica dimensionless del plan.

Limite de transferencia: La identidad no acredita signo, magnitud ni linealidad predictiva.

Decision M1: `conservar_calculo_contractual_aislado`. Accion inicial `M2`; posible reemplazo `M2`.

### 10. PLAN-LOG-HORIZON-SECONDS - Duracion logaritmica del horizonte

- Origen: `contract_infrastructure_only`.
- Capa/tipo actual: `feature_transform` / `deterministic_plan_calculation`.
- Tipo de definicion exacta: `exact_executable_identity`.
- Resumen anterior: ln(horizon_seconds)

Definicion exacta actual:

```text
log_horizon_seconds = ln(horizon_seconds).
The value is calculated only after horizon_seconds is finite and inside the limits declared for the selected time horizon.
```

Anclajes ejecutables:

- `challenger_engine.py:122-153` (`derive_plan_features`), SHA-256 `f586e50f202d8b84ac9fb79b8f4bb6fca78aa4d4664a05342d54a524836b7e7d`.

Respaldo declarado: Es una transformacion matematica de la duracion declarada.

Limite de transferencia: No acredita como cambia la alcanzabilidad con el tiempo.

Decision M1: `conservar_calculo_contractual_aislado`. Accion inicial `M2`; posible reemplazo `M2`.

### 11. PLAN-SIDE-SIGN - Codificacion simetrica del lado

- Origen: `contract_infrastructure_only`.
- Capa/tipo actual: `feature_transform` / `deterministic_plan_calculation`.
- Tipo de definicion exacta: `exact_executable_identity`.
- Resumen anterior: long=+1; short=-1

Definicion exacta actual:

```text
side_sign = +1.0 for long; -1.0 for short.
```

Anclajes ejecutables:

- `challenger_engine.py:122-153` (`derive_plan_features`), SHA-256 `f586e50f202d8b84ac9fb79b8f4bb6fca78aa4d4664a05342d54a524836b7e7d`.

Respaldo declarado: Es una codificacion reproducible del plan del usuario.

Limite de transferencia: La codificacion no acredita diferencias predictivas entre lados.

Decision M1: `conservar_calculo_contractual_aislado`. Accion inicial `M2`; posible reemplazo `M2`.

### 12. IND-EMA-CORE - EMA estandar con historia suficiente

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `standard_calculation`.
- Tipo de definicion exacta: `exact_executable_formula`.
- Resumen anterior: EMA_t = alpha*x_t + (1-alpha)*EMA_(t-1), alpha=2/(period+1)

Definicion exacta actual:

```text
alpha = 2 / (period + 1).
EMA_0 = first value in the supplied window.
EMA_t = (value_t - EMA_(t-1))*alpha + EMA_(t-1).
An empty input returns 0.0.
```

Anclajes ejecutables:

- `data_engine.py:30-37` (`ema`), SHA-256 `f0670cc769ad332a26cd744eb44f4d9d864efadf6b21abb914deee29258de3ec`.

Respaldo declarado: La media exponencial es una transformacion tecnica reconocida.

Limite de transferencia: No acredita que stacks EMA predigan TP/SL ni sus pesos.

Decision M1: `conservar_calculo_sin_peso_predictivo`. Accion inicial `M4`; posible reemplazo `M4`.

### 13. IND-EMA200-FALLBACK - Fallback EMA200 con hasta 80 cierres

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `implementation_variant`.
- Tipo de definicion exacta: `exact_executable_branch`.
- Resumen anterior: if len(closes)<200: ema(closes, min(80,len(closes))) etiquetada ema_200

Definicion exacta actual:

```text
If len(closes)>=200: ema_200 = EMA(closes[-220:], 200).
Else: ema_200 = EMA(closes, min(80, len(closes))).
Despite the fallback period being at most 80, the returned field is still named ema_200.
```

Anclajes ejecutables:

- `data_engine.py:104-165` (`summarize_timeframe`), SHA-256 `d1dba5310f27d2b162dbecbfe496d4c572fbebe8e2978c20c1e809c1373ba136`.

Respaldo declarado: La EMA tiene definicion reconocida.

Limite de transferencia: La fuente no permite llamar EMA200 a una EMA de hasta 80 datos.

Decision M1: `desactivar_fallback_mal_etiquetado`. Accion inicial `M4`; posible reemplazo `M4`.

### 14. IND-RSI14-CURRENT - RSI14 variante de media simple

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `implementation_variant`.
- Tipo de definicion exacta: `exact_executable_formula`.
- Resumen anterior: RSI sobre media simple de los ultimos 14 cambios

Definicion exacta actual:

```text
If len(values)<=14: RSI=50.0.
For the last 14 changes delta_i=value_i-value_(i-1): gain_i=max(delta_i,0); loss_i=max(-delta_i,0).
avg_gain = arithmetic_mean(gain_i); avg_loss = arithmetic_mean(loss_i).
If avg_loss==0: RSI=100.0; else RS=avg_gain/avg_loss and RSI=100-100/(1+RS).
This is an SMA-window variant, not Wilder recursive smoothing.
```

Anclajes ejecutables:

- `data_engine.py:40-58` (`rsi`), SHA-256 `61657a3b589f10a19af4e611ddc1c3c7124aaeaade15f36439c342e5b8e24877`.

Respaldo declarado: Wilder define RSI y su suavizado original.

Limite de transferencia: La implementacion actual no replica todo el suavizado de Wilder.

Decision M1: `reformular_a_definicion_estandar_o_renombrar`. Accion inicial `M10`; posible reemplazo `M10`.

### 15. IND-ATR14-CURRENT - ATR14 variante de media simple

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `implementation_variant`.
- Tipo de definicion exacta: `exact_executable_formula`.
- Resumen anterior: Media simple de true ranges recientes

Definicion exacta actual:

```text
For i=max(1,len(closes)-14)..len(closes)-1: TR_i=max(high_i-low_i, abs(high_i-close_(i-1)), abs(low_i-close_(i-1))).
ATR14 = arithmetic_mean(TR_i).
If len(closes)<=1: ATR14=0.0.
This is a simple mean over recent TR values, not Wilder recursive smoothing.
```

Anclajes ejecutables:

- `data_engine.py:61-71` (`atr`), SHA-256 `c451e3e3385bbea5d757d88fc7436f6f19a264a3e56d5a56fda475727054d7e2`.

Respaldo declarado: Wilder define true range y ATR.

Limite de transferencia: La implementacion no replica todo el suavizado original.

Decision M1: `reformular_a_definicion_estandar_o_renombrar`. Accion inicial `M4`; posible reemplazo `M4`.

### 16. IND-EMA-STACK - Stack EMA multi-temporalidad

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `research_hypothesis`.
- Tipo de definicion exacta: `exact_executable_rule`.
- Resumen anterior: bullish/bearish/mixed por orden EMA9, EMA21 y EMA50

Definicion exacta actual:

```text
bullish iff EMA9 > EMA21 > EMA50.
bearish iff EMA9 < EMA21 < EMA50.
mixed otherwise.
```

Anclajes ejecutables:

- `data_engine.py:326-331` (`classify_ema_stack`), SHA-256 `e72aee43d521cd4d233cd5fa185cc91b6405929663a61b4014a15974bf026edb`.
- `analysis_engine.py:2154-2176` (`trend_score`), SHA-256 `cfd423a7df040a9793addc90e3d696b05b9bf4eb94aa592adf295aa60a9abcb6`.

Respaldo declarado: Las medias y algunas reglas simples merecen investigacion empirica.

Limite de transferencia: No valida este stack, activos crypto, horizontes ni pesos.

Decision M1: `mantener_solo_como_hipotesis_estructural`. Accion inicial `M4`; posible reemplazo `M4`.

### 17. IND-SUPPORT-RESISTANCE - Detector interno de soportes y resistencias

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `research_hypothesis`.
- Tipo de definicion exacta: `exact_executable_algorithm`.
- Resumen anterior: Cluster de extremos recientes y distancia porcentual al nivel

Definicion exacta actual:

```text
Use the last 120 candle highs and lows.
resistance_candidates = highs strictly above current_price, sorted by abs(price-current_price).
support_candidates = lows strictly below current_price, sorted by abs(price-current_price).
For each side take the nearest 12 candidates, then return the arithmetic mean of the first min(5,n); None when n=0.
distance_to_support_pct = abs(100*(current_price-support)/support); distance_to_resistance_pct = abs(100*(resistance-current_price)/current_price).
```

Anclajes ejecutables:

- `data_engine.py:168-188` (`detect_levels`), SHA-256 `76bbc0bd33e9c5a39898e79becbdc331051280e20271603a9cb807b9e8cdf955`.
- `data_engine.py:320-323` (`cluster_level`), SHA-256 `507255aaffb12bbf25fa17181e514c32db8468474afdb7b2379966053776597b`.

Respaldo declarado: Existe evidencia parcial de interrupciones cerca de ciertos niveles en FX.

Limite de transferencia: No valida el detector interno, BTC ni sus umbrales.

Decision M1: `reformular_detector_antes_de_uso`. Accion inicial `M4`; posible reemplazo `M4`.

### 18. IND-FIBONACCI - Swing y niveles Fibonacci automaticos

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `research_hypothesis`.
- Tipo de definicion exacta: `exact_executable_algorithm`.
- Resumen anterior: Swings internos + retracements 0.236/0.382/0.5/0.618/0.786 y extensiones

Definicion exacta actual:

```text
Use last 180 candles; unavailable when fewer than 34 closes or current_price<=0.
min_move_pct = max(ATR14_pct*1.35, full_window_range_pct*0.18, 0.35).
A pivot high/low is a unique maximum/minimum in a window of 3 candles on each side. Search pivots backwards and select the most recent end with the most recent prior opposite pivot whose move_pct is at least min_move_pct.
Ratios: retracements={0.236,0.382,0.5,0.618,0.786}; extensions={1.272,1.618,2.0,2.618}.
Up swing: retracement=end-move*r; extension=end+move*(r-1). Down swing: retracement=end+move*r; extension=end-move*(r-1).
Zone uses retracement=(end-price)/move for up and (price-end)/move for down: extension if <-0.03; very superficial if <0.236; superficial if <0.382; golden_zone if <=0.618; deep if <=0.786; extreme if <=1.0; structure_broken otherwise.
```

Anclajes ejecutables:

- `data_engine.py:191-235` (`summarize_fibonacci`), SHA-256 `119e5954bc4882d05d553b1577274c3d921c790eef16a323f30755424654d6d2`.
- `analysis_engine.py:619-726` (`build_fibonacci_trade_context`), SHA-256 `a2f46c47acca6f82046e6ec968ab28585b88c7ba798f8849c9b68ece555095b6`.
- `data_engine.py:252-265` (`detect_price_pivots`), SHA-256 `5309db5b9faebd63c27905a92fe8ce0e1b49510a11a79d64a9720bdb961b3925`.
- `data_engine.py:268-282` (`select_recent_fibonacci_swing`), SHA-256 `479aea6952dd999e12d9f3d0b5d82ba4615ee9b925010675e50acec69db53492`.
- `data_engine.py:296-313` (`classify_fibonacci_price_zone`), SHA-256 `52b363870b8c0a0d1bdaa5cdbf8cbef03f7c7edb25151575c1b0386d6e34cefa`.

Respaldo declarado: La fuente evalua identificacion automatica de retrocesos.

Limite de transferencia: No encontro ventaja estadistica y no valida nuestros swings ni pesos.

Decision M1: `retirar_efecto_predictivo_conservar_solo_investigacion`. Accion inicial `M10`; posible reemplazo `M10`.

### 19. IND-ORDERBOOK-PROXY - Imbalance estatico top-20

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `proxy_hypothesis`.
- Tipo de definicion exacta: `exact_executable_formula`.
- Resumen anterior: (bid_notional_top20-ask_notional_top20)/(bid+ask)

Definicion exacta actual:

```text
bid_notional = sum(price_i*quantity_i) over returned bids.
ask_notional = sum(price_i*quantity_i) over returned asks.
imbalance = (bid_notional-ask_notional)/(bid_notional+ask_notional); 0.0 when denominator is 0.
best_bid=bids[0].price; best_ask=asks[0].price; mid=(best_bid+best_ask)/2.
spread_pct = 100*(best_ask-best_bid)/mid; 0.0 when mid is 0.
```

Anclajes ejecutables:

- `data_engine.py:334-352` (`summarize_order_book`), SHA-256 `78aaa4425e2a9c65216453e66f6b3a1a8439cda67cdc9435efb2e8a0eb6f09b4`.

Respaldo declarado: OFI dinamico en mejor bid/ask mostro relacion de corto plazo con precio.

Limite de transferencia: Top-20 estatico no es el OFI del estudio ni hereda coeficientes.

Decision M1: `reformular_proxy_sin_peso_actual`. Accion inicial `M10`; posible reemplazo `M10`.

### 20. IND-CVD-PROXY - CVD proxy de 500 aggTrades

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `proxy_hypothesis`.
- Tipo de definicion exacta: `exact_executable_formula`.
- Resumen anterior: (buy_notional-sell_notional)/(buy+sell) sobre muestra reciente

Definicion exacta actual:

```text
notional_i = float(p_i)*float(q_i).
If m_i is true (buyer is maker): sell_notional += notional_i and cvd -= notional_i; otherwise buy_notional += notional_i and cvd += notional_i.
total=buy_notional+sell_notional; cvd_ratio=cvd/total, buy_ratio=buy_notional/total and sell_ratio=sell_notional/total; ratios are None when total=0.
```

Anclajes ejecutables:

- `data_engine.py:355-379` (`summarize_trade_flow`), SHA-256 `9b2f6f78c556aa7c21f42a4c9d932d3a34640de70eb0ede0ef9f94a8988b604d`.

Respaldo declarado: Binance define trades; la literatura permite investigar order flow.

Limite de transferencia: No valida esta ventana, clasificacion ni peso.

Decision M1: `reformular_proxy_sin_peso_actual`. Accion inicial `M4`; posible reemplazo `M4`.

### 21. IND-PENDING-ZONE - Zona de entrada pendiente

- Origen: `current_production_engine`.
- Capa/tipo actual: `feature_transform` / `internal_composite_hypothesis`.
- Tipo de definicion exacta: `exact_executable_composite`.
- Resumen anterior: Confluencia, activacion, sweep, rechazo/ruptura y calidad de camino

Definicion exacta actual:

```text
Only pending entries are evaluated; market entries return unavailable with neutral score 50 and no activation/reaction values.
distance_activation_pct=100*abs(current-entry)/abs(entry); ATR_units=distance/max(ATR_pct,1e-6); range_units=distance/max(recent_range_pct,1e-6).
tolerance=max(0.18,min(0.75,ATR_pct*0.8)). Confluence starts at 50: Fib favorable +14; Fib adverse/alert -10; desired S/R within tolerance +13, within max(1.8*tolerance,0.55) +6, otherwise -5; technical>=62 +8, <=42 -8; aligned trend regime +8; countertrend bounce -7.
Activation starts 0.50: distance<=0.75*ATR +0.18; else <=1.5*ATR +0.10; else >max(range,2.5*ATR) -0.16; trigger direction aligned/opposed to trend regime +/-0.06; volume_ratio>=1.25 +0.04; clamp [0.05,0.90].
stop_noise=max(ATR_pct,recent_range_pct*0.35). Sweep starts 45: risk_distance<noise +28; else <1.6*noise +12; else -8; adverse order-book imbalance beyond +/-0.12 on limit pullback +8; clamp [5,95]. Sweep risk is high >=68, medium >=42, low otherwise.
Limit pullback: rejection=clamp(0.34+(confluence-50)/130-(sweep-45)/220,[0.10,0.82]); breakout=clamp(0.28+(sweep-45)/180-(confluence-50)/170,[0.08,0.78]).
Breakout/breakdown: breakout=clamp(0.35+(technical-50)/140+(volume_ratio-1)*0.08-(sweep-45)/260,[0.10,0.84]); rejection=clamp(0.30+(sweep-45)/180-(technical-50)/180,[0.08,0.78]).
Pullback reaction is probable at rejection>=0.54, otherwise sweep zone when risk is high. Breakout reaction is probable at breakout>=0.54, otherwise false-breakout risk when sweep risk is high.
invalidation_quality=round(clamp(58+risk_distance*5-sweep*0.32+(8 if Fib favorable else -6 if Fib adverse/alert else 0),[0,100])).
Target path: 0 if reward<=0; 60 if no barrier; if barrier lies between entry and TP, round(clamp(35+map(barrier_distance,0..reward)*0.25,[15,55])); 70 if TP is within max(0.12,ATR*0.45) of barrier; else 62.
```

Anclajes ejecutables:

- `analysis_engine.py:1146-1346` (`build_zone_analysis`), SHA-256 `b51481acc40fd6bf9b2dfb1f4f79c7490a486cc2f898c1def3f5bdd3452ef0d8`.
- `analysis_engine.py:1436-1460` (`build_target_path_quality`), SHA-256 `3cc683971b34fa9bdafaadd1a4a73e75a55b2f6c52a3ba3f25dab6d7c397a69f`.
- `analysis_engine.py:1349-1425` (`build_zone_probability_context`), SHA-256 `676c0ed9e546e9d5a387fd308c73adebabbede0410210873dac9ed28f06f1921`.
- `analysis_engine.py:1428-1433` (`classify_entry_order_type`), SHA-256 `9977d1185e8b857a1c03002168be55fbd8e550c5c8fe884f8ca20be80047e384`.

Respaldo declarado: Niveles pueden investigarse; la zona concreta es diseno interno.

Limite de transferencia: No existe fuente para formulas, thresholds ni probabilidades de zona.

Decision M1: `conservar_solo_observacional_y_reformular_interaccion`. Accion inicial `M4`; posible reemplazo `M4`.

### 22. SCORE-TREND_BIAS - Tendencia EMA multi-TF

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: EMA stacks ponderados; cortes +/-0.2 y +/-0.55; efecto +0.10/+0.05/-0.05/-0.09

Definicion exacta actual:

```text
Map each EMA stack to bullish=+1, bearish=-1, mixed=0. raw=sum(stack_value_tf*trend_weight_tf); multiply raw by -1 for short.
normalized=raw/sum(available trend weights). Return +0.10 if normalized>=0.55; +0.05 if >=0.20; -0.09 if <=-0.55; -0.05 if <=-0.20; 0 otherwise.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:2154-2176` (`trend_score`), SHA-256 `cfd423a7df040a9793addc90e3d696b05b9bf4eb94aa592adf295aa60a9abcb6`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: family_evidence_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 23. SCORE-TECHNICAL_DIRECTION_BIAS - Rating tecnico direccional

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Score EMA+precio/EMA+RSI; cortes +/-0.15 y +/-0.45; efecto +0.035/+0.015/-0.02/-0.04

Definicion exacta actual:

```text
Per timeframe start s=0: EMA bullish +0.55, bearish -0.55; price_vs_EMA21>0.08 +0.25, <-0.08 -0.25; RSI 45..65 +0.20, >75 -0.25, <25 +0.10, 35..45(excluding 45) +0.05. Multiply s by -1 for short and clamp [-1,1].
normalized=sum(s_tf*trend_weight_tf)/sum(available weights). direction_bias=+0.035 if normalized>=0.45; +0.015 if >=0.15; -0.040 if <=-0.45; -0.020 if <=-0.15; 0 otherwise.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:2179-2250` (`build_technical_rating`), SHA-256 `59c378c92b0c094ed95987285641906e23c0cbda6f2df78a3694130cc7039071`.
- `analysis_engine.py:2253-2279` (`technical_timeframe_score`), SHA-256 `30dc6fd51966043ae3053a419ed82f5e7bbc6ffd2f11e3e699f9963f2011b982`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: definitions_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 24. SCORE-PRICE_VS_ENTRY_BIAS - Precio actual frente a entrada

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Long: +0.03 si price<=entry, si no -0.02; short simetrico

Definicion exacta actual:

```text
long: +0.03 when current_price<=entry, else -0.02.
short: +0.03 when current_price>=entry, else -0.02.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: none

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_formula_actual`. Accion inicial `M5`; posible reemplazo `M4`.

### 25. SCORE-VOLUME_BIAS - Ratio de volumen

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: +0.025 si volume_ratio>1.25; -0.015 si <0.65; ponderado por micro_weight

Definicion exacta actual:

```text
raw=+0.025 if volume_ratio>1.25; -0.015 if volume_ratio<0.65; 0 otherwise.
volume_bias = raw * max(0.5,micro_weight).
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_umbral_y_reformular`. Accion inicial `M5`; posible reemplazo `M10`.

### 26. SCORE-ORDER_BOOK_BIAS - Imbalance order book

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Umbral +/-0.12; efecto +/-0.016 por lado y micro_weight

Definicion exacta actual:

```text
long raw=+0.016 if imbalance>0.12; -0.016 if imbalance<-0.12; 0 otherwise.
short raw=+0.016 if imbalance<-0.12; -0.016 if imbalance>0.12; 0 otherwise.
order_book_bias=raw*micro_weight.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: different_proxy

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_umbral_y_reformular`. Accion inicial `M5`; posible reemplazo `M10`.

### 27. SCORE-MOMENTUM_BIAS - Momentum RSI

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Bandas RSI discretas por lado; efecto +0.02 o -0.025 por micro_weight

Definicion exacta actual:

```text
long raw=-0.025 if RSI>72; +0.020 if 45<=RSI<=62; 0 otherwise.
short raw=-0.025 if RSI<28; +0.020 if 38<=RSI<=55; 0 otherwise.
momentum_bias=raw*micro_weight.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: indicator_definition_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_umbrales_actuales`. Accion inicial `M5`; posible reemplazo `M10`.

### 28. SCORE-MARKET_REGIME_BIAS - Sesgo de regimen

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Efectos 0.024/-0.028/-0.018 con multiplicador por horizonte

Definicion exacta actual:

```text
Regime: compression if recent_range_pct<0.45 and ATR_pct<0.08; else uptrend if >=3 bullish stacks; else downtrend if >=3 bearish stacks; else countertrend bounce if 4h stack opposes side; else mixed.
weight=0.85 intraday_short, 1.0 intraday_wide, 1.15 short_swing. Aligned trend returns +0.024*weight; opposing trend returns -0.028*weight; countertrend bounce returns -0.018*htf_penalty_weight; compression/mixed return 0.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:1804-1827` (`classify_market_regime`), SHA-256 `058f22b30db652d9832b9b79f090e13630fa2a7bcf439e7d1c99e63a46eb907a`.
- `analysis_engine.py:1830-1846` (`market_regime_direction_bias`), SHA-256 `060f38ca5c62a6b3a447ef0065a4d641e848af0d99794d796057ff8e4bfca80a`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: concept_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 29. SCORE-FIBONACCI_PROBABILITY_ADJUSTMENT - Ajuste Fibonacci

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Ajuste actual 0 para favorable y negativo para contextos adversos

Definicion exacta actual:

```text
Fib score starts 50. Swing aligned +10 else -14; golden-zone entry +14; superficial +6; extension/very-superficial -8; extreme/broken -12; entry near a named retracement +4; TP near extension +5 else TP in extension -5; SL near retracement -4; S/R confluence +6.
Near tolerance=max(0.18,min(0.70,ATR_pct*0.65)); target tolerance is max(that,0.35). Clamp rounded score to [18,88].
score>=68: adjustment=0, risk_addition=0, execution=-4. score<=38: adjustment=-0.02 if swing not aligned else -0.01, risk=+0.04, execution=+8. score<=46: adjustment=-0.01, risk=+0.02, execution=+5. Otherwise all 0.
```

Anclajes ejecutables:

- `analysis_engine.py:619-726` (`build_fibonacci_trade_context`), SHA-256 `a2f46c47acca6f82046e6ec968ab28585b88c7ba798f8849c9b68ece555095b6`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: non_supportive_external_evidence

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_efecto_predictivo`. Accion inicial `M5`; posible reemplazo `M4`.

### 30. SCORE-ZONE_PROBABILITY_ADJUSTMENT - Ajuste de zona pendiente

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Ajustes discretos de zona hasta +0.025/-0.035

Definicion exacta actual:

```text
Start adjustment=0 and risk_addition=0. Limit pullback: probable rebound with confluence>=65 and non-high sweep adds +0.018; sweep zone or high sweep adds -0.025 TP and +0.035 risk.
Stop breakout/breakdown: probable breakout with confluence>=60 and target_path>=55 adds +0.014; false-breakout or high sweep adds -0.025 TP and +0.035 risk.
Exceptional confluence>=78, target_path>=62, invalidation>=52 and non-high sweep adds +0.007. Confluence<=42 subtracts 0.012 and adds 0.012 risk; target_path<=40 subtracts 0.012 and adds 0.010 risk; invalidation<=38 subtracts 0.012 and adds 0.012 risk.
Activation>0.72 with high sweep adds 0.010 risk. Final TP adjustment is rounded clamp [-0.035,+0.025]; risk addition rounded clamp [0,0.06].
```

Anclajes ejecutables:

- `analysis_engine.py:1349-1425` (`build_zone_probability_context`), SHA-256 `676c0ed9e546e9d5a387fd308c73adebabbede0410210873dac9ed28f06f1921`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: small_internal_sample

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 31. SCORE-TAKER_FLOW_BIAS - Ratio taker buy/sell

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Umbrales 1.12/0.88; efecto +/-0.02 por lado y derivatives_weight

Definicion exacta actual:

```text
If ratio is missing/zero return 0. Long: +0.020 if ratio>1.12, -0.020 if ratio<0.88, else 0. Short is symmetric.
taker_flow_bias=raw*derivatives_weight.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:2084-2089` (`taker_flow_score`), SHA-256 `dae657138b87c321fe83c9b51cf64a1e820105b18f65a0e251b91f88f3513313`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_and_family_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_umbral_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 32. SCORE-CVD_BIAS - CVD proxy

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Umbral +/-0.12; efecto +/-0.018 por lado y micro_weight

Definicion exacta actual:

```text
If CVD ratio is None return 0. Long: +0.018 if ratio>0.12, -0.018 if ratio<-0.12, else 0. Short is symmetric.
cvd_bias=raw*micro_weight.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:2102-2107` (`cvd_flow_score`), SHA-256 `2c552d93324bd044fd4a194bfd081aea55ec13c69c7af577736aa259e69b65f4`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: different_proxy

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 33. SCORE-OI_TREND_BIAS - Tendencia precio-OI

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: OI change >=0.2 y signo precio 24h; efecto +/-0.02

Definicion exacta actual:

```text
If OI change is None, OI change<0.2, or 24h price change is zero: 0.
price_direction=sign(price_change_24h). directional_pressure=price_direction for long and -price_direction for short. Return +0.020 if pressure>0 else -0.020.
oi_trend_bias=raw*derivatives_weight.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:2134-2141` (`open_interest_trend_score`), SHA-256 `cb4f4c19341e8e83a0c7b57af4f100c9142fcc75abc7e43488f0600eb09feb13`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 34. SCORE-BREADTH_BIAS - Breadth crypto

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Advancers 58/42 y mediana; efecto +/-0.02 por macro_weight

Definicion exacta actual:

```text
bullish_breadth iff advancers_24h_pct>=58 and median_change_24h_pct>0; bearish_breadth iff advancers<=42 and median<0.
Long returns +0.020 bullish, -0.020 bearish, else 0; short symmetric.
breadth_bias=raw*max(0.5,macro_weight).
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:2144-2151` (`market_breadth_score`), SHA-256 `1fd0b2c747602d944a54d597300ff58157578ed6e39a41808cf025e64b02648c`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_efecto_y_posponer`. Accion inicial `M5`; posible reemplazo `M10`.

### 35. SCORE-VOLATILITY_PENALTY - SL frente a volatilidad

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.07 si risk_distance < max(range,ATR)*0.35

Definicion exacta actual:

```text
risk_distance_pct=100*abs(stop_loss-entry)/entry.
volatility_penalty=0.07 if risk_distance_pct < max(recent_range_pct,ATR_pct)*0.35; otherwise 0.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: atr_definition_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_penalizacion_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 36. SCORE-LIQUIDITY_PENALTY - Penalizacion de spread

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.03 si spread_pct>0.04

Definicion exacta actual:

```text
liquidity_penalty=0.03 if spread_pct>0.04; otherwise 0.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `separar_de_probabilidad_de_mercado`. Accion inicial `M5`; posible reemplazo `M4`.

### 37. SCORE-OVEREXTENSION_PENALTY - Extension frente a EMA21

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.025 si abs(price_vs_ema21)>max(0.5,ATR*1.8)

Definicion exacta actual:

```text
overextension_penalty=0.025 if abs(price_vs_EMA21_pct) > max(0.5,ATR_pct*1.8); otherwise 0.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: definitions_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 38. SCORE-FUNDING_PENALTY - Funding extremo por lado

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.025 si long funding>0.03 o short funding<-0.03

Definicion exacta actual:

```text
raw=0.025 for long when funding_rate_pct>0.03, or for short when funding_rate_pct<-0.03; 0 when missing or otherwise.
funding_penalty=raw*funding_weight.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:2074-2081` (`funding_context_penalty`), SHA-256 `82d767adb53d52bdfc424fd6af4cdddaf61ea31fa1482d7687a7a536afd75216`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 39. SCORE-FUNDING_RELATIVE_PENALTY - Funding frente a media

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Thresholds internos de funding actual frente a media reciente

Definicion exacta actual:

```text
Return 0 when current/mean funding is missing or abs(mean)<0.000001.
relative_multiple=abs(current_funding)/max(abs(mean_funding),1e-6). raw=0.010 when multiple>=1.8 and current funding is positive for long or negative for short; otherwise 0.
funding_relative_penalty=raw*funding_weight.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:1740-1750` (`funding_relative_context_penalty`), SHA-256 `9976ba1028707b71093771ee616e6ba5a40337586714761c40756056206d40c1`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 40. SCORE-CROWDING_PENALTY - Crowding long/short

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.015 si long ratio>2.0 o short ratio<0.5

Definicion exacta actual:

```text
Return 0 if ratio is missing/zero. Return 0.015 when long and global_long_short_ratio>2.0, or short and ratio<0.5; else 0.
```

Anclajes ejecutables:

- `analysis_engine.py:2092-2099` (`crowding_penalty_score`), SHA-256 `b141b6d52093b909ddb3391c593ec72bef1ee696d51cf54fa50089dc670877ac`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M10`.

### 41. SCORE-LEVEL_PENALTY - Barrera de soporte/resistencia

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.025 si nivel queda antes de max(0.25,35% del reward)

Definicion exacta actual:

```text
reward_distance_pct=100*abs(TP-entry)/entry.
For long use distance_to_resistance; for short use distance_to_support. Return 0.025 when the selected distance is defined and <max(0.25,reward_distance_pct*0.35); else 0.
```

Anclajes ejecutables:

- `analysis_engine.py:2110-2121` (`level_risk_penalty`), SHA-256 `49167acdb050bd7d8c80f158817a75ca63a7fd0803b88f83d52bc1b3e2d334bf`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: family_evidence_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_penalizacion_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 42. SCORE-SENTIMENT_PENALTY - Sentimiento extremo

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.015 con FearGreed >=75 para long o <=25 para short

Definicion exacta actual:

```text
Return 0 when Fear & Greed is missing. Return 0.015 for long when value>=75 or short when value<=25; otherwise 0.
```

Anclajes ejecutables:

- `analysis_engine.py:2124-2131` (`sentiment_extreme_penalty`), SHA-256 `d5f7376c1f1f16fda5a136cc6f0fd6b1f867284e72192d58da03e4129d0d70d9`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: provider_methodology_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_efecto_y_posponer`. Accion inicial `M5`; posible reemplazo `M10`.

### 43. SCORE-HIGHER_TIMEFRAME_PENALTY - Contradiccion HTF

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Penalizacion discreta por estructura 4h/1d contraria y horizonte

Definicion exacta actual:

```text
Confirmation timeframe: 1h intraday_short, 4h intraday_wide, 1w short_swing; fall back to 4h when absent.
base=0.018*htf_penalty_weight. Return base if confirmation EMA stack is bearish for long or bullish for short; else 0.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:1753-1763` (`higher_timeframe_contra_penalty`), SHA-256 `3f03c68a2f726307abf43872aca9f8a2cc9c8f7dae26320859a11412a38e66a4`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: concept_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_duplicidad_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 44. SCORE-TECHNICAL_ENTRY_TIMING_PENALTY - Timing tecnico

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.02 por RSI extremo y extension frente a EMA/ATR

Definicion exacta actual:

```text
Use the first primary timeframe. stretch=max(0.45,ATR_pct*1.7).
Penalty=0.020 when long and RSI>=72 and price_vs_EMA21>stretch, or short and RSI<=28 and price_vs_EMA21<-stretch; otherwise 0.
```

Anclajes ejecutables:

- `analysis_engine.py:2179-2250` (`build_technical_rating`), SHA-256 `59c378c92b0c094ed95987285641906e23c0cbda6f2df78a3694130cc7039071`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: definitions_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 45. SCORE-TECHNICAL_BARRIER_PENALTY - Barrera tecnica al TP

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: 0.025 si barrera<55% reward; 0.012 si <85%

Definicion exacta actual:

```text
Use resistance distance for long and support distance for short. When barrier is defined and reward_distance>0: penalty=0.025 if barrier_distance<0.55*reward; else 0.012 if <0.85*reward; else 0.
```

Anclajes ejecutables:

- `analysis_engine.py:2179-2250` (`build_technical_rating`), SHA-256 `59c378c92b0c094ed95987285641906e23c0cbda6f2df78a3694130cc7039071`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: family_evidence_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_penalizacion_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 46. SCORE-OI_CONTEXT_PENALTY - Contexto precio-OI

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Penalizacion discreta por combinaciones de precio y OI

Definicion exacta actual:

```text
Return 0 if OI change is missing. Return 0.012 when long with price_change_24h>0.5 and OI_change<-0.2, or short with price_change_24h<-0.5 and OI_change<-0.2; otherwise 0.
oi_context_penalty=raw*derivatives_weight.
Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, htf=1.35, funding=1.25.
```

Anclajes ejecutables:

- `analysis_engine.py:1766-1773` (`oi_price_context_penalty`), SHA-256 `fee7ca2b46ae548d0db5b29afd8c5fd7e2646c8869c1a4b1c05e6b93094d3022`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: data_only

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_puntos_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 47. SCORE-CONTRADICTION_PENALTY - Penalizacion por contradicciones

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Cuenta contradicciones y aplica 0.018/0.032/0.045

Definicion exacta actual:

```text
Count one contradiction for opposite non-zero signs between cvd_bias and taker_flow_bias; one each when oi_context_penalty, level_penalty or htf_penalty is non-zero.
Return 0.045 for count>=4; 0.032 for count=3; 0.018 for count=2; 0 for count<2.
```

Anclajes ejecutables:

- `analysis_engine.py:1776-1801` (`combined_contradiction_penalty`), SHA-256 `da70132685b5896d28f2e5dbba6f43ca00323eb851538b5d5720fbe443eba25b`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: none

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_conteo_y_reformular`. Accion inicial `M5`; posible reemplazo `M4`.

### 48. SCORE-RISK_CALIBRATION_TP_ADJUSTMENT - Ajuste TP agregado de calibracion

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_aggregate`.
- Resumen anterior: Suma de gates con floor agregado -0.16

Definicion exacta actual:

```text
tp_adjustment=sum(tp_delta of every active GATE entry in this catalogue).
Returned value=round(max(-0.16,tp_adjustment),4). All current gate TP deltas are non-positive, so there is no positive contribution.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: small_internal_sample

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_ajuste_agregado`. Accion inicial `M5`; posible reemplazo `M4`.

### 49. SCORE-ZONE_RANGE_PROBABILITY_ADJUSTMENT - Ajuste rango por no activacion

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_score_rule`.
- Resumen anterior: Aumenta range_probability por baja activacion pendiente

Definicion exacta actual:

```text
range_adjustment=+0.04 if activation<0.28; else +0.02 if activation<0.42; otherwise 0.
Returned value=round(clamp(range_adjustment,[0,0.04]),4).
```

Anclajes ejecutables:

- `analysis_engine.py:1349-1425` (`build_zone_probability_context`), SHA-256 `676c0ed9e546e9d5a387fd308c73adebabbede0410210873dac9ed28f06f1921`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: none

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `separar_semanticas`. Accion inicial `M5`; posible reemplazo `M4`.

### 50. SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT - Ajuste rango de calibracion

- Origen: `current_production_engine`.
- Capa/tipo actual: `predictive_score` / `active_predictive_adjustment`.
- Tipo de definicion exacta: `exact_executable_constant`.
- Resumen anterior: Ajuste agregado de rango; actualmente no activado en cohorte E1.4

Definicion exacta actual:

```text
range_adjustment is initialized to 0.0 and no current gate changes it.
Returned value=round(range_adjustment,4)=0.0 for every input.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.
- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: none

Limite de transferencia: Ninguna fuente valida el threshold y peso exactos actuales.

Decision M1: `retirar_formula_actual`. Accion inicial `M5`; posible reemplazo `M4`.

### 51. GATE-SL_PROBABILITY_GTE_55 - SL estimado >=55%

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF sl_probability>=0.55 THEN -0.045 TP; +0.10 risk; cap D; force

Definicion exacta actual:

```text
Condition: sl_probability>=0.55.
On activation: tp_delta=-0.045; risk_delta=0.1; quality_penalty+=12; confidence_penalty+=10; EV_score_penalty+=10; execution_risk_addition+=10; grade_cap=D; force_observar=True.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
This is the first branch; the >=0.50 gate is skipped.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 52. GATE-SL_PROBABILITY_GTE_50 - SL estimado >=50%

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF 0.50<=sl_probability<0.55 THEN -0.025 TP; +0.06 risk; cap C

Definicion exacta actual:

```text
Condition: 0.50<=sl_probability<0.55.
On activation: tp_delta=-0.025; risk_delta=0.06; quality_penalty+=8; confidence_penalty+=6; EV_score_penalty+=6; execution_risk_addition+=6; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
This is the elif branch after the >=0.55 test.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 53. GATE-DIRECTION_SCORE_LT_40 - TP estimado <40%

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF tp_probability<0.40 THEN -0.025 TP; +0.07 risk; cap D; force

Definicion exacta actual:

```text
Condition: first_pass_tp_probability<0.40.
On activation: tp_delta=-0.025; risk_delta=0.07; quality_penalty+=8; confidence_penalty+=8; EV_score_penalty+=6; execution_risk_addition+=6; grade_cap=D; force_observar=True.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 54. GATE-TECHNICAL_SCORE_LT_40 - Rating tecnico <40

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF technical_rating.score<40 THEN -0.020 TP; +0.07 risk; cap C

Definicion exacta actual:

```text
Condition: technical_rating.score<40 (missing score defaults to 50).
On activation: tp_delta=-0.02; risk_delta=0.07; quality_penalty+=8; confidence_penalty+=8; EV_score_penalty+=6; execution_risk_addition+=6; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 55. GATE-RR_RATIO_GTE_3 - R/R >=3

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF risk_reward_ratio>=3 THEN -0.035 TP if reward>=3% else -0.020; +0.08 risk; cap C

Definicion exacta actual:

```text
Condition: risk_reward_ratio>=3.0.
On activation: tp_delta=-0.035 if reward_distance>=3.0 else -0.020; risk_delta=0.08; quality_penalty+=15; confidence_penalty+=5; EV_score_penalty+=12; execution_risk_addition+=8; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 56. GATE-REWARD_DISTANCE_GTE_3 - TP distante >=3%

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF reward_distance>=3 THEN -0.025 TP; +0.07 risk; cap C

Definicion exacta actual:

```text
Condition: reward_distance_pct>=3.0.
On activation: tp_delta=-0.025; risk_delta=0.07; quality_penalty+=10; confidence_penalty+=4; EV_score_penalty+=10; execution_risk_addition+=6; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
Can activate together with the R/R>=3 gate.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 57. GATE-RISK_DISTANCE_LT_0_25 - SL <0.25%

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF risk_distance<0.25 THEN -0.025 TP; +0.10 risk; cap C

Definicion exacta actual:

```text
Condition: risk_distance_pct<0.25.
On activation: tp_delta=-0.025; risk_delta=0.1; quality_penalty+=10; confidence_penalty+=6; EV_score_penalty+=8; execution_risk_addition+=12; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
This is the first branch; the >=3.0 branch is skipped.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 58. GATE-RISK_DISTANCE_GTE_3 - SL >=3%

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF risk_distance>=3 THEN +0.08 risk; cap C

Definicion exacta actual:

```text
Condition: risk_distance_pct>=3.0.
On activation: tp_delta=0.0; risk_delta=0.08; quality_penalty+=10; confidence_penalty+=4; EV_score_penalty+=8; execution_risk_addition+=6; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
This is the elif branch after the <0.25 test.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 59. GATE-TICKER_24H_CONTRA_SIDE - Ticker 24h contrario

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF side_signed_contra(price_change_24h,0.25) THEN -0.025 TP; +0.05 risk; cap C

Definicion exacta actual:

```text
Condition: (long and price_change_24h<=-0.25) OR (short and price_change_24h>=0.25).
On activation: tp_delta=-0.025; risk_delta=0.05; quality_penalty+=6; confidence_penalty+=6; EV_score_penalty+=4; execution_risk_addition+=4; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
Missing price change does not activate the gate.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.
- `analysis_engine.py:1059-1062` (`side_signed_contra`), SHA-256 `336a7594c108eb536f8eaa920e81386106584ad01e101870317f6706d658420c`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 60. GATE-EMA_STACK_15M_CONTRA_SIDE - EMA stack 15m contrario

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF timeframe_contra_side(15m,require_stack=True) THEN -0.020 TP; +0.04 risk; cap C

Definicion exacta actual:

```text
Condition: (long and EMA_stack_15m=='bearish') OR (short and EMA_stack_15m=='bullish').
On activation: tp_delta=-0.02; risk_delta=0.04; quality_penalty+=6; confidence_penalty+=6; EV_score_penalty+=4; execution_risk_addition+=4; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
Missing timeframe does not activate the gate.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.
- `analysis_engine.py:1065-1074` (`timeframe_contra_side`), SHA-256 `41937f7e643ff9e0ff01d3d7da6dbf00f330e48b949cb49f099cbf37ac4dad36`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 61. GATE-PRICE_VS_EMA_1H_CONTRA_SIDE - Precio vs EMA21 1h contrario

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF timeframe_contra_side(1h,threshold=0.08) THEN -0.020 TP; +0.04 risk; cap C

Definicion exacta actual:

```text
Condition: (long and price_vs_EMA21_1h<=-0.08) OR (short and price_vs_EMA21_1h>=0.08).
On activation: tp_delta=-0.02; risk_delta=0.04; quality_penalty+=6; confidence_penalty+=6; EV_score_penalty+=4; execution_risk_addition+=4; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
Missing value does not activate the gate.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.
- `analysis_engine.py:1065-1074` (`timeframe_contra_side`), SHA-256 `41937f7e643ff9e0ff01d3d7da6dbf00f330e48b949cb49f099cbf37ac4dad36`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 62. GATE-PENDING_ZONE_NEGATIVE_ADJUSTMENT - Zona pendiente negativa

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF zone_probability_adjustment<0 THEN -0.015 TP; +0.04 risk; cap C

Definicion exacta actual:

```text
Condition: zone_probability_adjustment<0.
On activation: tp_delta=-0.015; risk_delta=0.04; quality_penalty+=6; confidence_penalty+=5; EV_score_penalty+=4; execution_risk_addition+=4; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 63. GATE-PENDING_STOP_BREAKDOWN - Orden stop breakdown

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF entry_order_type=='stop_breakdown' THEN -0.030 TP; +0.08 risk; cap D; force

Definicion exacta actual:

```text
Condition: entry_order_type=='stop_breakdown'.
On activation: tp_delta=-0.03; risk_delta=0.08; quality_penalty+=10; confidence_penalty+=8; EV_score_penalty+=8; execution_risk_addition+=8; grade_cap=D; force_observar=True.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 64. GATE-PENDING_LIQUIDITY_SWEEP_HIGH - Sweep risk alto

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF liquidity_sweep_risk=='alto' THEN -0.020 TP; +0.05 risk; cap C

Definicion exacta actual:

```text
Condition: liquidity_sweep_risk=='alto'.
On activation: tp_delta=-0.02; risk_delta=0.05; quality_penalty+=7; confidence_penalty+=6; EV_score_penalty+=5; execution_risk_addition+=6; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 65. GATE-PENDING_FALSE_BREAKOUT_RISK - Riesgo de falsa ruptura

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF reaction_bias=='falsa_ruptura_riesgo' THEN -0.020 TP; +0.05 risk; cap C

Definicion exacta actual:

```text
Condition: reaction_bias=='falsa_ruptura_riesgo'.
On activation: tp_delta=-0.02; risk_delta=0.05; quality_penalty+=7; confidence_penalty+=6; EV_score_penalty+=5; execution_risk_addition+=6; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 66. GATE-EXTREME_FIB_EXTREME_SENTIMENT_CLUSTER - Fibonacci extremo + sentimiento

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF extreme_fibonacci and extreme_sentiment THEN -0.035 TP; +0.08 risk; cap C

Definicion exacta actual:

```text
Condition: extreme_fibonacci AND extreme_sentiment, where extreme_fibonacci=(Fib bias=='desfavorable' AND (Fib score<30 OR entry_zone=='retroceso_extremo')) and extreme_sentiment=(sentiment_penalty>=0.01).
On activation: tp_delta=-0.035; risk_delta=0.08; quality_penalty+=12; confidence_penalty+=10; EV_score_penalty+=9; execution_risk_addition+=8; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 67. GATE-EXTREME_FIB_SENTIMENT_CVD_CONTRA - Cluster anterior + CVD contrario

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF extreme_fibonacci and extreme_sentiment and cvd_contra THEN -0.015 TP; +0.03 risk; cap C

Definicion exacta actual:

```text
Condition: extreme_fibonacci AND extreme_sentiment AND cvd_bias<-0.005.
On activation: tp_delta=-0.015; risk_delta=0.03; quality_penalty+=4; confidence_penalty+=5; EV_score_penalty+=4; execution_risk_addition+=4; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
Nested inside the preceding Fib+sentiment gate.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 68. GATE-RSI_EXTREME_MULTI_RISK_CLUSTER - RSI extremo + dos riesgos

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF rsi_extreme and material_risk_count>=2 THEN -0.012 TP; +0.025 risk; cap C

Definicion exacta actual:

```text
Condition: rsi_extreme AND material_risk_count>=2, where rsi_extreme=(short and RSI<=30) OR (long and RSI>=70), and material_risk_count=count_true(extreme_fibonacci,extreme_sentiment,cvd_bias<-0.005).
On activation: tp_delta=-0.012; risk_delta=0.025; quality_penalty+=4; confidence_penalty+=4; EV_score_penalty+=3; execution_risk_addition+=4; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.
- `analysis_engine.py:1077-1080` (`rsi_extreme_against_entry`), SHA-256 `f6f716743388bf52a86166409d5422c0ed3b319e6f88ebd7ef8755fc8a1180a2`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 69. GATE-RSI_EXTREME_WITH_FIB_SENTIMENT_CLUSTER - RSI + Fibonacci + sentimiento

- Origen: `current_production_engine`.
- Capa/tipo actual: `risk_calibration` / `internal_empirical_gate`.
- Tipo de definicion exacta: `exact_executable_gate`.
- Resumen anterior: IF rsi_extreme and extreme_fibonacci and extreme_sentiment THEN -0.008 TP; +0.015 risk; cap C

Definicion exacta actual:

```text
Condition: rsi_extreme AND extreme_fibonacci AND extreme_sentiment.
On activation: tp_delta=-0.008; risk_delta=0.015; quality_penalty+=3; confidence_penalty+=3; EV_score_penalty+=2; execution_risk_addition+=3; grade_cap=C; force_observar=False.
All active gates accumulate. Aggregate caps: TP adjustment has floor -0.16; risk addition cap 0.28; quality penalty cap 35; confidence penalty cap 28; EV-score penalty cap 30; execution risk addition cap 32. The strictest grade cap wins.
Nested inside the RSI-extreme multi-risk gate.
```

Anclajes ejecutables:

- `analysis_engine.py:729-1056` (`build_risk_calibration_context`), SHA-256 `ff558a7786e7ac59c2d118db715d045168ad1cbd932d8aa975c09b60d29d25e6`.
- `analysis_engine.py:1077-1080` (`rsi_extreme_against_entry`), SHA-256 `f6f716743388bf52a86166409d5422c0ed3b319e6f88ebd7ef8755fc8a1180a2`.

Respaldo declarado: Origen interno documentado; no hay validacion externa del gate exacto.

Limite de transferencia: Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.

Decision M1: `retirar_gate_del_calculo_conservar_evidencia_historica`. Accion inicial `M5`; posible reemplazo `no_aplica_gate_exacto_retirado`.

### 70. OUT-TP-ADDITIVE - TP score aditivo

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_output`.
- Resumen anterior: 0.5 + biases - penalties

Definicion exacta actual:

```text
tp_raw=0.50 + trend_bias + technical_direction_bias + price_vs_entry_bias + volume_bias + order_book_bias + momentum_bias + regime_bias + fibonacci_adjustment + zone_adjustment + taker_flow_bias + cvd_bias + oi_trend_bias + breadth_bias - volatility_penalty - liquidity_penalty - overextension_penalty - funding_penalty - funding_relative_penalty - crowding_penalty - level_penalty - sentiment_penalty - htf_penalty - technical_entry_timing_penalty - technical_barrier_penalty - oi_context_penalty - contradiction_penalty.
Every named term is defined as its own SCORE entry in this catalogue.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `retirar_y_reconstruir_salida`. Accion inicial `M6`; posible reemplazo `M6`.

### 71. OUT-TP-CAPS - Caps TP

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_output`.
- Resumen anterior: clamp 0.26..0.74 y despues 0.22..0.74

Definicion exacta actual:

```text
first_pass_tp = min(0.74,max(0.26,tp_raw)).
final_tp = min(0.74,max(0.22,first_pass_tp + risk_calibration_tp_adjustment)).
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `retirar_caps_heuristicos`. Accion inicial `M6`; posible reemplazo `M6`.

### 72. OUT-RANGE - Probabilidad de rango

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_output`.
- Resumen anterior: 0.12/0.10/0.08/0.06 + ajustes; cap 0.04..0.22

Definicion exacta actual:

```text
base_range=0.12 for regime compression/mixed; else 0.10 when contradiction_penalty>=0.03; else 0.08 when recent_range_pct<1.2; else 0.06.
first_range=min(0.20,base_range+zone_range_adjustment).
final_range=min(0.22,max(0.04,first_range+risk_calibration_range_adjustment)).
```

Anclajes ejecutables:

- `analysis_engine.py:1849-1854` (`range_probability_for_context`), SHA-256 `563bea5e543ef1725a719c06eb3fc8a5f19a71a53cb00fdd5355b7eba70c74ff`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `reformular_como_expiracion`. Accion inicial `M6`; posible reemplazo `M6`.

### 73. OUT-SL-RESIDUAL - SL residual

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_output`.
- Resumen anterior: max(0.05,1-TP-range)

Definicion exacta actual:

```text
first_pass_sl=max(0.05,1-first_pass_tp-first_range).
final_sl=max(0.05,1-final_tp-final_range).
There is no final renormalization; TP+SL+range can exceed 1 when the 0.05 SL floor binds.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `retirar_y_reconstruir_salida`. Accion inicial `M6`; posible reemplazo `M6`.

### 74. OUT-PROBABILITY-BANDS - Bandas de probabilidad

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_output`.
- Resumen anterior: ancho 0.04/0.06/0.08 por contradiccion

Definicion exacta actual:

```text
width=0.04 if contradiction_penalty==0; 0.06 if 0<contradiction_penalty<0.03; 0.08 otherwise.
For TP and SL: low=max(0.01,p-width/2), high=min(0.99,p+width/2).
For range use min(width,0.05) in the same formula. Values are rounded to 4 decimals; label formats unrounded bounds as whole percentages.
```

Anclajes ejecutables:

- `analysis_engine.py:1857-1863` (`build_probability_ranges`), SHA-256 `c034da08245cf7a003af5e3889790472cabbaada6564873d1842d8e499432c1d`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `retirar_bandas_heuristicas`. Accion inicial `M6`; posible reemplazo `M6`.

### 75. OUT-EV-COST - Esperanza matematica

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `financial_identity`.
- Tipo de definicion exacta: `exact_executable_identity`.
- Resumen anterior: TP*net_win-SL*net_loss-range*cost

Definicion exacta actual:

```text
notional=margin*leverage; gross_win=notional*(reward_distance_pct/100); gross_loss=notional*(risk_distance_pct/100).
estimated_cost=notional*(fee_rate_round_trip+slippage_rate_round_trip)+funding_cost.
net_win=gross_win-estimated_cost; net_loss=gross_loss+estimated_cost.
EV_USDT=TP*net_win - SL*net_loss - range*estimated_cost.
EV_pct_margin=100*EV_USDT/margin when margin!=0 else 0; EV_pct_notional=100*EV_USDT/notional when notional!=0 else 0.
```

Anclajes ejecutables:

- `analysis_engine.py:1876-1907` (`calculate_expected_value`), SHA-256 `dba9e2b9f592c9c44afb2d09407296f41ec1c2ba1fb0dc3fb663a12fe6e8857e`.

Respaldo declarado: La identidad de valor esperado es valida si probabilidades y costes lo son.

Limite de transferencia: TP/SL no calibrados y costes simplificados invalidan su uso decisional.

Decision M1: `conservar_identidad_reconstruir_entradas`. Accion inicial `M7`; posible reemplazo `M7`.

### 76. OUT-FEE - Fee round-trip fija

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_cost_rule`.
- Resumen anterior: notional*0.0008

Definicion exacta actual:

```text
fee_rate_round_trip=0.0008.
fee_component=notional*0.0008.
```

Anclajes ejecutables:

- `analysis_engine.py:1876-1907` (`calculate_expected_value`), SHA-256 `dba9e2b9f592c9c44afb2d09407296f41ec1c2ba1fb0dc3fb663a12fe6e8857e`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `reformular_coste`. Accion inicial `M5`; posible reemplazo `M5`.

### 77. OUT-SLIPPAGE - Slippage minimo

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_cost_rule`.
- Resumen anterior: max(spread_pct/100,0.0002)

Definicion exacta actual:

```text
slippage_rate_round_trip=max(spread_pct/100,0.0002).
slippage_component=notional*slippage_rate_round_trip.
```

Anclajes ejecutables:

- `analysis_engine.py:1876-1907` (`calculate_expected_value`), SHA-256 `dba9e2b9f592c9c44afb2d09407296f41ec1c2ba1fb0dc3fb663a12fe6e8857e`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `reformular_coste`. Accion inicial `M5`; posible reemplazo `M5`.

### 78. OUT-FUNDING-COST - Coste funding absoluto

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_cost_rule`.
- Resumen anterior: notional*abs(funding_rate_pct)/100 una vez

Definicion exacta actual:

```text
funding_cost=notional*abs(funding_rate_pct or 0)/100.
The current formula applies one unsigned funding observation, without multiplying by expected holding periods.
```

Anclajes ejecutables:

- `analysis_engine.py:1876-1907` (`calculate_expected_value`), SHA-256 `dba9e2b9f592c9c44afb2d09407296f41ec1c2ba1fb0dc3fb663a12fe6e8857e`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `reformular_coste`. Accion inicial `M5`; posible reemplazo `M5`.

### 79. OUT-RISK-SCORE - Risk score agregado

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_output`.
- Resumen anterior: Suma manual de flags y cortes 0.12/0.24/0.42

Definicion exacta actual:

```text
risk_raw=(0.20 if stop_too_close else 0)+(0.12 if R/R<1.2 else 0)+(0.08 if recent_range_pct>2.5 else 0)+(0.06 if spread_pct>0.04 else 0)+(0.05 if overextension_penalty else 0)+(0.06 if funding_penalty else 0)+(0.04 if funding_relative_penalty else 0)+(0.04 if crowding_penalty else 0)+(0.05 if level_penalty else 0)+(0.03 if sentiment_penalty else 0)+(0.07 if htf_penalty else 0)+(0.05 if timing_penalty else 0)+(0.05 if barrier_penalty else 0)+Fib_risk+zone_risk+calibration_risk+(0.08 if contradiction_penalty>=0.03 else 0).
risk_score=clamp(risk_raw,[0,1]). Level: high>=0.42; medium-high>=0.24; medium>=0.12; low otherwise.
```

Anclajes ejecutables:

- `analysis_engine.py:126-616` (`analyze_trade`), SHA-256 `1da879381e0a1710926dc94b15dfcf78fea2c7ecf6e0080b03723cd33303f3af`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `reformular_capa_de_riesgo`. Accion inicial `M5`; posible reemplazo `M5`.

### 80. OUT-GRADE - Grado A/B/C/D

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_policy`.
- Resumen anterior: Cortes TP, risk_score y expected_value_score + cap

Definicion exacta actual:

```text
A iff TP>=0.62 and risk_score<0.20 and EV_score>=58.
Else B iff TP>=0.52 and risk_score<0.36 and EV_score>=50.
Else C iff TP>=0.44 and EV_score>=42; else D.
Then apply the strictest active calibration grade cap using order A<B<C<D; a cap can only worsen the grade.
```

Anclajes ejecutables:

- `analysis_engine.py:1986-1993` (`grade_from_scores`), SHA-256 `898d14af67d9996c0a0ba96d6561a200ff395ccdbb3dd3c1122d9d9bd99be322`.
- `analysis_engine.py:1092-1096` (`cap_grade`), SHA-256 `9c110bea1ad55eab6fdb693c4fd47b632a81454a044cfbee8fc66888715a8ffa`.
- `analysis_engine.py:1083-1089` (`stricter_grade_cap`), SHA-256 `412d3845e7cb0d2c8a2ba0c8d2ccf029e8b5c64e04bc6f27b99492d0f7587b27`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `reformular_politica`. Accion inicial `M5`; posible reemplazo `M5`.

### 81. OUT-CONFIDENCE - Confianza textual

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_policy`.
- Resumen anterior: Cortes 76/61/46 sobre confidence_score

Definicion exacta actual:

```text
confidence='alta' if confidence_score>=76; 'media' if >=61; 'media-baja' if >=46; 'baja' otherwise.
```

Anclajes ejecutables:

- `analysis_engine.py:1996-2003` (`confidence_from_score`), SHA-256 `6a3d5a7bbdd1e47e1bb28be46e8655e498c4cf75409d02266c891bbe11da8a58`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `reformular_incertidumbre`. Accion inicial `M5`; posible reemplazo `M5`.

### 82. OUT-DECISION - Decision simular/observar

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_policy`.
- Resumen anterior: Reglas por grade, risk, confidence, EV y force

Definicion exacta actual:

```text
In order: if force_observar then 'observar'; else if EV_USDT<0 then 'observar'; else if grade in {A,B}, risk!='alto' and confidence in {alta,media}, then 'simular'; else if grade in {B,C} and risk!='alto', then 'simular con tamano prudente'; else 'observar'.
```

Anclajes ejecutables:

- `analysis_engine.py:2006-2022` (`decision_from_context`), SHA-256 `187a9820606f132746fbbba0b1445e7902b5e14cf3828a72167b9ee4ba351695`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `reformular_politica`. Accion inicial `M5`; posible reemplazo `M5`.

### 83. OUT-LAYERED-SCORES - Scores por capas

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_output`.
- Resumen anterior: Transformaciones manuales 0..100 de direccion/calidad/riesgo/confianza/EV

Definicion exacta actual:

```text
map100(x,lo,hi)=round(clamp((x-lo)/(hi-lo),[0,1])*100), or 50 if hi==lo. direction_score=round(TP*100).
risk_design_penalty=min(22,risk_distance_pct*4.5); ev_design_score=map100(EV_pct_notional,-0.8,1.2).
quality=round(clamp(42+0.16*map100(R/R,0.8,3.2)+0.22*ev_design_score+0.12*(Fib_score-50)-risk_design_penalty,[0,100])); then max(0,quality-calibration_quality_penalty).
execution=round(clamp(30+220*volatility_penalty+300*level_penalty+Fib_execution+250*liquidity_penalty+calibration_execution+0.35*map100(spread_pct,0,0.08),[0,100])).
alignment starts 70; subtract round(700*contradiction_penalty) when non-zero; subtract 12 when HTF penalty; add round(420*regime_bias); subtract 12 when taker_flow_bias*cvd_bias<0; add technical confidence_adjustment; subtract calibration confidence penalty. confidence_score=clamp(alignment,[15,95]).
EV_score=max(0,map100(EV_pct_notional,-1.0,1.6)-calibration_EV_penalty).
```

Anclajes ejecutables:

- `analysis_engine.py:1910-1983` (`build_layered_scores`), SHA-256 `dc6059c2579c7e089a727ffe0a043c58832b1c5174fc8961a47bb7ac282165c8`.
- `analysis_engine.py:2356-2360` (`score_to_percent`), SHA-256 `5f52986a8a1cbc91206f18d954bc13a59ed8f20b057470314711f32d4c547f0f`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `convertir_en_traza`. Accion inicial `M5`; posible reemplazo `M5`.

### 84. OUT-HORIZON-FALLBACK - Fallback de horizonte

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_fallback`.
- Resumen anterior: Valor desconocido usa intraday_short

Definicion exacta actual:

```text
profile = TIME_HORIZON_PROFILES.get(requested_value, TIME_HORIZON_PROFILES['intraday_short']).
Every unknown horizon silently uses intraday_short parameters.
```

Anclajes ejecutables:

- `analysis_engine.py:104-105` (`time_horizon_profile`), SHA-256 `d7f141ea7583b267db39d406d586af1bc54e393b29d1f863bee74c1efd035ad6`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `retirar_fallback`. Accion inicial `M5`; posible reemplazo `M5`.

### 85. OUT-MISSING-DATA - Defaults neutrales por falta de datos

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `output_transformation`.
- Tipo de definicion exacta: `exact_executable_fallback`.
- Resumen anterior: RSI=50, EMA=precio y multiples None->0

Definicion exacta actual:

```text
When a timeframe lacks any of closes/highs/lows/volumes/taker_buy_volumes: EMA9=EMA21=EMA50=EMA200=current_price; RSI=50; ATR=ATR_pct=range=last_body=distances=price_vs_EMA=0; volume_ratio=1; taker_buy_ratio=0.5; position_in_range=0.5; EMA_stack='mixed'.
Other current neutralizations include missing score inputs returning 0 in their individual SCORE rules and missing derivatives falling back from selected period to the legacy 5m fields.
```

Anclajes ejecutables:

- `data_engine.py:104-165` (`summarize_timeframe`), SHA-256 `d1dba5310f27d2b162dbecbfe496d4c572fbebe8e2978c20c1e809c1373ba136`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `retirar_defaults_neutrales`. Accion inicial `M5`; posible reemplazo `M5`.

### 86. OUT-RISK-CAL-METRIC - Metrica visual de calibracion

- Origen: `current_production_engine`.
- Capa/tipo actual: `output_and_policy` / `presentation_rule`.
- Tipo de definicion exacta: `exact_executable_presentation`.
- Resumen anterior: 100-len(flags)*10-risk_addition

Definicion exacta actual:

```text
If at least one calibration flag is active: display_score=max(0,100-10*len(flags)-round(100*risk_addition)); bias='desfavorable'.
If no flag is active: display_score=82 and bias='neutral'.
This is presentation only and does not feed TP, SL, grade or decision.
```

Anclajes ejecutables:

- `analysis_engine.py:1688-1710` (`build_risk_calibration_metric`), SHA-256 `e05acdc396fbdcac689abf58cb656864db6c7d4280672a581357234ae0e9a9c4`.

Respaldo declarado: Diseno interno; sin fuente para parametros exactos.

Limite de transferencia: No acredita probabilidad, calibracion ni rentabilidad.

Decision M1: `presentacion_unicamente_redefinir`. Accion inicial `M7`; posible reemplazo `M7`.

## 4. Regla de mantenimiento

El JSON es el artefacto canonico. El generador vuelve a resolver cada
funcion y recalcula su SHA-256. `--check` falla si el informe o el
JSON dejan de coincidir con el generador; las pruebas fallan si falta
una entrada, una definicion o un anclaje.

Este anexo describe lo que existe y no legitima ninguna heuristica.
El propietario aprobo M1-A el 2026-07-27. M1 queda completamente
cerrada y M2 pasa a ser la siguiente fase pendiente, todavia no
iniciada.
