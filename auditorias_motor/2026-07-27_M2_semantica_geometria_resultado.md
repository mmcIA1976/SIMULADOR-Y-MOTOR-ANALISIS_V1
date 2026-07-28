# M2 - Semantica, geometria e invariantes del resultado

Fecha: 2026-07-27
Estado: COMPLETADA Y APROBADA EL 2026-07-27

## 1. Limite de la fase

M2 define que debe significar el resultado antes de elegir datos, reglas
o modelo. No crea un motor nuevo, no selecciona regresion, GBM, first
passage ni otro metodo, y no modifica el scoring productivo.

La auditoria externa de las 86 reglas se usa solo como apoyo. Se integra
la separacion entre no entrada y expiracion posterior a entrada. Las
recomendaciones de datos, features, costes y validacion se aplazan a su
fase. Se descartan 3-60 h y cualquier eleccion anticipada de modelo.

## 2. Tiempo cero y horizonte

- `analysis_at` es el tiempo cero pre-trade.
- `data_cutoff_at <= analysis_at` para toda evidencia predictiva.
- Es obligatorio `horizon_seconds` dentro del marco elegido.
- `expiry_at = analysis_at + horizon_seconds`.
- El reloj no se reinicia si una orden pendiente entra tarde.
- No existe fallback a 3-60 h ni a otro marco.

| Marco | Minimo | Maximo |
|---|---:|---:|
| `intraday_short` | 30 min | 4 h |
| `intraday_wide` | 4 h | 24 h |
| `short_swing` | 1 dia | 7 dias |

## 3. Geometria

```text
s = +1 para long; -1 para short
d_tp = s * ln(TP / entrada)
d_sl = -s * ln(SL / entrada)
z_tp = d_tp / sigma_H
z_sl = d_sl / sigma_H
```

Long exige `SL < entrada < TP`; short exige `TP < entrada < SL`.
Las dos distancias son positivas y simetricas. `sigma_H` debe ser una
escala positiva de volatilidad de retornos logaritmicos correspondiente
al horizonte exacto. Si falta o no es valida, la probabilidad se
bloquea. M3 debe aprobar el dato y M4 definir el estimador antes de
que M6 lo integre; M2 no inventa aqui ninguna de esas decisiones.

## 4. Arbol de eventos

Para entrada a mercado, el baseline semantico ideal usa `P(entrada)=1`.
Para una orden pendiente se separa primero:

```text
entrada ejecutada antes del vencimiento
no_entry: entrada no ejecutada antes del vencimiento
```

Condicionado a entrada ejecutada:

```text
TP_first
SL_first
expiry_after_entry
```

Las probabilidades globales son:

```text
P(TP_first)            = P(entry) * P(TP_first | entry)
P(SL_first)            = P(entry) * P(SL_first | entry)
P(expiry_after_entry)  = P(entry) * P(expiry_after_entry | entry)
P(no_entry)            = 1 - P(entry)
```

Las cuatro suman uno. La interfaz mantiene como resultados principales
`P(TP_first)` y `P(SL_first)` y muestra:

```text
P(unresolved) = P(expiry_after_entry) + P(no_entry)
P(TP_first) + P(SL_first) + P(unresolved) = 1
```

`no_entry` y `expiry_after_entry` nunca se confunden en la traza.
Touch, trigger y fill deberan definirse en el contrato de ejecucion;
M2 prohibe tratarlos como sinonimos silenciosos.

## 5. Ambiguedad y censura

- TP y SL en la misma observacion sin secuencia resoluble: ambiguo.
- Fin de cobertura, huecos o cierre manual previo: censurado.
- Ambos estados se conservan y no se fuerzan a ningun outcome.
- El outcome posterior nunca reescribe el snapshot pre-trade.

## 6. Invariantes (19)

