# M4.6 - Combinaciones, doble conteo y reconciliacion final

Fecha: 2026-07-27
Estado: COMPLETADA INTERNAMENTE; M4 SIGUE EN CURSO

## 1. Universo reconciliado

- 27/27 reglas formales.
- 15/15 hipotesis.
- 30/30 elementos antiguos.
- 17/17 familias semilla.
- 12/12 bloques P0.
- 8 combinaciones.
- 0 probabilidades, pesos, puntos o efectos productivos.

## 2. Regla contra doble conteo

Cada dato ocupa un unico slot canonico. No pueden sumarse:

- valores derivados junto a sus padres como votos independientes;
- etiquetas junto a los valores continuos que las producen;
- un vector contenedor junto a sus componentes;
- fuentes alternativas de la misma medida;
- spread y shortfall desde midpoint para la misma ejecucion;
- variables economicas o de exposicion a la probabilidad de mercado.

## 3. Interacciones

- Toda interaccion `x_i*x_j` conserva `x_i` y `x_j`.
- El signo y magnitud de cualquier efecto siguen desconocidos.
- Las combinaciones quedan fijadas antes de observar resultados.
- M6 debera definir el modelo probabilistico y sus coeficientes.
- M8 debera contrastar cada incremento en datos independientes.

## 4. Combinaciones prerregistradas

| ID | Capa | Estado |
|---|---|---|
| `M4-COMB-REACHABILITY-BASE-001` | market_probability_candidate | no verificada, sin peso |
| `M4-COMB-PENDING-TREE-001` | market_probability_tree | no verificada, sin peso |
| `M4-COMB-STRUCTURE-001` | market_probability_candidate | no verificada, sin peso |
| `M4-COMB-FLOW-001` | market_probability_candidate | no verificada, sin peso |
| `M4-COMB-PRICE-OI-001` | market_probability_candidate | no verificada, sin peso |
| `M4-COMB-DERIVATIVES-001` | market_probability_candidate | no verificada, sin peso |
| `M4-COMB-FULL-MARKET-001` | market_probability_candidate | no verificada, sin peso |
| `M4-COMB-ECONOMIC-EVALUATION-001` | economic_evaluation | no verificada, sin peso |

## 5. Sustitucion de contradicciones

El antiguo `SCORE-CONTRADICTION_PENALTY` queda retirado. Un
estado mixto se conserva como dato; solo las interacciones
prerregistradas pueden estudiar si una variable condiciona a otra.

## 6. Pendiente

- `probability_link_and_calibration` -> M6: M4 defines inputs and combinations, not coefficients.
- `software_implementation` -> M5: Production remains frozen through M4.
- `mathematical_and_software_verification` -> M7: Requires the implemented M5-M6 candidate.
- `independent_empirical_validation` -> M8: Requires preregistered metrics and temporal holdout.
- `account_liquidation_and_risk_policy` -> M5_or_later: Equity, margin mode and maintenance brackets are not in the approved P0 data contract.
- `grade_and_decision_policy` -> after_M8: No validated governance thresholds exist.

## 7. Siguiente paso

`M4.7`: reproducibilidad completa y revision del propietario.
M4 no se cierra sin aprobacion expresa.

SHA-256: `b80c7089d2cd272803c110cd6256638e4bc74650b4964b028e4a8682bd1f5f78`.
