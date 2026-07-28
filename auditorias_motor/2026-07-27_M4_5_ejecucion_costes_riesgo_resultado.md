# M4.5 - Ejecucion, costes, riesgo y evaluacion

Fecha: 2026-07-27
Estado: COMPLETADA INTERNAMENTE; M4 SIGUE EN CURSO

## 1. Resultado

- 8 fichas economicas formales.
- 0 hipotesis predictivas: esta subfase no predice mercado.
- 0 probabilidades, puntos, pesos o efectos productivos.
- Produccion y aprendizaje permanecen congelados.

## 2. Separacion obligatoria

- Mercado: probabilidades TP/SL/expiry, calibradas mas adelante.
- Ejecucion: spread, profundidad, fill, comisiones y slippage.
- Exposicion: margen, apalancamiento, cantidad y PnL monetario.
- Economia: payoff por resultado y EV solo con entradas completas.
- Gobierno: grade y decision quedan sin definir.

## 3. Formulas

- `mid=(bid+ask)/2`; `spread=(ask-bid)/mid`.
- `VWAP=sum(p_i*q_i)/Q` sobre el lado consumido del libro.
- `IS=D*(VWAP-mid)/mid`, con `D=+1` buy y `-1` sell.
- `fee=notional*rate(role)` para maker, taker o RPI.
- `funding=-position_sign*quantity*mark*rate` por evento.
- `notional=margin*leverage`; `quantity=notional/entry`.
- `PnL(P)=direction*quantity*(P-entry)`.
- `payoff_k=gross_k-fee_k-IS_k+funding_k`.
- `EV=sum(p_k*payoff_k)`, si `sum(p_k)=1`.

## 4. Bloqueos reales

- El libro futuro de salida no es observable en pre-trade.
- Las tasas futuras de funding no se conocen exactamente.
- Sin autenticacion no existe comision exacta de la cuenta.
- Sin equity, margin mode y maintenance brackets no hay riesgo de
  liquidacion ni riesgo de cuenta completo.
- Sin probabilidades calibradas M6 no existe EV autorizado.
- Sin politica documentada no existe grade ni decision autorizada.

## 5. Reglas

| ID | Probabilidad | Peso | Produccion |
|---|---|---|---|
| `M4-RULE-QUOTED-SPREAD-001` | no | no | no |
| `M4-RULE-DEPTH-SWEEP-001` | no | no | no |
| `M4-RULE-FEE-SCENARIOS-001` | no | no | no |
| `M4-RULE-FUNDING-CASHFLOW-001` | no | no | no |
| `M4-RULE-PLAN-EXPOSURE-001` | no | no | no |
| `M4-RULE-NET-PAYOFFS-001` | no | no | no |
| `M4-RULE-EXPECTED-VALUE-001` | no | no | no |
| `M4-RULE-EVALUATION-READINESS-001` | no | no | no |

## 6. Elementos actuales retirados o sustituidos

- `SCORE-LIQUIDITY_PENALTY`: Retirado: ejecucion separada de probabilidad de mercado.
- `OUT-FEE`: Sustituido por tasa autenticada y rol por cada tramo.
- `OUT-SLIPPAGE`: Sustituido por barrido visible actual; no minimo fijo.
- `OUT-FUNDING-COST`: Sustituido por flujo firmado por evento; futuro bloqueado.
- `OUT-RISK-SCORE`: Retirado: exposicion monetaria sin score arbitrario.
- `OUT-EV-COST`: Identidad conservada; salida bloqueada hasta M6 y costes completos.
- `OUT-GRADE`: Retirado hasta politica de gobierno documentada.
- `OUT-CONFIDENCE`: Disponibilidad no se convierte en confianza numerica.
- `OUT-DECISION`: Retirado hasta politica posterior validada.
- `OUT-LAYERED-SCORES`: Retirado: no mezcla mercado, ejecucion, plan y riesgo.
- `GATE-RR_RATIO_GTE_3`: Umbral universal retirado.
- `GATE-RISK_DISTANCE_LT_0_25`: Umbral universal retirado.
- `GATE-RISK_DISTANCE_GTE_3`: Umbral universal retirado.
- `GATE-REWARD_DISTANCE_GTE_3`: Umbral universal retirado.

## 7. Siguiente paso

`M4.6`: combinaciones, doble conteo y reconciliacion final.
No se inicia M5 ni se modifica el motor productivo.

SHA-256: `daf663744645202ccffbdd72865f4e770a76c94f9a9ed96de197398855b57de0`.