| ID | Categoria | Exigencia |
|---|---|---|
| `M2-INV-PRETRADE-01` | `time` | analysis_at is time zero; every predictive datum and model cutoff must be <= analysis_at, and no later outcome may alter the original snapshot. |
| `M2-INV-HORIZON-01` | `time` | A concrete horizon_seconds inside one of the three current profiles is mandatory; expiry_at=analysis_at+horizon_seconds. |
| `M2-INV-GEOMETRY-01` | `geometry` | Long requires SL<entry<TP; short requires TP<entry<SL; invalid geometry blocks the analysis. |
| `M2-INV-GEOMETRY-02` | `geometry` | TP and SL distances are positive signed log distances and are side-symmetric. |
| `M2-INV-SCALE-01` | `geometry` | Barrier distances must also be expressed in units of an approved positive log-return volatility scale matched to the exact horizon; an unavailable or invalid scale blocks probability. |
| `M2-INV-ACTIVATION-01` | `entry` | Pending entry execution is a separate event. no_entry cannot be renamed as range or expiry_after_entry. |
| `M2-INV-CLOCK-01` | `entry` | For pending plans the clock never restarts at entry; late entry has only expiry_at-entry_at remaining. |
| `M2-INV-OUTCOME-01` | `outcome` | Conditional on executed entry, TP_first, SL_first and expiry_after_entry are mutually exclusive and exhaustive. |
| `M2-INV-OUTCOME-02` | `outcome` | Overall pending outcomes are TP_first, SL_first, expiry_after_entry and no_entry. |
| `M2-INV-OUTPUT-01` | `output` | The two main displayed percentages are unconditional P(TP_first) and P(SL_first) from analysis_at; unresolved is explicit. |
| `M2-INV-MONO-TP-01` | `monotonicity` | With snapshot, entry, SL and horizon fixed, moving TP farther cannot increase P(TP_first) and must affect reachability. |
| `M2-INV-MONO-SL-01` | `monotonicity` | With snapshot, entry, TP and horizon fixed, moving SL farther cannot increase P(SL_first) and must affect reachability. |
| `M2-INV-MONO-HORIZON-01` | `monotonicity` | With all non-time inputs fixed, extending the horizon cannot increase unresolved probability. |
| `M2-INV-CONTINUITY-01` | `continuity` | An infinitesimal continuous input change cannot create a material probability jump unless a documented discrete market event changes state. |
| `M2-INV-SYMMETRY-01` | `symmetry` | Mirrored long and short plans with mirrored signed market inputs must produce mirrored geometry and equivalent reachability. |
| `M2-INV-SEPARATION-01` | `separation` | Market path probability, entry execution, costs, plan quality and account risk remain separate before an explicit integration. |
| `M2-INV-DATA-01` | `evidence` | Missing, stale, future, invalid or unapproved mandatory data produces blocked or insufficient_evidence, never neutral evidence. |
| `M2-INV-AMBIGUITY-01` | `labels` | A later observation that cannot order TP and SL is ambiguous; missing coverage or manual closure is censored. |
| `M2-INV-TRACE-01` | `traceability` | Every output records semantic version, plan, clock, geometry, entry tree, conditional and overall masses, data cutoff and blocking reasons. |

## 7. Casos limite (15)

| ID | Caso | Resultado exigido |
|---|---|---|
| `M2-CASE-001` | `valid_long_geometry` | `accepted_positive_distances` |
| `M2-CASE-002` | `valid_short_mirror` | `same_log_distances_as_case_001` |
| `M2-CASE-003` | `invalid_long_barriers` | `blocked_invalid_geometry` |
| `M2-CASE-004` | `market_entry_distribution` | `no_entry_zero_all_masses_one` |
| `M2-CASE-005` | `pending_no_entry_separated` | `{"expiry_after_entry":0.12,"no_entry":0.4,"sl_first":0.18,"tp_first":0.3}` |
| `M2-CASE-006` | `late_pending_entry_does_not_restart_clock` | `{"expiry_at_seconds":14400,"remaining_seconds":600}` |
| `M2-CASE-007` | `same_interval_tp_sl` | `ambiguous_not_forced` |
| `M2-CASE-008` | `missing_exact_duration` | `blocked` |
| `M2-CASE-009` | `unknown_horizon` | `blocked` |
| `M2-CASE-010` | `case_872_873_discontinuity` | `no_material_jump` |
| `M2-CASE-011` | `current_probability_floor_mass` | `mass_exactly_one` |
| `M2-CASE-012` | `missing_market_data` | `blocked_or_insufficient_evidence` |
| `M2-CASE-013` | `account_parameters_do_not_change_path` | `same_market_path_distribution` |
| `M2-CASE-014` | `farther_barrier_sensitivity` | `p_tp_b_not_greater_and_not_identical_without_reason` |
| `M2-CASE-015` | `missing_or_invalid_horizon_volatility` | `blocked_not_neutralized` |

