# M4.2 - Alcanzabilidad por geometria, volatilidad y horizonte

Fecha: 2026-07-27
Estado: HITO INTERNO COMPLETADO; M4 SIGUE EN CURSO

## 1. Resultado

- Fichas formales: **6**.
- Hipotesis separadas: **3**.
- Efectos probabilisticos autorizados: **0**.
- Pesos numericos autorizados: **0**.
- Cambios productivos: **ninguno**.

M4.2 define calculos y restricciones. No convierte distancia o
volatilidad en porcentajes. La integracion probabilistica pertenece a
M6 y debera respetar monotonicidad, masa y primer cruce de barreras.

## 2. Formulas

- Geometria: `d_TP=s*ln(TP/E)` y `d_SL=-s*ln(SL/E)`.
- Retorno: `r_i=ln(C_i/C_(i-1))`.
- Varianza realizada anterior: `RV_prev(H)=sum(r_i^2)`.
- Escala observada: `sigma_prev(H)=sqrt(RV_prev(H))`.
- Alcanzabilidad: `z_TP=d_TP/sigma_prev(H)` y
  `z_SL=d_SL/sigma_prev(H)`.
- Entrada pendiente: `z_entry=abs(ln(E/P_analysis))/sigma_prev(H)`.

`sigma_prev(H)` se etiqueta como observacion del horizonte anterior,
no como prediccion del siguiente. Su utilidad futura es una hipotesis
prerregistrada que debera verificarse independientemente.

## 3. Politica temporal

- El horizonte exacto nunca se redondea.
- El intervalo debe dividir exactamente H.
- Se exigen al menos 24 retornos cerrados dentro de H.
- Se elige el mayor intervalo soportado que cumpla ambas condiciones.
- Huecos, barras abiertas, futuras u obsoletas bloquean la familia.
- La cifra 24 es politica de resolucion del proyecto, no optimo publicado.

## 4. Reglas

| ID | Tipo | Bloques | Probabilidad |
|---|---|---|---|
| `M4-RULE-HORIZON-SAMPLING-001` | `deterministic_policy` | 26 | no |
| `M4-RULE-PLAN-GEOMETRY-001` | `deterministic_calculation` | 26, 28 | no |
| `M4-RULE-LOG-RETURNS-001` | `deterministic_calculation` | 26 | no |
| `M4-RULE-REALIZED-VOLATILITY-001` | `deterministic_measure_with_separate_hypothesis` | 26 | no |
| `M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002` | `deterministic_calculation` | 26, 28 | no |
| `M4-RULE-PENDING-ACTIVATION-001` | `deterministic_calculation` | 28 | no |

## 5. Sustituciones

- `IND-ATR14-CURRENT`: Not used as P0 horizon scale; P1 ATR remains deferred.
- `IND-PENDING-ZONE`: Replaced by deterministic activation distance.
- `SCORE-PRICE_VS_ENTRY_BIAS`: Retired; M2 log geometry is canonical.
- `SCORE-ZONE_PROBABILITY_ADJUSTMENT`: Retired; activation remains a separate future event.
- `SCORE-VOLATILITY_PENALTY`: Retired; continuous z_TP/z_SL geometry replaces bands.
- `SCORE-ZONE_RANGE_PROBABILITY_ADJUSTMENT`: Retired; no-entry and expiry-after-entry remain separate.

## 6. Limites

- La literatura respalda realized volatility y primer cruce como
  problemas tecnicos, no los porcentajes de esta aplicacion.
- No se presupone persistencia exacta de volatilidad.
- No se presupone Brownian motion, normalidad ni drift constante.
- No se usan ATR, bandas sigma ni thresholds como probabilidades.
- La entrada pendiente conserva `no_entry` separado de la expiracion.

## 7. Siguiente paso

`M4.3`: regimen, estructura y jerarquia multi-timeframe. No puede
reutilizar la misma volatilidad o tendencia bajo nombres distintos.

SHA-256 del payload canonico (`operational_sampling_policy`, `policy_decision_records`, `sources`, `rules`, `supersedes_current_elements`): `50672ed0ca9fdca56148c8c9009771d21ba259597ca212270132d25453db75ae`.
