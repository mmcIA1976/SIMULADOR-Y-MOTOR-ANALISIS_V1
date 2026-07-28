# M4.3 - Regimen, estructura y multi-timeframe

Fecha: 2026-07-27
Estado: HITO INTERNO COMPLETADO; M4 SIGUE EN CURSO

## 1. Resultado

- Fichas formales: **6**.
- Hipotesis separadas: **5**.
- Efectos probabilisticos autorizados: **0**.
- Pesos numericos autorizados: **0**.
- Regimenes categoricos autorizados: **0**.
- Periodos EMA autorizados: **0**.
- Cambios productivos: **ninguno**.

## 2. Variables exactas

- Desplazamiento: `D_W=ln(C_end/C_start)`.
- Variacion total: `TV_W=sum(abs(r_i))`.
- Eficiencia: `E_W=abs(D_W)/TV_W`.
- Eficiencia firmada: `SE_W=D_W/TV_W`.
- Percentil RV: midrank frente a 60 ventanas H anteriores.
- MTF: vector ordenado de `SE_H`, `SE_2H` y `SE_4H`.
- Regimen observado: vector `(q_RV, SE_H)` sin etiqueta.
- Nivel estructural: maximo/minimo del horizonte anterior, sin
  llamarlo soporte o resistencia.

## 3. Decisiones

- EMA queda como operador matematico, no como evidencia P0.
- No sobreviven periodos 9/21/50/200 ni cruces automaticos.
- No hay votos ni pesos multi-timeframe.
- Volatilidad, percentil y regimen son una sola familia, no tres senales.
- Tendencia H y acuerdo MTF son una familia, no bonus mas penalizacion.
- Un extremo entre entrada y TP se registra, pero no se penaliza.

## 4. Reglas

| ID | Estado | Probabilidad | Peso |
|---|---|---|---|
| `M4-RULE-EXPONENTIAL-SMOOTHER-001` | `documented_operator_not_admitted_as_p0_evidence` | no | no |
| `M4-RULE-PATH-STRUCTURE-001` | `documented_candidate_no_predictive_weight` | no | no |
| `M4-RULE-PRIOR-EXTREMA-001` | `documented_candidate_no_predictive_weight` | no | no |
| `M4-RULE-VOLATILITY-RANK-001` | `documented_candidate_no_predictive_weight` | no | no |
| `M4-RULE-MTF-HIERARCHY-001` | `documented_candidate_no_predictive_weight` | no | no |
| `M4-RULE-CONTINUOUS-REGIME-001` | `documented_candidate_no_predictive_weight` | no | no |

## 5. Limites de transferencia

- Momentum tradicional no acredita crypto intradia.
- Resultados tecnicos crypto varian por activo y fuera de muestra.
- Los niveles FX publicados no equivalen a nuestros extremos.
- El vector continuo no es un modelo Markov de regimen.
- Los parametros 60 y H/2H/4H son politicas del proyecto.

## 6. Siguiente paso

`M4.4`: order flow, spot-Futures, OI y funding. Debera mantener
separados actividad, direccion, basis, posicionamiento y coste.

SHA-256: `839f2f190c81e944c792bf8c5ee5bc7bbc2a61281ed707253113daab1ca3aabd`.