El caso `M2-CASE-010` conserva expresamente la reproduccion 872/873:
pasar el precio short de `99.999999` a `100` con entrada `100` no
puede cambiar cinco puntos una supuesta probabilidad.

## 8. Contrato de salida

Una salida aprobable debe declarar identidad, reloj, geometria,
distribucion de entrada, outcomes condicionales, outcomes globales,
las tres masas, calidad de datos, metodo/version y bloqueos.

Estados permitidos:

- `probability_available`;
- `blocked`;
- `insufficient_evidence`.

Quedan prohibidos puntos manuales presentados como probabilidad, SL
residual con suelo, fallback silencioso, ausencia neutral, mezclar
no entrada con rango, reiniciar el reloj y renormalizar ocultando
eventos.

## 9. Resultado contra el motor actual

El scoring productivo falla **9**
comprobaciones M2, de ellas
**6** criticas. Es el resultado
esperado: M2 especifica el contrato que la revision futura debera
cumplir; no certifica el score vigente.

| Hallazgo | Severidad | Motivo |
|---|---|---|
| `M2-CURRENT-FAIL-01` | `critical` | The residual 5% SL floor can create mass > 1. |
| `M2-CURRENT-FAIL-02` | `critical` | An infinitesimal price change causes a 5-point score jump. |
| `M2-CURRENT-FAIL-03` | `critical` | The production TradeProposal has only a category, not an exact expiry duration. |
| `M2-CURRENT-FAIL-04` | `high` | An unknown horizon silently becomes intraday_short. |
| `M2-CURRENT-FAIL-05` | `critical` | Missing candles are converted into apparently neutral technical evidence. |
| `M2-CURRENT-FAIL-06` | `critical` | Pending no-entry is added to range instead of remaining an independent event. |
| `M2-CURRENT-FAIL-07` | `high` | Execution/cost concepts directly alter the market path score. |
| `M2-CURRENT-FAIL-08` | `critical` | The output is a heuristic score without a documented probabilistic derivation. |
| `M2-CURRENT-FAIL-09` | `high` | Displayed bands are not uncertainty intervals derived from evidence. |

## 10. Relacion con E1.5

Se conservan del contrato E1.5: tiempo cero pre-trade, distancias
logaritmicas, horizonte concreto, bloqueo por datos, traza y
aislamiento de produccion.

La aprobacion de M2 supera dos puntos de E1.5:

1. una orden pendiente no activada ya no se mezcla con expiracion
   despues de entrada;
2. el baseline multinomial deja de estar preseleccionado; M6 debera
   comparar y justificar el metodo.

`challenger_engine.py` sigue siendo infraestructura inerte
`contract-only`; M2 no lo modifica ni lo convierte en motor nuevo.

## 11. Estado y siguiente fase

SHA-256 del contrato: `b7f57f373fc0cab0385ec0b3eef4477cb98f4bc0f355fd20f4ddabbb0a3413c3`.

M2 queda completada y aprobada expresamente por el propietario el
2026-07-27. M3 no se ha iniciado y es la siguiente fase:
contratos y auditoria de datos pre-trade.
