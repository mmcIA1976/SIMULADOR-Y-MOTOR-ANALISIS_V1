# M4.7 - 26 reglas nucleares y 1 operador auxiliar

Fecha: 2026-07-27
Estado: MATERIAL DE AUDITORIA; M4 NO CERRADA; M5 NO INICIADA

## Como leer este documento

El catalogo contiene 26 reglas nucleares P0 y 1 operador auxiliar.
Una formula documentada no equivale a una probabilidad validada.
Las 15 hipotesis siguen sin verificar y no tienen peso productivo.
Las decisiones de politica provisionales se registran aparte de la evidencia.

## Indice rapido de formulas

| # | ID | Subfase | Formula |
|---:|---|---|---|
| 1 | `M4-RULE-HORIZON-SAMPLING-001` | M4.2 | `I={delta in profile_intervals: H mod delta=0 and H/delta>=24}<br>delta*=max(I)<br>N_H=H/delta*` |
| 2 | `M4-RULE-PLAN-GEOMETRY-001` | M4.2 | `s=+1 long; s=-1 short<br>d_TP=s*ln(TP/E)<br>d_SL=-s*ln(SL/E)<br>valid iff d_TP>0 and d_SL>0` |
| 3 | `M4-RULE-LOG-RETURNS-001` | M4.2 | `r_i=ln(C_i/C_(i-1))` |
| 4 | `M4-RULE-REALIZED-VOLATILITY-001` | M4.2 | `RV_prev(H)=sum_(i=1..N_H)(r_i^2)<br>sigma_prev(H)=sqrt(RV_prev(H))` |
| 5 | `M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002` | M4.2 | `z_TP=d_TP/sigma_prev(H)<br>z_SL=d_SL/sigma_prev(H)<br>b=ln(d_TP/d_SL)` |
| 6 | `M4-RULE-PENDING-ACTIVATION-001` | M4.2 | `market: d_entry=0, z_entry=0<br>pending: d_entry=abs(ln(E/P_analysis))<br>z_entry=d_entry/sigma_prev(H)` |
| 7 | `M4-RULE-EXPONENTIAL-SMOOTHER-001` | M4.3 | `S_0=x_0<br>S_t=alpha*x_t+(1-alpha)*S_(t-1), 0<alpha<=1` |
| 8 | `M4-RULE-PATH-STRUCTURE-001` | M4.3 | `D_W=sum(r_i)=ln(C_end/C_start)<br>TV_W=sum(abs(r_i))<br>if TV_W>0: E_W=abs(D_W)/TV_W; SE_W=D_W/TV_W<br>if TV_W=0: E_W=0; SE_W=0; flat_path=true` |
| 9 | `M4-RULE-PRIOR-EXTREMA-001` | M4.3 | `X_high=max(H_i), X_low=min(L_i) over previous exact H<br>long target extreme=X_high; short target extreme=X_low<br>between=entry<X_high<TP long; TP<X_low<entry short` |
| 10 | `M4-RULE-VOLATILITY-RANK-001` | M4.3 | `q=(count(RV_j<RV_t)+0.5*count(RV_j=RV_t))/60<br>j are 60 strictly prior non-overlapping H windows` |
| 11 | `M4-RULE-MTF-HIERARCHY-001` | M4.3 | `calculate SE_W for W in {H,2H,4H} on the same closed grid<br>sign_W=sign(SE_W)<br>agreement in {all_positive,all_negative,mixed,flat_present}` |
| 12 | `M4-RULE-CONTINUOUS-REGIME-001` | M4.3 | `R_t=(q_RV,t, SE_H,t)` |
| 13 | `M4-RULE-AGGRESSOR-IMBALANCE-001` | M4.4 | `B_H=sum(p_i*q_i where buyer_is_maker=false)<br>S_H=sum(p_i*q_i where buyer_is_maker=true)<br>ATI_H=(B_H-S_H)/(B_H+S_H)<br>periodic alternative=(sum(buyVol)-sum(sellVol))/total` |
| 14 | `M4-RULE-OPEN-INTEREST-CHANGE-001` | M4.4 | `dOI_H=ln(OI_t/OI_(t-H))<br>current_timestamp_ms-previous_timestamp_ms=H*1000` |
| 15 | `M4-RULE-PRICE-OI-STATE-001` | M4.4 | `POI_H=(D_H,dOI_H)` |
| 16 | `M4-RULE-SPOT-FUTURES-BASIS-001` | M4.4 | `mid_F=(F_bid+F_ask)/2; mid_S=(S_bid+S_ask)/2<br>b_mid=ln(mid_F/mid_S)<br>b_sellF_buyS=ln(F_bid/S_ask)<br>b_buyF_sellS=ln(F_ask/S_bid)` |
| 17 | `M4-RULE-MARK-INDEX-PREMIUM-001` | M4.4 | `b_mark_index=ln(markPrice/indexPrice)` |
| 18 | `M4-RULE-FUNDING-STATE-001` | M4.4 | `linearized_f_last_hour=lastFundingRate/fundingIntervalHours<br>L_prev(H)=sum(f_j where t-H<fundingTime_j<=t)<br>L_prev_hour(H)=L_prev(H)/H_hours<br>N_schedule=count configured event times within future H` |
| 19 | `M4-RULE-DERIVATIVES-CONTEXT-001` | M4.4 | `DC_H=(ATI_H,dOI_H,b_mid,linearized_f_last_hour)` |
| 20 | `M4-RULE-QUOTED-SPREAD-001` | M4.5 | `mid=(best_bid+best_ask)/2<br>spread_quote=best_ask-best_bid<br>spread_fraction_mid=spread_quote/mid` |
| 21 | `M4-RULE-DEPTH-SWEEP-001` | M4.5 | `buy consume asks; sell consume bids<br>VWAP_filled=sum(price_i*filled_qty_i)/filled_qty<br>D=+1 buy, -1 sell<br>IS_filled_quote=D*(sum(price_i*filled_qty_i)-arrival_mid*filled_qty)<br>IS_filled_fraction=IS_filled_quote/(arrival_mid*filled_qty)<br>complete_VWAP=VWAP_filled iff filled_qty=requested_qty<br>fill_ratio=filled_qty/requested_qty` |
| 22 | `M4-RULE-FEE-SCENARIOS-001` | M4.5 | `fee(role)=notional*commission_rate(role)<br>lower=min(fee(role)); upper=max(fee(role))<br>pretrade one-role input is a scenario point, not an observation<br>exact iff execution is observed, role is unique, notional is executed and fee_asset is known` |
| 23 | `M4-RULE-FUNDING-CASHFLOW-001` | M4.5 | `position_sign=+1 long, -1 short<br>cashflow_event=-position_sign*quantity*mark_price*rate<br>cashflow_total=sum(cashflow_event)` |
| 24 | `M4-RULE-PLAN-EXPOSURE-001` | M4.5 | `notional=margin*leverage<br>quantity=notional/entry<br>gross_pnl(P)=direction*quantity*(P-entry)<br>gross_reward=gross_pnl(TP)<br>gross_risk=-gross_pnl(SL)<br>gross_RR=gross_reward/gross_risk<br>risk_fraction_margin=gross_risk/margin` |
| 25 | `M4-RULE-NET-PAYOFFS-001` | M4.5 | `net_payoff_k=gross_price_pnl_k-fee_k-IS_cost_k+funding_k<br>no_entry direct trading cashflow=0` |
| 26 | `M4-RULE-EXPECTED-VALUE-001` | M4.5 | `0<=p_k<=1<br>sum(p_k)=1<br>EV=sum(p_k*y_k)` |
| 27 | `M4-RULE-EVALUATION-READINESS-001` | M4.5 | `economic_ready=all(required economic statuses available\|N/A)<br>account_risk_ready=(account_risk status=available)<br>decision_authorized=false until governance is defined` |

## 1. M4-RULE-HORIZON-SAMPLING-001

**Nombre:** Seleccion exacta de intervalo para el horizonte

**Subfase:** M4.2

**Bloques:** 26

**Tipo:** `deterministic_policy`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Select a closed-kline interval that divides the exact horizon without temporal interpolation.

### Datos

- {"m3_data_contract_ids":["M3-DATA-001","M3-DATA-005"],"provider":"user_plan_and_binance_usdm"}

### Tiempo, unidades y frescura

