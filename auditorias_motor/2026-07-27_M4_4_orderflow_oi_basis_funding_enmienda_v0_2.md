# M4.4 - Order flow, OI, basis y funding

Fecha: 2026-07-27
Estado: COMPLETADA INTERNAMENTE; M4 SIGUE EN CURSO

## 1. Resultado

- 7 fichas formales.
- 7 hipotesis separadas.
- 0 probabilidades, puntos, pesos o efectos productivos.
- Produccion y aprendizaje permanecen congelados.

## 2. Formulas

- Agresion ejecutada: `ATI_H=(B_H-S_H)/(B_H+S_H)`.
- OI: `dOI_H=ln(OI_t/OI_(t-H))`.
- Estado precio-OI: `(D_H,dOI_H)` sin narrativa de cuadrantes.
- Basis: tres razones logaritmicas con quotes limitados por tiempo de recepcion.
- Prima mark-index: `ln(markPrice/indexPrice)`.
- Funding: tasa observada linealizada por hora y carga realizada del H anterior.
- Contexto: `(ATI_H,dOI_H,b_mid,linearized_f_last_hour)` sin score.

## 3. Decisiones criticas

- Taker imbalance no se denomina OFI ni CVD.
- OI no identifica por si solo largos o cortos.
- Spot o Futures no reciben liderazgo permanente.
- La ultima tasa de funding no se trata como la tasa futura.
- Medidas alternativas de una familia no se suman ni promedian.
- Retencion insuficiente bloquea; no se sustituye por last-N.

## 4. Reglas

| ID | Probabilidad | Peso | Produccion |
|---|---|---|---|
| `M4-RULE-AGGRESSOR-IMBALANCE-001` | no | no | no |
| `M4-RULE-OPEN-INTEREST-CHANGE-001` | no | no | no |
| `M4-RULE-PRICE-OI-STATE-001` | no | no | no |
| `M4-RULE-SPOT-FUTURES-BASIS-001` | no | no | no |
| `M4-RULE-MARK-INDEX-PREMIUM-001` | no | no | no |
| `M4-RULE-FUNDING-STATE-001` | no | no | no |
| `M4-RULE-DERIVATIVES-CONTEXT-001` | no | no | no |

## 5. Limites de transferencia

- La evidencia OFI publicada incluye libro, altas y cancelaciones.
- La evidencia OI publicada procede de futuros tradicionales.
- Los estudios spot-futuros no establecen un lider fijo.
- El funding ancla el perpetuo, pero no predice direccion solo.
- Las seis parejas y tres horizontes requieren validacion propia.

## 6. Siguiente paso

`M4.5`: ejecucion, costes, riesgo y evaluacion. Debera separar
probabilidad de mercado de viabilidad economica de la operacion.

SHA-256 del payload canonico (politicas, fuentes, reglas, familias y sustituciones): `b96b1ea221d7df3ef72a6545cfd1bbf2790bccbe517ad2430eb9d2d99ea377f8`.