- {"freshness":"M3-DATA-005 closed-period contract","market":"Binance USD-M perpetual","price_unit":"quote_asset_per_base","return_unit":"natural_log_return","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"timestamps":"M3 provider close_time plus requested_at/received_at; all <= analysis_at"}

### Formula exacta

```text
I={delta in profile_intervals: H mod delta=0 and H/delta>=24}
delta*=max(I)
N_H=H/delta*
```

### Normalizacion entre pares

- Same algorithm for every pair; only H and profile select delta.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- valid exact horizon inside approved profile

### No aplicacion o bloqueo

- no supported exact divisor with at least 24 returns

### Fuentes y afirmacion respaldada

- [BINANCE-USDM-KLINES](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) [provider_semantics]: Supported kline intervals and timestamp fields.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, weight or threshold.
- No source proves transfer to all six pairs and three horizons.
- The minimum of 24 returns is project policy, not an academic optimum.

### Relacion esperada con resultados

- No TP/SL direction; data-resolution policy only.

### Control de doble conteo

- Produces one interval identity, no evidence.

### Ausencia de datos

- Block reachability family.

### Pruebas, limites e invariantes

- H is never rounded
- delta divides H exactly
- N_H>=24
- selection is pair-independent

### Traza producida

- time_horizon
- horizon_seconds
- interval
- interval_seconds
- returns_per_horizon
- selection_policy

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Suspend if M7 shows unstable or aliased RV at the selected grid.
- Change only by versioned M4 amendment before empirical testing.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 2. M4-RULE-PLAN-GEOMETRY-001

**Nombre:** Geometria logaritmica long/short

**Subfase:** M4.2

**Bloques:** 26, 28

**Tipo:** `deterministic_calculation`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Represent TP and SL distance symmetrically across sides.

### Datos

- {"m3_data_contract_ids":["M3-DATA-001"],"provider":"user_plan_and_binance_usdm"}

### Tiempo, unidades y frescura

- {"freshness":"M3-DATA-005 closed-period contract","market":"Binance USD-M perpetual","price_unit":"quote_asset_per_base","return_unit":"natural_log_return","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"timestamps":"M3 provider close_time plus requested_at/received_at; all <= analysis_at"}

### Formula exacta

```text
s=+1 long; s=-1 short
d_TP=s*ln(TP/E)
d_SL=-s*ln(SL/E)
valid iff d_TP>0 and d_SL>0
```

### Normalizacion entre pares

- Log ratios are dimensionless and scale-invariant.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- valid plan geometry

### No aplicacion o bloqueo

- invalid side, price or barrier ordering

### Fuentes y afirmacion respaldada

- `M2-SEMANTIC-CONTRACT` [internal_project_contract]: Approved side-symmetric geometry.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, weight or threshold.
- No source proves transfer to all six pairs and three horizons.

### Relacion esperada con resultados

- Holding all else fixed, a farther same-side barrier cannot be declared easier to reach.

### Control de doble conteo

- Single canonical geometry for all later blocks.

### Ausencia de datos

- Block the complete analysis.

### Pruebas, limites e invariantes

- long/short mirror symmetry
- positive distances
- price-scale invariance
- continuous response to barrier movement

### Traza producida

- side_sign
- entry
- take_profit
- stop_loss
- tp_log_distance
- sl_log_distance

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Withdraw any implementation that differs from M2.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 3. M4-RULE-LOG-RETURNS-001

**Nombre:** Retornos logaritmicos de velas cerradas

**Subfase:** M4.2

**Bloques:** 26

**Tipo:** `deterministic_calculation`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Create the only return series used by M4.2 volatility.

### Datos

- {"m3_data_contract_ids":["M3-DATA-005"],"provider":"user_plan_and_binance_usdm"}

### Tiempo, unidades y frescura

- {"freshness":"M3-DATA-005 closed-period contract","market":"Binance USD-M perpetual","price_unit":"quote_asset_per_base","return_unit":"natural_log_return","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"timestamps":"M3 provider close_time plus requested_at/received_at; all <= analysis_at"}

### Formula exacta

```text
r_i=ln(C_i/C_(i-1))
```

### Normalizacion entre pares

- Dimensionless return; same formula for every pair.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- M3-compliant consecutive closed klines

### No aplicacion o bloqueo

- gap, open bar, invalid close or insufficient history

### Fuentes y afirmacion respaldada

- [ANDERSEN-BOLLERSLEV-DIEBOLD-LABYS-2003](https://doi.org/10.1111/1468-0262.00418) [mathematical_or_methodological_definition]: High-frequency return inputs for realized volatility.
- [BINANCE-USDM-KLINES](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) [provider_semantics]: Close price and close timestamp semantics.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, weight or threshold.
- No source proves transfer to all six pairs and three horizons.

### Relacion esperada con resultados

- No direction or probability by itself.

### Control de doble conteo

- One canonical return series per selected interval.

### Ausencia de datos

- Block realized volatility and dependent rules.

### Pruebas, limites e invariantes

- constant price gives zero returns
- multiplying all prices by a constant does not change returns
- gaps and invalid prices block

### Traza producida

- close_count
- return_count
- first_close_time
- last_close_time
- return_series_hash

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Withdraw any fallback that inserts zero returns.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 4. M4-RULE-REALIZED-VOLATILITY-001

**Nombre:** Volatilidad realizada del horizonte anterior

**Subfase:** M4.2

**Bloques:** 26

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Measure observed log-price variation over the immediately preceding exact horizon without scaling from another horizon.

### Datos

- {"m3_data_contract_ids":["M3-DATA-001","M3-DATA-005"],"provider":"user_plan_and_binance_usdm"}

### Tiempo, unidades y frescura

- {"freshness":"M3-DATA-005 closed-period contract","market":"Binance USD-M perpetual","price_unit":"quote_asset_per_base","return_unit":"natural_log_return","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"timestamps":"M3 provider close_time plus requested_at/received_at; all <= analysis_at"}

### Formula exacta

```text
RV_prev(H)=sum_(i=1..N_H)(r_i^2)
sigma_prev(H)=sqrt(RV_prev(H))
```

### Normalizacion entre pares

- Log-volatility is dimensionless and calculated over the same exact H for every pair.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete previous-H window with at least 24 returns

### No aplicacion o bloqueo

- missing/gapped/future/stale bars
- zero sigma blocks normalized reachability

### Fuentes y afirmacion respaldada

- [ANDERSEN-BOLLERSLEV-DIEBOLD-LABYS-2003](https://doi.org/10.1111/1468-0262.00418) [family_or_adjacent_foundation]: Sum-of-squared high-frequency returns measures RV.
- [XIE-ET-AL-2019-BITCOIN-RV](https://doi.org/10.3390/econometrics7030040) [external_empirical_evidence_adjacent_to_project_target]: Bitcoin RV can be forecast, but competing model specifications matter.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, weight or threshold.
- No source proves transfer to all six pairs and three horizons.
- Lagged sigma_prev(H) is not labelled a forecast.
- No persistence coefficient is assumed.

### Relacion esperada con resultados

- Higher sigma lowers both normalized barrier distances; it does not choose TP versus SL direction.

### Control de doble conteo

- RV is one scale input. M4.3 regime may classify it but cannot re-add the same value as independent evidence.

### Ausencia de datos

- Block all sigma-normalized M4.2 outputs.

### Pruebas, limites e invariantes

- exact previous-H span
- RV>=0
- sigma=sqrt(RV)
- scale invariance
- no annualization or cross-horizon square-root scaling

### Traza producida

- interval
- horizon_seconds
- return_count
- window_start_close_time
- window_end_close_time
- realized_variance
- realized_volatility
- forecast_status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Reject M4-HYP-REACH-001 if independent evaluation shows no incremental reachability value or unstable pair behavior.
- A future forecast model belongs to M6 and needs a new rule ID.

### Hipotesis predictiva separada

- ID: `M4-HYP-REACH-001`.
- Estado: `proposed_unverified`.
- Enunciado: Previous-horizon RV may provide a useful reference scale for next-horizon barrier distance.
- No afirma: It is not assumed equal to future volatility and receives no probability weight.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 5. M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002

**Nombre:** Geometria de barreras normalizada por volatilidad

**Subfase:** M4.2

**Bloques:** 26, 28

**Tipo:** `deterministic_calculation`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Express both barriers in comparable horizon-volatility units.

### Datos

- {"m3_data_contract_ids":["M3-DATA-001","M3-DATA-005"],"provider":"user_plan_and_binance_usdm"}

### Tiempo, unidades y frescura

- {"freshness":"M3-DATA-005 closed-period contract","market":"Binance USD-M perpetual","price_unit":"quote_asset_per_base","return_unit":"natural_log_return","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"timestamps":"M3 provider close_time plus requested_at/received_at; all <= analysis_at"}

### Formula exacta

```text
z_TP=d_TP/sigma_prev(H)
z_SL=d_SL/sigma_prev(H)
b=ln(d_TP/d_SL)
```

### Normalizacion entre pares

- Dimensionless z values comparable across price scales.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- valid geometry and finite sigma_prev(H)>0

### No aplicacion o bloqueo

- invalid geometry, missing history or sigma<=0

### Fuentes y afirmacion respaldada

- `M2-SEMANTIC-CONTRACT` [internal_project_contract]: Mandatory z_TP and z_SL geometry.
- [POETZELBERGER-WANG-2001](https://doi.org/10.1239/jap/996986650) [family_or_adjacent_foundation]: Actual crossing probability requires a specified path process and boundary treatment.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, weight or threshold.
- No source proves transfer to all six pairs and three horizons.
- z is not a normal CDF input until M6 selects and validates a model.
- No threshold such as one or two sigma is a decision boundary.

### Relacion esperada con resultados

- Continuous monotonic geometry constraint, not a probability or directional signal.

### Control de doble conteo

- Geometry appears once in M6. Raw percentage, ATR bands and price-vs-entry bonuses cannot re-enter separately.

### Ausencia de datos

- Block probability publication.

### Pruebas, limites e invariantes

- z_TP>0 and z_SL>0
- barrier monotonicity
- volatility monotonicity
- long/short mirror symmetry
- continuity

### Traza producida

- tp_log_distance
- sl_log_distance
- sigma_prev_horizon
- z_tp
- z_sl
- distance_balance_log_ratio

### Campos prohibidos o reservados a null

- probability

### Refutacion, suspension o retirada

- Any later model violating monotonicity fails M7.
- Withdraw any score bands attached directly to z.

### Hipotesis predictiva separada

- ID: `M4-HYP-REACH-002`.
- Estado: `mathematical_constraint_for_future_model`.
- Enunciado: Holding all other state fixed, increasing only z_TP must not increase P(TP first); likewise for z_SL and P(SL first).

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 6. M4-RULE-PENDING-ACTIVATION-001

**Nombre:** Distancia de activacion para entrada pendiente

**Subfase:** M4.2

**Bloques:** 28

**Tipo:** `deterministic_calculation`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Represent the pre-entry barrier separately from TP/SL after entry under the M2 event tree.

### Datos

- {"m3_data_contract_ids":["M3-DATA-001","M3-DATA-004","M3-DATA-005"],"provider":"user_plan_and_binance_usdm"}

### Tiempo, unidades y frescura

- {"freshness":"M3-DATA-005 closed-period contract","market":"Binance USD-M perpetual","price_unit":"quote_asset_per_base","return_unit":"natural_log_return","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"timestamps":"M3 provider close_time plus requested_at/received_at; all <= analysis_at"}

### Formula exacta

```text
market: d_entry=0, z_entry=0
pending: d_entry=abs(ln(E/P_analysis))
z_entry=d_entry/sigma_prev(H)
```

### Normalizacion entre pares

- Dimensionless log distance over the same sigma_prev(H).

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- market entry or valid unsatisfied pending trigger

### No aplicacion o bloqueo

- missing trigger_condition
- pending condition already satisfied
- invalid or stale current price

### Fuentes y afirmacion respaldada

- `M2-SEMANTIC-CONTRACT` [internal_project_contract]: No-entry and post-entry expiry are separate outcomes.
- `M3-DATA-CONTRACTS` [internal_project_contract]: Plan trigger, analysis price and timestamps are pre-trade data.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, weight or threshold.
- No source proves transfer to all six pairs and three horizons.
- Distance alone does not define activation probability.

### Relacion esperada con resultados

- Feeds a future P(entry within H) branch; never adds points to conditional P(TP first | entry).

### Control de doble conteo

- Entry activation is evaluated once before conditional TP/SL.

### Ausencia de datos

- Block pending-order probability analysis.

### Pruebas, limites e invariantes

- market z_entry=0
- pending z_entry>0
- trigger direction preserved
- already-satisfied pending trigger rejected
- activation probability remains null

### Traza producida

- entry_type
- trigger_condition
- entry_order_type
- current_price
- entry
- entry_log_distance
- z_entry
- activation_status

### Campos prohibidos o reservados a null

- activation_probability

### Refutacion, suspension o retirada

- Any future activation model must preserve M2 probability mass.
- Withdraw any zone score or fixed activation band.

### Hipotesis predictiva separada

- ID: `M4-HYP-PENDING-001`.
- Estado: `mathematical_constraint_for_future_model`.
- Enunciado: Holding path law fixed, moving an unsatisfied entry trigger farther away must not increase activation probability.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 7. M4-RULE-EXPONENTIAL-SMOOTHER-001

**Nombre:** Operador de suavizado exponencial

**Subfase:** M4.3

**Bloques:** 1, 3

**Tipo:** `deterministic_operator_not_p0_evidence`

**Estado:** `documented_operator_not_admitted_as_p0_evidence`

### Objetivo

Preserve the standard recursive operator while refusing unsupported EMA periods and crossover meanings.

### Datos

- {"m3_data_contract_ids":["M3-DATA-005"],"provider":"Binance USD-M and immutable user plan"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"market":"Binance USD-M perpetual","normalized_units":"log_return_or_dimensionless","price_unit":"quote_asset_per_base","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant closed data only; every observation <= analysis_at"}

### Formula exacta

```text
S_0=x_0
S_t=alpha*x_t+(1-alpha)*S_(t-1), 0<alpha<=1
```

### Normalizacion entre pares

- Natural-log ratios, path ratios or within-pair empirical ranks.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M4.2-compliant closed history
- same formula and policy for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or invalid data
- insufficient declared history

### Fuentes y afirmacion respaldada

- [NIST-SINGLE-EXPONENTIAL-SMOOTHING](https://www.itl.nist.gov/div898/handbook/pmc/section4/pmc431.htm) [mathematical_or_methodological_definition]: Recursive exponential smoothing and initialization.

### Lo que las fuentes no respaldan

- No source supplies a project score, probability, weight or threshold.
- Evidence from other assets or horizons is not assumed transferable.
- No alpha or 9/21/50/200 period is approved.
- Price above/below a smoother is not a directional rule.

### Relacion esperada con resultados

- None; operator is descriptive only.

### Control de doble conteo

- Cannot enter P0 alongside path displacement.

### Ausencia de datos

- Do not calculate; never replace history with a shorter EMA.

### Pruebas, limites e invariantes

- 0<alpha<=1
- explicit initialization
- constant input remains constant

### Traza producida

- alpha
- initialization
- input_count
- smoothed_value

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Withdraw any fixed period introduced without a new rule card.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 8. M4-RULE-PATH-STRUCTURE-001

**Nombre:** Desplazamiento y eficiencia de trayectoria

**Subfase:** M4.3

**Bloques:** 1, 24

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Separate net displacement from total path variation over an exact closed window.

### Datos

- {"m3_data_contract_ids":["M3-DATA-005"],"provider":"Binance USD-M and immutable user plan"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"market":"Binance USD-M perpetual","normalized_units":"log_return_or_dimensionless","price_unit":"quote_asset_per_base","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant closed data only; every observation <= analysis_at"}

### Formula exacta

```text
D_W=sum(r_i)=ln(C_end/C_start)
TV_W=sum(abs(r_i))
if TV_W>0: E_W=abs(D_W)/TV_W; SE_W=D_W/TV_W
if TV_W=0: E_W=0; SE_W=0; flat_path=true
```

### Normalizacion entre pares

- Natural-log ratios, path ratios or within-pair empirical ranks.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M4.2-compliant closed history
- same formula and policy for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or invalid data
- insufficient declared history

### Fuentes y afirmacion respaldada

- [MOSKOWITZ-OOI-PEDERSEN-2012](https://doi.org/10.1016/j.jfineco.2011.11.003) [external_empirical_evidence_adjacent_to_project_target]: Past return sign showed momentum at monthly horizons in traditional futures.
- [HUDSON-URQUHART-2021](https://doi.org/10.1007/s10479-019-03357-1) [external_empirical_evidence_adjacent_to_project_target]: Crypto technical-rule performance varied by asset and failed OOS for Bitcoin in their selected test.

### Lo que las fuentes no respaldan

- No source supplies a project score, probability, weight or threshold.
- Evidence from other assets or horizons is not assumed transferable.
- Path efficiency itself is a project deterministic measure.
- Positive displacement is not automatically bullish evidence.

### Relacion esperada con resultados

- No direct effect; future models may test side-aligned SE_W under regime and horizon controls.

### Control de doble conteo

- D_W, E_W and SE_W are one price-path evidence family.

### Ausencia de datos

- Block structure and all dependent combinations.

### Pruebas, limites e invariantes

- 0<=E_W<=1
- -1<=SE_W<=1
- TV_W=0 implies E_W=SE_W=0 and flat_path=true
- scale invariance
- D_W equals log endpoint ratio

### Traza producida

- window_seconds
- return_count
- log_displacement
- total_log_variation
- path_efficiency
- signed_path_efficiency
- direction_descriptor

### Campos prohibidos o reservados a null

- prediction

### Refutacion, suspension o retirada

- Retire hypothesis if no stable independent incremental value.
- Reject any implementation that thresholds SE_W without amendment.

### Hipotesis predictiva separada

- ID: `M4-HYP-STRUCTURE-001`.
- Estado: `proposed_unverified`.
- Enunciado: Side-aligned signed path efficiency may condition which barrier is reached first within the same horizon.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 9. M4-RULE-PRIOR-EXTREMA-001

**Nombre:** Extremos observados del horizonte anterior

**Subfase:** M4.3

**Bloques:** 1, 28

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Record prior-H high/low and whether the target-side extreme lies strictly between entry and TP.

### Datos

- {"m3_data_contract_ids":["M3-DATA-001","M3-DATA-005"],"provider":"Binance USD-M and immutable user plan"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"market":"Binance USD-M perpetual","normalized_units":"log_return_or_dimensionless","price_unit":"quote_asset_per_base","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant closed data only; every observation <= analysis_at"}

### Formula exacta

```text
X_high=max(H_i), X_low=min(L_i) over previous exact H
long target extreme=X_high; short target extreme=X_low
between=entry<X_high<TP long; TP<X_low<entry short
```

### Normalizacion entre pares

- Natural-log ratios, path ratios or within-pair empirical ranks.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M4.2-compliant closed history
- same formula and policy for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or invalid data
- insufficient declared history

### Fuentes y afirmacion respaldada

- [OSLER-2000-SUPPORT-RESISTANCE](https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.pdf) [external_empirical_evidence_adjacent_to_project_target]: Published FX levels predicted some intraday trend interruptions with heterogeneous performance.
- [CURCIO-ET-AL-2014-PRICE-MEMORY](https://doi.org/10.1038/srep04487) [family_or_adjacent_foundation]: Local extrema, bounce count and time scale can be studied as price-memory candidates.

### Lo que las fuentes no respaldan

- No source supplies a project score, probability, weight or threshold.
- Evidence from other assets or horizons is not assumed transferable.
- A rolling high/low is not called support or resistance.
- An extreme between entry and TP receives no penalty.

### Relacion esperada con resultados

- Unknown until independently tested; both interruption and breakout continuation remain possible.

### Control de doble conteo

- Replaces support, level and technical-barrier penalties with one extrema descriptor.

### Ausencia de datos

- Rule not evaluated; no synthetic level.

### Pruebas, limites e invariantes

- prior_low<=prior_high
- strict between relation
- long/short mirror handling
- no support/resistance label

### Traza producida

- prior_high
- prior_low
- target_side_extreme
- adverse_side_extreme
- target_extreme_between_entry_and_tp
- target_extreme_log_distance
- barrier_effect

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Retire hypothesis if effect is unstable by pair/horizon.
- A richer bounce detector requires a new rule and source claims.

### Hipotesis predictiva separada

- ID: `M4-HYP-LEVEL-001`.
- Estado: `proposed_unverified`.
- Enunciado: A prior target-side extreme between entry and TP may condition first-passage behavior.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 10. M4-RULE-VOLATILITY-RANK-001

**Nombre:** Percentil continuo de volatilidad

**Subfase:** M4.3

**Bloques:** 24, 26

**Tipo:** `deterministic_context_measure`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Locate current previous-H RV within 60 strictly prior non-overlapping H windows without categorical bands.

### Datos

- {"m3_data_contract_ids":["M3-DATA-005"],"provider":"Binance USD-M and immutable user plan"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"market":"Binance USD-M perpetual","normalized_units":"log_return_or_dimensionless","price_unit":"quote_asset_per_base","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant closed data only; every observation <= analysis_at"}

### Formula exacta

```text
q=(count(RV_j<RV_t)+0.5*count(RV_j=RV_t))/60
j are 60 strictly prior non-overlapping H windows
```

### Normalizacion entre pares

- Natural-log ratios, path ratios or within-pair empirical ranks.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M4.2-compliant closed history
- same formula and policy for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or invalid data
- insufficient declared history

### Fuentes y afirmacion respaldada

- [HAMILTON-1989-REGIME-SWITCHING](https://doi.org/10.2307/1912559) [family_or_adjacent_foundation]: Regimes require a specified estimated state model.
- [CORSI-2009-HAR-RV](https://doi.org/10.1093/jjfinec/nbp001) [family_or_adjacent_foundation]: Volatility contains heterogeneous temporal components.

### Lo que las fuentes no respaldan

- No source supplies a project score, probability, weight or threshold.
- Evidence from other assets or horizons is not assumed transferable.
- Sixty windows is project policy, not a published optimum.
- q is not labelled low, medium or high.

### Relacion esperada con resultados

- Context only; no direct TP-versus-SL direction.

### Control de doble conteo

- Rank is a transformation of M4.2 RV, not independent evidence.

### Ausencia de datos

- Block regime context; retain geometry if otherwise valid.

### Pruebas, limites e invariantes

- 0<=q<=1
- exactly 60 prior windows
- current window excluded from reference
- midrank tie handling

### Traza producida

- current_realized_variance
- reference_window_count
- reference_cutoff
- volatility_percentile
- ranking_method

### Campos prohibidos o reservados a null

- regime_label

### Refutacion, suspension o retirada

- Change reference length only through versioned amendment.
- Retire interaction if no stable conditional value.

### Hipotesis predictiva separada

- ID: `M4-HYP-REGIME-001`.
- Estado: `proposed_unverified_interaction_only`.
- Enunciado: Volatility rank may alter the reliability of structure signals but has no directional effect alone.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 11. M4-RULE-MTF-HIERARCHY-001

**Nombre:** Jerarquia multi-timeframe H, 2H y 4H

**Subfase:** M4.3

**Bloques:** 1, 3, 24

**Tipo:** `deterministic_interaction_descriptor`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Expose structure at the plan horizon and two slower contexts without votes, weights or duplicate penalties.

### Datos

- {"m3_data_contract_ids":["M3-DATA-001","M3-DATA-005"],"provider":"Binance USD-M and immutable user plan"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"market":"Binance USD-M perpetual","normalized_units":"log_return_or_dimensionless","price_unit":"quote_asset_per_base","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant closed data only; every observation <= analysis_at"}

### Formula exacta

```text
calculate SE_W for W in {H,2H,4H} on the same closed grid
sign_W=sign(SE_W)
agreement in {all_positive,all_negative,mixed,flat_present}
```

### Normalizacion entre pares

- Natural-log ratios, path ratios or within-pair empirical ranks.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M4.2-compliant closed history
- same formula and policy for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or invalid data
- insufficient declared history

### Fuentes y afirmacion respaldada

- [CORSI-2009-HAR-RV](https://doi.org/10.1093/jjfinec/nbp001) [family_or_adjacent_foundation]: Different horizons can carry distinct temporal information.
- [HUDSON-URQUHART-2021](https://doi.org/10.1007/s10479-019-03357-1) [transfer_limit_evidence]: Technical-rule effects are asset and sample dependent.

### Lo que las fuentes no respaldan

- No source supplies a project score, probability, weight or threshold.
- Evidence from other assets or horizons is not assumed transferable.
- H/2H/4H is project context policy, not a cited optimum.
- Agreement has no score or automatic direction.

### Relacion esperada con resultados

- Only an interaction candidate; mixed signs are not a penalty.

### Control de doble conteo

- MTF consumes the three SE values once; no trend score plus HTF contradiction penalty.

### Ausencia de datos

- Do not collapse available windows into a partial vote.

### Pruebas, limites e invariantes

- exact windows H,2H,4H
- same sampling grid
- no numeric aggregation
- order and signs preserved

### Traza producida

- window_multipliers
- signed_path_efficiencies
- direction_signs
- agreement_descriptor

### Campos prohibidos o reservados a null

- aggregate_score
- probability_effect

### Refutacion, suspension o retirada

- Retire if no incremental value beyond H structure.
- Any weights require a new documented integration rule.

### Hipotesis predictiva separada

- ID: `M4-HYP-MTF-001`.
- Estado: `proposed_unverified`.
- Enunciado: Sign agreement across H, 2H and 4H may condition first-passage behavior beyond H structure alone.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 12. M4-RULE-CONTINUOUS-REGIME-001

**Nombre:** Vector continuo de regimen

**Subfase:** M4.3

**Bloques:** 24

**Tipo:** `context_vector_no_label`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Represent current state by volatility percentile and signed path efficiency without arbitrary regime names.

### Datos

- {"m3_data_contract_ids":["M3-DATA-005"],"provider":"Binance USD-M and immutable user plan"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"market":"Binance USD-M perpetual","normalized_units":"log_return_or_dimensionless","price_unit":"quote_asset_per_base","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant closed data only; every observation <= analysis_at"}

### Formula exacta

```text
R_t=(q_RV,t, SE_H,t)
```

### Normalizacion entre pares

- Natural-log ratios, path ratios or within-pair empirical ranks.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M4.2-compliant closed history
- same formula and policy for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or invalid data
- insufficient declared history

### Fuentes y afirmacion respaldada

- [HAMILTON-1989-REGIME-SWITCHING](https://doi.org/10.2307/1912559) [transfer_limit_evidence]: A genuine latent regime requires model estimation; this rule therefore remains an observed state vector.

### Lo que las fuentes no respaldan

- No source supplies a project score, probability, weight or threshold.
- Evidence from other assets or horizons is not assumed transferable.
- The vector is not a Markov regime model.
- No low/high or bull/bear labels are assigned.

### Relacion esperada con resultados

- Unknown interaction; no marginal directional effect.

### Control de doble conteo

- Vector references its atomic inputs; it does not add evidence.

### Ausencia de datos

- Vector unavailable if either component is unavailable.

### Pruebas, limites e invariantes

- q_RV in [0,1]
- SE_H in [-1,1]
- regime_label is null
- directional_score is null

### Traza producida

- volatility_percentile
- signed_path_efficiency

### Campos prohibidos o reservados a null

- regime_label
- directional_score
- probability_effect

### Refutacion, suspension o retirada

- A categorical or latent regime requires a separate model card.
- Retire interaction if M8 finds no stable conditional effect.

### Hipotesis predictiva separada

- ID: `M4-HYP-REGIME-002`.
- Estado: `proposed_unverified_interaction_only`.
- Enunciado: The interaction of q_RV and SE_H may identify conditions where directional structure behaves differently.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 13. M4-RULE-AGGRESSOR-IMBALANCE-001

**Nombre:** Desequilibrio de operaciones agresoras ejecutadas

**Subfase:** M4.4

**Bloques:** 7

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Measure buyer-taker versus seller-taker executed volume over one exact window without calling it full order flow.

### Datos

- {"m3_data_contract_ids":["M3-DATA-005","M3-DATA-007","M3-DATA-015"],"provider":"Binance USD-M"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"markets":["Binance USD-M perpetual"],"normalized_units":"log_ratio_or_dimensionless_ratio","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant data only; exact windows end at or before analysis_at"}

### Formula exacta

```text
B_H=sum(p_i*q_i where buyer_is_maker=false)
S_H=sum(p_i*q_i where buyer_is_maker=true)
ATI_H=(B_H-S_H)/(B_H+S_H)
periodic alternative=(sum(buyVol)-sum(sellVol))/total
```

### Normalizacion entre pares

- Natural-log changes and bounded ratios; raw activity is not compared across pairs.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M3-compliant observations
- exact horizon or explicitly identified current snapshot
- same formula for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or incomplete data
- provider retention cannot cover the exact window

### Fuentes y afirmacion respaldada

- [BINANCE-USD-M-MARKET-DATA](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) [provider_semantics]: Trade side, price, quantity and taker volumes.
- [CONT-KUKANOV-STOIKOV-2014](https://doi.org/10.1093/jjfinec/nbt003) [transfer_limit_evidence]: Trade imbalance is weaker than full order-book event imbalance in the studied equity data.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, threshold or weight.
- Evidence from another asset, venue or horizon is not transferred.
- ATI_H is not OFI or CVD.
- Limit orders and cancellations are absent.
- Event and periodic measures cannot be added or averaged.

### Relacion esperada con resultados

- Unknown; no direct TP/SL effect.

### Control de doble conteo

- aggTrades, taker endpoint and kline taker volume are alternative measurements of one evidence family.

### Ausencia de datos

- Rule unavailable; no zero or neutral imbalance.

### Pruebas, limites e invariantes

- -1<=ATI_H<=1
- exact complete window
- buyer-maker means seller taker
- source alternatives are not averaged

### Traza producida

- window_start_ms
- window_end_ms
- coverage_start_ms
- coverage_end_ms
- ati_source
- activity_unit
- aggregation_method
- source_retention_status
- buy_taker_volume
- sell_taker_volume
- total_activity
- ATI_H
- coverage_complete

### Campos prohibidos o reservados a null

- prediction

### Refutacion, suspension o retirada

- Retire if no stable incremental value after full controls.
- A true OFI rule requires book-event capture and a new card.

### Hipotesis predictiva separada

- ID: `M4-HYP-FLOW-001`.
- Estado: `proposed_unverified`.
- Enunciado: Side-aligned ATI_H may condition first-barrier behavior after controlling for path, volatility and activity.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 14. M4-RULE-OPEN-INTEREST-CHANGE-001

**Nombre:** Cambio logaritmico de open interest

**Subfase:** M4.4

**Bloques:** 9

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Measure the change in outstanding contract quantity over the same exact horizon without inferring long/short direction.

### Datos

- {"m3_data_contract_ids":["M3-DATA-013","M3-DATA-014"],"provider":"Binance USD-M"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"markets":["Binance USD-M perpetual"],"normalized_units":"log_ratio_or_dimensionless_ratio","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant data only; exact windows end at or before analysis_at"}

### Formula exacta

```text
dOI_H=ln(OI_t/OI_(t-H))
current_timestamp_ms-previous_timestamp_ms=H*1000
```

### Normalizacion entre pares

- Natural-log changes and bounded ratios; raw activity is not compared across pairs.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M3-compliant observations
- exact horizon or explicitly identified current snapshot
- same formula for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or incomplete data
- provider retention cannot cover the exact window

### Fuentes y afirmacion respaldada

- [BINANCE-USD-M-MARKET-DATA](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) [provider_semantics]: Current and historical total open interest.
- [HONG-YOGO-2012](https://doi.org/10.1016/j.jfineco.2011.05.008) [external_empirical_evidence_adjacent_to_project_target]: OI changes carried information in traditional futures samples.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, threshold or weight.
- Evidence from another asset, venue or horizon is not transferred.
- Gross OI does not identify net long or net short pressure.
- OI value is not substituted for contract quantity.

### Relacion esperada con resultados

- Context only; no standalone direction.

### Control de doble conteo

- Current OI and historical OI form one endpoint change.

### Ausencia de datos

- Rule unavailable; no assumed unchanged OI.

### Pruebas, limites e invariantes

- OI_t>0 and OI_(t-H)>0
- exact endpoint separation H
- dimensionless log change
- long_short_direction is null

### Traza producida

- previous_timestamp_ms
- current_timestamp_ms
- horizon_seconds
- actual_separation_seconds
- alignment_error_seconds
- previous_open_interest
- current_open_interest
- dOI_H
- long_short_direction

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Retire hypothesis if unstable by pair or horizon.
- Reject any implementation that labels OI rise as longs.

### Hipotesis predictiva separada

- ID: `M4-HYP-OI-001`.
- Estado: `proposed_unverified_interaction_only`.
- Enunciado: dOI_H may alter the conditional value of price-path and aggressor-flow observations.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 15. M4-RULE-PRICE-OI-STATE-001

**Nombre:** Estado conjunto precio y open interest

**Subfase:** M4.4

**Bloques:** 1, 9

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Preserve the joint continuous state (D_H,dOI_H) without legacy quadrant narratives or duplicate points.

### Datos

- {"m3_data_contract_ids":["M3-DATA-005","M3-DATA-013","M3-DATA-014"],"provider":"Binance USD-M"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"markets":["Binance USD-M perpetual"],"normalized_units":"log_ratio_or_dimensionless_ratio","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant data only; exact windows end at or before analysis_at"}

### Formula exacta

```text
POI_H=(D_H,dOI_H)
```

### Normalizacion entre pares

- Natural-log changes and bounded ratios; raw activity is not compared across pairs.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M3-compliant observations
- exact horizon or explicitly identified current snapshot
- same formula for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or incomplete data
- provider retention cannot cover the exact window

### Fuentes y afirmacion respaldada

- [HONG-YOGO-2012](https://doi.org/10.1016/j.jfineco.2011.05.008) [transfer_limit_evidence]: OI may contain information beyond futures price.
- `M4.3-STRUCTURE` [internal_project_contract]: D_H is the exact-H log price displacement.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, threshold or weight.
- Evidence from another asset, venue or horizon is not transferred.
- No quadrant means new longs, new shorts, covering or exit.
- The vector adds no evidence beyond its components.

### Relacion esperada con resultados

- Unknown interaction; no quadrant score.

### Control de doble conteo

- References D_H and dOI_H; cannot be added as a third signal.

### Ausencia de datos

- Vector unavailable if either component is unavailable.

### Pruebas, limites e invariantes

- continuous values preserved
- positioning_label is null
- aggregate_score is null

### Traza producida

- D_H
- dOI_H
- price_sign
- oi_sign
- state_descriptor

### Campos prohibidos o reservados a null

- positioning_label
- probability_effect

### Refutacion, suspension o retirada

- Retire interaction if no incremental conditional value.
- Any semantic quadrant requires separately verified evidence.

### Hipotesis predictiva separada

- ID: `M4-HYP-PRICE-OI-001`.
- Estado: `proposed_unverified_interaction_only`.
- Enunciado: The joint continuous state may condition first-passage behavior beyond price displacement alone.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 16. M4-RULE-SPOT-FUTURES-BASIS-001

**Nombre:** Intervalo observable spot-Futures

**Subfase:** M4.4

**Bloques:** 15

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Measure receive-time-bounded midpoint and executable quote ratios between Binance Spot and USD-M perpetual.

### Datos

- {"m3_data_contract_ids":["M3-DATA-008","M3-DATA-016","M3-DATA-017"],"provider":"Binance USD-M and Binance Spot"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"markets":["Binance USD-M perpetual","Binance Spot"],"normalized_units":"log_ratio_or_dimensionless_ratio","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant receive times only; cross-venue receive-time skew is bounded by a provisional project policy"}

### Formula exacta

```text
mid_F=(F_bid+F_ask)/2; mid_S=(S_bid+S_ask)/2
b_mid=ln(mid_F/mid_S)
b_sellF_buyS=ln(F_bid/S_ask)
b_buyF_sellS=ln(F_ask/S_bid)
```

### Normalizacion entre pares

- Natural-log changes and bounded ratios; raw activity is not compared across pairs.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M3-compliant observations
- exact horizon or explicitly identified current snapshot
- same formula for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or incomplete data
- provider retention cannot cover the exact window

### Fuentes y afirmacion respaldada

- [BINANCE-SPOT-MARKET-DATA](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market) [provider_semantics]: Spot best bid and ask.
- [BAUR-DIMPFL-2019](https://doi.org/10.1002/fut.22004) [external_empirical_evidence_adjacent_to_project_target]: Spot led futures in their Bitcoin sample.
- [FRINO-ET-AL-2025](https://doi.org/10.1002/fut.22560) [external_empirical_evidence_adjacent_to_project_target]: Futures generally led spot in a later sample, with daily variation.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, threshold or weight.
- Evidence from another asset, venue or horizon is not transferred.
- No market is assigned permanent price leadership.
- The raw interval excludes fees, latency and fill uncertainty.

### Relacion esperada con resultados

- Unknown; no automatic convergence direction.

### Control de doble conteo

- Midpoint and executable bounds are one basis observation.

### Ausencia de datos

- Block basis; mark-index premium is not a silent substitute.

### Pruebas, limites e invariantes

- bid<=ask on both venues
- capture skew<=2000ms
- capture times are local receive times, not synchronized market times
- log ratios are scale invariant
- price_leadership is null

### Traza producida

- four_quotes
- futures_received_at_ms
- spot_received_at_ms
- capture_skew_ms
- capture_time_basis
- market_timestamp_synchronized
- basis_capture_uncertainty_status
- capture_limit_status
- b_mid
- executable_basis_bounds
- fees_included

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Retire if capture uncertainty dominates observed basis.
- Price leadership requires a separate time-series model.

### Hipotesis predictiva separada

- ID: `M4-HYP-BASIS-001`.
- Estado: `proposed_unverified_interaction_only`.
- Enunciado: Basis magnitude and sign may condition price discovery when combined with flow, OI and freshness.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 17. M4-RULE-MARK-INDEX-PREMIUM-001

**Nombre:** Prima sincronizada mark-index

**Subfase:** M4.4

**Bloques:** 10, 15

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Measure the same-timestamp USD-M mark-to-index log ratio without presenting the index as Binance Spot.

### Datos

- {"m3_data_contract_ids":["M3-DATA-010"],"provider":"Binance USD-M"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"markets":["Binance USD-M perpetual"],"normalized_units":"log_ratio_or_dimensionless_ratio","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant data only; exact windows end at or before analysis_at"}

### Formula exacta

```text
b_mark_index=ln(markPrice/indexPrice)
```

### Normalizacion entre pares

- Natural-log changes and bounded ratios; raw activity is not compared across pairs.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M3-compliant observations
- exact horizon or explicitly identified current snapshot
- same formula for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or incomplete data
- provider retention cannot cover the exact window

### Fuentes y afirmacion respaldada

- [BINANCE-USD-M-MARKET-DATA](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) [provider_semantics]: Mark price, index price and provider time.
- [HE-MANELA-ROSS-VON-WACHTER-2022](https://arxiv.org/abs/2212.06888) [family_or_adjacent_foundation]: Perpetual prices can deviate from spot anchors.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, threshold or weight.
- Evidence from another asset, venue or horizon is not transferred.
- Index price is not Binance Spot bookTicker.
- Premium sign is not a return forecast.

### Relacion esperada con resultados

- Context only; no convergence assumption.

### Control de doble conteo

- Cross-venue basis and mark-index premium share one family and cannot both receive independent effects.

### Ausencia de datos

- Rule unavailable; no zero premium.

### Pruebas, limites e invariantes

- markPrice>0 and indexPrice>0
- same provider timestamp
- binance_spot_basis is null

### Traza producida

- provider_time
- mark_price
- index_price
- mark_index_log_premium
- binance_spot_basis

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Retire hypothesis if it adds no value beyond actual basis.

### Hipotesis predictiva separada

- ID: `M4-HYP-PREMIUM-001`.
- Estado: `proposed_unverified_interaction_only`.
- Enunciado: The synchronized mark-index premium may improve basis context when cross-venue capture is noisy.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 18. M4-RULE-FUNDING-STATE-001

**Nombre:** Estado temporal y carga realizada de funding

**Subfase:** M4.4

**Bloques:** 10

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Normalize the current rate by its configured interval and record realized prior-H funding without forecasting rates.

### Datos

- {"m3_data_contract_ids":["M3-DATA-010","M3-DATA-011","M3-DATA-012"],"provider":"Binance USD-M"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"markets":["Binance USD-M perpetual"],"normalized_units":"log_ratio_or_dimensionless_ratio","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant data only; exact windows end at or before analysis_at"}

### Formula exacta

```text
linearized_f_last_hour=lastFundingRate/fundingIntervalHours
L_prev(H)=sum(f_j where t-H<fundingTime_j<=t)
L_prev_hour(H)=L_prev(H)/H_hours
N_schedule=count configured event times within future H
```

### Normalizacion entre pares

- Natural-log changes and bounded ratios; raw activity is not compared across pairs.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M3-compliant observations
- exact horizon or explicitly identified current snapshot
- same formula for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or incomplete data
- provider retention cannot cover the exact window

### Fuentes y afirmacion respaldada

- [BINANCE-USD-M-MARKET-DATA](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) [provider_semantics]: Funding rate, funding time, next time and adjusted interval configuration.
- [HE-MANELA-ROSS-VON-WACHTER-2022](https://arxiv.org/abs/2212.06888) [family_or_adjacent_foundation]: Funding is an anchoring cash-flow mechanism.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, threshold or weight.
- Evidence from another asset, venue or horizon is not transferred.
- Last observed funding is not the next funding rate.
- Historical average is not a future rate.
- Scheduled events do not imply a projected funding cost.

### Relacion esperada con resultados

- No direct TP/SL effect; economic cost is M4.5.

### Control de doble conteo

- Current, normalized and historical funding describe one funding family.

### Ausencia de datos

- Funding context unavailable; never assume zero.

### Pruebas, limites e invariantes

- fundingIntervalHours>0
- funding events ordered and <=analysis_at
- future_funding_rate_assumption is null
- projected_funding_cost is null

### Traza producida

- last_funding_rate
- interval_hours
- linearized_last_funding_rate_per_hour
- next_funding_time
- scheduled_events_under_current_config
- previous_horizon_funding_load
- projected_funding_cost

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Retire interaction if no stable independent value.
- Projected cost requires M4.5 execution assumptions.

### Hipotesis predictiva separada

- ID: `M4-HYP-FUNDING-001`.
- Estado: `proposed_unverified_interaction_only`.
- Enunciado: Funding state may condition basis and positioning interactions but has no standalone price direction.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 19. M4-RULE-DERIVATIVES-CONTEXT-001

**Nombre:** Vector continuo de contexto de derivados

**Subfase:** M4.4

**Bloques:** 7, 9, 10, 15

**Tipo:** `deterministic_measure_with_separate_hypothesis`

**Estado:** `documented_candidate_no_predictive_weight`

### Objetivo

Expose flow, OI, basis and funding jointly without crowding labels, votes or additive scores.

### Datos

- {"m3_data_contract_ids":["M3-DATA-007","M3-DATA-008","M3-DATA-010","M3-DATA-012","M3-DATA-014","M3-DATA-016","M3-DATA-017"],"provider":"Binance USD-M"}

### Tiempo, unidades y frescura

- {"horizons":["intraday_short","intraday_wide","short_swing"],"markets":["Binance USD-M perpetual"],"normalized_units":"log_ratio_or_dimensionless_ratio","symbols":["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","INJUSDT"],"time_rule":"M3-compliant data only; exact windows end at or before analysis_at"}

### Formula exacta

```text
DC_H=(ATI_H,dOI_H,b_mid,linearized_f_last_hour)
```

### Normalizacion entre pares

- Natural-log changes and bounded ratios; raw activity is not compared across pairs.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- complete M3-compliant observations
- exact horizon or explicitly identified current snapshot
- same formula for every supported pair

### No aplicacion o bloqueo

- missing, stale, future, gapped or incomplete data
- provider retention cannot cover the exact window

### Fuentes y afirmacion respaldada

- `M4.3-STRUCTURE` [internal_project_contract]: Interaction vectors reference atomic components without adding them as separate evidence.
- `M3-DATA-CONTRACTS` [internal_project_contract]: Every component has a separate data contract.

### Lo que las fuentes no respaldan

- No source supplies a project probability, score, threshold or weight.
- Evidence from another asset, venue or horizon is not transferred.
- The vector is not a crowding index.
- No component has a numeric coefficient.

### Relacion esperada con resultados

- Unknown interaction; no direct probability.

### Control de doble conteo

- The vector references four atomic families and adds no fifth piece of evidence.

### Ausencia de datos

- Vector unavailable if any required component is absent.

### Pruebas, limites e invariantes

- ATI_H in [-1,1]
- all components continuous
- crowding_label is null
- aggregate_score is null

### Traza producida

- ATI_H
- dOI_H
- b_mid
- linearized_f_last_hour

### Campos prohibidos o reservados a null

- crowding_label
- aggregate_score
- probability_effect

### Refutacion, suspension o retirada

- Retire interaction if no incremental validated value.
- Any coefficient requires M6 and independent validation.

### Hipotesis predictiva separada

- ID: `M4-HYP-DERIVATIVES-001`.
- Estado: `proposed_unverified_interaction_only`.
- Enunciado: Joint derivatives state may contain conditional value not present in any marginal observation.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 20. M4-RULE-QUOTED-SPREAD-001

**Nombre:** Spread cotizado en el instante de llegada

**Subfase:** M4.5

**Bloques:** 29

**Tipo:** `deterministic_economic_operator`

**Estado:** `formal_documented_operator_not_implemented_in_production`

### Objetivo

Descriptor actual de coste cotizado; no penalizacion.

### Datos

- best_bid>0
- best_ask>=best_bid
- receive_time

### Tiempo, unidades y frescura

- symbol must belong to the six-pair scope
- timestamps and freshness follow the referenced M3 contracts
- price and money use quote asset; quantity uses base asset
- rates and fractions are dimensionless unless explicitly stated

### Formula exacta

```text
mid=(best_bid+best_ask)/2
spread_quote=best_ask-best_bid
spread_fraction_mid=spread_quote/mid
```

### Normalizacion entre pares

- Dimensionless ratios remain comparable; quote-money outputs are never compared across pairs without explicit normalization.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- all declared inputs are present and valid
- the operator belongs to the applicable execution, exposure or economic branch

### No aplicacion o bloqueo

- Libro cruzado, dato no positivo o timestamp ausente.

### Fuentes y afirmacion respaldada

- [BINANCE-USD-M-MARKET-DATA](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) [provider_semantics]: Bid y ask son observables oficiales del mercado.
- [FINRA-INSTITUTIONAL-ORDER-HANDLING-2019](https://www.finra.org/sites/default/files/OCE_WP_jan2019.pdf) [family_or_adjacent_foundation]: El midpoint de llegada es referencia de ejecucion.

### Lo que las fuentes no respaldan

- Que un spread concreto prediga TP o SL.
- Que el spread actual sea el spread de salida futuro.

### Relacion esperada con resultados

- No direct market-probability relation is authorized. The output describes execution, exposure or payoff after market outcomes.

### Control de doble conteo

- Use the canonical M4.6 slot for this family; derived values, containers and overlapping costs are not additional votes.

### Ausencia de datos

- Block the unavailable result and expose the missing component; do not use a neutral value or universal constant.

### Pruebas, limites e invariantes

- Snapshot actual; puede cambiar antes de ejecutar.
- long/short signs must follow the declared direction
- no execution or exposure value may change market probability

### Traza producida

- rule id and version
- input values and units
- provider/receive timestamps when market data is used
- formula branch, output and availability status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Libro cruzado, dato no positivo o timestamp ausente.
- Suspend if provider semantics or units no longer match the documented contract.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 21. M4-RULE-DEPTH-SWEEP-001

**Nombre:** Barrido visible e implementation shortfall

**Subfase:** M4.5

**Bloques:** 29

**Tipo:** `deterministic_economic_operator`

**Estado:** `formal_documented_operator_not_implemented_in_production`

### Objetivo

VWAP y shortfall del tramo llenado siempre que exista fill; coste completo solo si fill_ratio=1.

### Datos

- side buy|sell
- base_quantity>0
- bids descendentes
- asks ascendentes
- arrival midpoint

### Tiempo, unidades y frescura

- symbol must belong to the six-pair scope
- timestamps and freshness follow the referenced M3 contracts
- price and money use quote asset; quantity uses base asset
- rates and fractions are dimensionless unless explicitly stated

### Formula exacta

```text
buy consume asks; sell consume bids
VWAP_filled=sum(price_i*filled_qty_i)/filled_qty
D=+1 buy, -1 sell
IS_filled_quote=D*(sum(price_i*filled_qty_i)-arrival_mid*filled_qty)
IS_filled_fraction=IS_filled_quote/(arrival_mid*filled_qty)
complete_VWAP=VWAP_filled iff filled_qty=requested_qty
fill_ratio=filled_qty/requested_qty
```

### Normalizacion entre pares

- Dimensionless ratios remain comparable; quote-money outputs are never compared across pairs without explicit normalization.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- all declared inputs are present and valid
- the operator belongs to the applicable execution, exposure or economic branch

### No aplicacion o bloqueo

- Fill ratio menor que uno bloquea el coste completo.
- Orden o niveles invalidos bloquean.

### Fuentes y afirmacion respaldada

- [FINRA-INSTITUTIONAL-ORDER-HANDLING-2019](https://www.finra.org/sites/default/files/OCE_WP_jan2019.pdf) [family_or_adjacent_foundation]: VWAP firmado contra midpoint mide shortfall.
- [ALMGREN-CHRISS-2001](https://doi.org/10.21314/JOR.2001.041) [family_or_adjacent_foundation]: Coste e impacto pertenecen al problema de ejecucion.

### Lo que las fuentes no respaldan

- Impacto permanente exacto.
- Slippage de una salida futura.
- Minimo universal de 0.02%.

### Relacion esperada con resultados

- No direct market-probability relation is authorized. The output describes execution, exposure or payoff after market outcomes.

### Control de doble conteo

- Use the canonical M4.6 slot for this family; derived values, containers and overlapping costs are not additional votes.

### Ausencia de datos

- Block the unavailable result and expose the missing component; do not use a neutral value or universal constant.

### Pruebas, limites e invariantes

- Solo profundidad visible solicitada.
- No garantiza fills ni incorpora latencia o cola.
- El coste del tramo llenado no representa el coste de la cantidad no llenada.
- El IS desde midpoint ya contiene medio spread y barrido; no se suma de nuevo el spread.
- long/short signs must follow the declared direction
- no execution or exposure value may change market probability

### Traza producida

- rule id and version
- input values and units
- provider/receive timestamps when market data is used
- formula branch, output and availability status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Fill ratio menor que uno bloquea el coste completo.
- Orden o niveles invalidos bloquean.
- Suspend if provider semantics or units no longer match the documented contract.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 22. M4-RULE-FEE-SCENARIOS-001

**Nombre:** Comision por rol de liquidez autenticado

**Subfase:** M4.5

**Bloques:** 29

**Tipo:** `deterministic_economic_operator`

**Estado:** `formal_documented_operator_not_implemented_in_production`

### Objetivo

Coste observado exacto tras ejecucion o escenario pre-trade puntual/acotado.

### Datos

- notional>=0
- allowed_roles subset maker|taker|rpi
- authenticated commission rates
- observed_execution flag
- fee_asset required for observed exact cost

### Tiempo, unidades y frescura

- symbol must belong to the six-pair scope
- timestamps and freshness follow the referenced M3 contracts
- price and money use quote asset; quantity uses base asset
- rates and fractions are dimensionless unless explicitly stated

### Formula exacta

```text
fee(role)=notional*commission_rate(role)
lower=min(fee(role)); upper=max(fee(role))
pretrade one-role input is a scenario point, not an observation
exact iff execution is observed, role is unique, notional is executed and fee_asset is known
```

### Normalizacion entre pares

- Dimensionless ratios remain comparable; quote-money outputs are never compared across pairs without explicit normalization.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- all declared inputs are present and valid
- the operator belongs to the applicable execution, exposure or economic branch

### No aplicacion o bloqueo

- Sin autenticacion o tasa requerida, el coste exacto bloquea.

### Fuentes y afirmacion respaldada

- [BINANCE-USD-M-ACCOUNT](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account) [provider_semantics]: La cuenta expone tasas maker, taker y RPI.

### Lo que las fuentes no respaldan

- Comision universal de ida y vuelta de 0.08%.
- Rol de liquidez de una salida futura desconocida.

### Relacion esperada con resultados

- No direct market-probability relation is authorized. The output describes execution, exposure or payoff after market outcomes.

### Control de doble conteo

- Use the canonical M4.6 slot for this family; derived values, containers and overlapping costs are not additional votes.

### Ausencia de datos

- Block the unavailable result and expose the missing component; do not use a neutral value or universal constant.

### Pruebas, limites e invariantes

- RPI solo entra cuando el tipo de orden lo permite.
- Cada tramo y resultado usa su propio notional y rol.
- El basis bruto no se netea con comisiones; ambos conservan campos y unidades separados.
- long/short signs must follow the declared direction
- no execution or exposure value may change market probability

### Traza producida

- rule id and version
- input values and units
- provider/receive timestamps when market data is used
- formula branch, output and availability status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Sin autenticacion o tasa requerida, el coste exacto bloquea.
- Suspend if provider semantics or units no longer match the documented contract.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 23. M4-RULE-FUNDING-CASHFLOW-001

**Nombre:** Flujo monetario firmado de funding

**Subfase:** M4.5

**Bloques:** 10, 29

**Tipo:** `deterministic_economic_operator`

**Estado:** `formal_documented_operator_not_implemented_in_production`

### Objetivo

Flujo firmado para eventos realizados o escenarios explicitos.

### Datos

- side long|short
- base_quantity>0
- event mark_price>0
- event funding_rate signed

### Tiempo, unidades y frescura

- symbol must belong to the six-pair scope
- timestamps and freshness follow the referenced M3 contracts
- price and money use quote asset; quantity uses base asset
- rates and fractions are dimensionless unless explicitly stated

### Formula exacta

```text
position_sign=+1 long, -1 short
cashflow_event=-position_sign*quantity*mark_price*rate
cashflow_total=sum(cashflow_event)
```

### Normalizacion entre pares

- Dimensionless ratios remain comparable; quote-money outputs are never compared across pairs without explicit normalization.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- all declared inputs are present and valid
- the operator belongs to the applicable execution, exposure or economic branch

### No aplicacion o bloqueo

- Eventos futuros desconocidos bloquean el funding exacto.

### Fuentes y afirmacion respaldada

- [HE-MANELA-ROSS-VON-WACHTER-2022](https://arxiv.org/abs/2212.06888) [family_or_adjacent_foundation]: Funding positivo transfiere de largos a cortos.
- `M4.4-DERIVATIVES` [internal_project_contract]: La ultima tasa observada no es una tasa futura.

### Lo que las fuentes no respaldan

- Usar abs(rate) una vez como coste para ambas direcciones.
- Proyectar la ultima tasa durante todo el horizonte.

### Relacion esperada con resultados

- No direct market-probability relation is authorized. The output describes execution, exposure or payoff after market outcomes.

### Control de doble conteo

- Use the canonical M4.6 slot for this family; derived values, containers and overlapping costs are not additional votes.

### Ausencia de datos

- Block the unavailable result and expose the missing component; do not use a neutral value or universal constant.

### Pruebas, limites e invariantes

- Antes del cierre solo admite escenarios, no forecast exacto.
- long/short signs must follow the declared direction
- no execution or exposure value may change market probability

### Traza producida

- rule id and version
- input values and units
- provider/receive timestamps when market data is used
- formula branch, output and availability status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Eventos futuros desconocidos bloquean el funding exacto.
- Suspend if provider semantics or units no longer match the documented contract.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 24. M4-RULE-PLAN-EXPOSURE-001

**Nombre:** Exposicion monetaria lineal del plan

**Subfase:** M4.5

**Bloques:** 30

**Tipo:** `deterministic_economic_operator`

**Estado:** `formal_documented_operator_not_implemented_in_production`

### Objetivo

Exposicion, recompensa y perdida brutas; sin score ni probabilidad.

### Datos

- side
- entry, TP, SL
- margin>0
- leverage>0

### Tiempo, unidades y frescura

- symbol must belong to the six-pair scope
- timestamps and freshness follow the referenced M3 contracts
- price and money use quote asset; quantity uses base asset
- rates and fractions are dimensionless unless explicitly stated

### Formula exacta

```text
notional=margin*leverage
quantity=notional/entry
gross_pnl(P)=direction*quantity*(P-entry)
gross_reward=gross_pnl(TP)
gross_risk=-gross_pnl(SL)
gross_RR=gross_reward/gross_risk
risk_fraction_margin=gross_risk/margin
```

### Normalizacion entre pares

- Dimensionless ratios remain comparable; quote-money outputs are never compared across pairs without explicit normalization.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- all declared inputs are present and valid
- the operator belongs to the applicable execution, exposure or economic branch

### No aplicacion o bloqueo

- Geometria direccional invalida o entrada/margen/leverage no positivos.

### Fuentes y afirmacion respaldada

- `M2-SEMANTICS` [internal_project_contract]: La geometria valida depende de la direccion.
- [INVESTOR-GOV-LEVERAGED-INVESTING](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/leveraged-investing-strategies-know-risks-using-these-advanced-investment-tools) [family_or_adjacent_foundation]: El apalancamiento amplifica ganancias y perdidas.
- `M3-DATA-CONTRACTS` [internal_project_contract]: Margen y apalancamiento pertenecen al plan de usuario.

### Lo que las fuentes no respaldan

- Que el apalancamiento altere la probabilidad de mercado.
- RR minimo 3 o distancias 0.25%/3% como universales.
- Precio de liquidacion exacto.

### Relacion esperada con resultados

- No direct market-probability relation is authorized. The output describes execution, exposure or payoff after market outcomes.

### Control de doble conteo

- Use the canonical M4.6 slot for this family; derived values, containers and overlapping costs are not additional votes.

### Ausencia de datos

- Block the unavailable result and expose the missing component; do not use a neutral value or universal constant.

### Pruebas, limites e invariantes

- Modelo lineal USD-M bruto, antes de costes.
- No incluye equity, margin mode ni maintenance brackets.
- long/short signs must follow the declared direction
- no execution or exposure value may change market probability

### Traza producida

- rule id and version
- input values and units
- provider/receive timestamps when market data is used
- formula branch, output and availability status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Geometria direccional invalida o entrada/margen/leverage no positivos.
- Suspend if provider semantics or units no longer match the documented contract.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 25. M4-RULE-NET-PAYOFFS-001

**Nombre:** Vector monetario neto por resultado

**Subfase:** M4.5

**Bloques:** 32

**Tipo:** `deterministic_economic_operator`

**Estado:** `formal_documented_operator_not_implemented_in_production`

### Objetivo

Payoff neto separado para TP, SL, expiry y no-entry.

### Datos

- gross_price_pnl by outcome
- fee_cost by outcome
- execution_shortfall_cost by outcome
- signed funding_cashflow by outcome

### Tiempo, unidades y frescura

- symbol must belong to the six-pair scope
- timestamps and freshness follow the referenced M3 contracts
- price and money use quote asset; quantity uses base asset
- rates and fractions are dimensionless unless explicitly stated

### Formula exacta

```text
net_payoff_k=gross_price_pnl_k-fee_k-IS_cost_k+funding_k
no_entry direct trading cashflow=0
```

### Normalizacion entre pares

- Dimensionless ratios remain comparable; quote-money outputs are never compared across pairs without explicit normalization.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- all declared inputs are present and valid
- the operator belongs to the applicable execution, exposure or economic branch

### No aplicacion o bloqueo

- Payoff exacto bloqueado por cualquier componente desconocido.

### Fuentes y afirmacion respaldada

- `M2-SEMANTICS` [internal_project_contract]: Cada rama pre-trade es un resultado distinto.
- [FINRA-INSTITUTIONAL-ORDER-HANDLING-2019](https://www.finra.org/sites/default/files/OCE_WP_jan2019.pdf) [family_or_adjacent_foundation]: La ejecucion aporta coste y falta de fill observables.

### Lo que las fuentes no respaldan

- Un unico coste restado a todas las ramas.
- Incluir opportunity cost no modelado en no-entry.

### Relacion esperada con resultados

- No direct market-probability relation is authorized. The output describes execution, exposure or payoff after market outcomes.

### Control de doble conteo

- Use the canonical M4.6 slot for this family; derived values, containers and overlapping costs are not additional votes.

### Ausencia de datos

- Block the unavailable result and expose the missing component; do not use a neutral value or universal constant.

### Pruebas, limites e invariantes

- Si un coste de una rama falta, esa rama queda incompleta.
- long/short signs must follow the declared direction
- no execution or exposure value may change market probability

### Traza producida

- rule id and version
- input values and units
- provider/receive timestamps when market data is used
- formula branch, output and availability status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Payoff exacto bloqueado por cualquier componente desconocido.
- Suspend if provider semantics or units no longer match the documented contract.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 26. M4-RULE-EXPECTED-VALUE-001

**Nombre:** Identidad de valor esperado por resultados

**Subfase:** M4.5

**Bloques:** 32

**Tipo:** `deterministic_economic_operator`

**Estado:** `formal_documented_operator_not_implemented_in_production`

### Objetivo

Valor esperado monetario, solo cuando todos los datos existen.

### Datos

- coherent probabilities p_k
- complete net payoff y_k for identical outcomes

### Tiempo, unidades y frescura

- symbol must belong to the six-pair scope
- timestamps and freshness follow the referenced M3 contracts
- price and money use quote asset; quantity uses base asset
- rates and fractions are dimensionless unless explicitly stated

### Formula exacta

```text
0<=p_k<=1
sum(p_k)=1
EV=sum(p_k*y_k)
```

### Normalizacion entre pares

- Dimensionless ratios remain comparable; quote-money outputs are never compared across pairs without explicit normalization.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- all declared inputs are present and valid
- the operator belongs to the applicable execution, exposure or economic branch

### No aplicacion o bloqueo

- Claves distintas, probabilidades que no suman uno o payoff incompleto.

### Fuentes y afirmacion respaldada

- `M2-SEMANTICS` [internal_project_contract]: Las probabilidades y payoffs deben compartir resultados.

### Lo que las fuentes no respaldan

- El EV actual calculado con TP% y SL% no calibrados.
- Una decision automatica basada solo en EV.

### Relacion esperada con resultados

- No direct market-probability relation is authorized. The output describes execution, exposure or payoff after market outcomes.

### Control de doble conteo

- Use the canonical M4.6 slot for this family; derived values, containers and overlapping costs are not additional votes.

### Ausencia de datos

- Block the unavailable result and expose the missing component; do not use a neutral value or universal constant.

### Pruebas, limites e invariantes

- Probabilidades coherentes no existiran antes de M6.
- Costes futuros incompletos impiden un EV exacto.
- long/short signs must follow the declared direction
- no execution or exposure value may change market probability

### Traza producida

- rule id and version
- input values and units
- provider/receive timestamps when market data is used
- formula branch, output and availability status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Claves distintas, probabilidades que no suman uno o payoff incompleto.
- Suspend if provider semantics or units no longer match the documented contract.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## 27. M4-RULE-EVALUATION-READINESS-001

**Nombre:** Estado explicito de disponibilidad economica

**Subfase:** M4.5

**Bloques:** 30, 32

**Tipo:** `deterministic_economic_operator`

**Estado:** `formal_documented_operator_not_implemented_in_production`

### Objetivo

Estados y faltantes; nunca score, grade o recomendacion.

### Datos

- status market probabilities
- status entry and exit execution
- status fees and funding
- status payoffs and account risk

### Tiempo, unidades y frescura

- symbol must belong to the six-pair scope
- timestamps and freshness follow the referenced M3 contracts
- price and money use quote asset; quantity uses base asset
- rates and fractions are dimensionless unless explicitly stated

### Formula exacta

```text
economic_ready=all(required economic statuses available|N/A)
account_risk_ready=(account_risk status=available)
decision_authorized=false until governance is defined
```

### Normalizacion entre pares

- Dimensionless ratios remain comparable; quote-money outputs are never compared across pairs without explicit normalization.

### Horizontes

- intraday_short
- intraday_wide
- short_swing

### Activacion

- all declared inputs are present and valid
- the operator belongs to the applicable execution, exposure or economic branch

### No aplicacion o bloqueo

- Claves o estados fuera del contrato.

### Fuentes y afirmacion respaldada

- `M3-DATA-CONTRACTS` [internal_project_contract]: Ausencia y degradacion deben declararse por dato.

### Lo que las fuentes no respaldan

- Convertir disponibilidad en confianza numerica.
- Grados A/B/C o GO/NO-GO sin politica validada.

### Relacion esperada con resultados

- No direct market-probability relation is authorized. The output describes execution, exposure or payoff after market outcomes.

### Control de doble conteo

- Use the canonical M4.6 slot for this family; derived values, containers and overlapping costs are not additional votes.

### Ausencia de datos

- Block the unavailable result and expose the missing component; do not use a neutral value or universal constant.

### Pruebas, limites e invariantes

- Es control de completitud, no evidencia de rentabilidad.
- long/short signs must follow the declared direction
- no execution or exposure value may change market probability

### Traza producida

- rule id and version
- input values and units
- provider/receive timestamps when market data is used
- formula branch, output and availability status

### Campos prohibidos o reservados a null

- Ninguno en esta ficha.

### Refutacion, suspension o retirada

- Claves o estados fuera del contrato.
- Suspend if provider semantics or units no longer match the documented contract.

### Hipotesis predictiva separada

- Ninguna.

### Autorizacion actual

- Efecto probabilistico directo: **NO**.
- Peso numerico: **NO**.
- Produccion: **NO**.

## Cierre de lectura

El propietario puede objetar cualquier ficha citando su ID.
M4 permanece abierta hasta una aprobacion expresa.

SHA-256 del payload canonico consolidado: `4edd9f5be4debeddb374bbe477f29e51df7e30723e8cebd2e31504b9c6abb8f0`.
