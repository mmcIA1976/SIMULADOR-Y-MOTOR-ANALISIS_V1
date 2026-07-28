# M4.7 - Paquete de revision del propietario

Fecha: 2026-07-27
Estado: LISTO PARA REVISION; M4 NO CERRADA; M5 NO INICIADA

## 1. Que se revisa

- 27 reglas formales completas.
- 15 hipotesis no verificadas.
- 15 slots canonicos.
- 16 relaciones anti-duplicidad.
- 8 combinaciones.
- 30 elementos antiguos.
- 29 artefactos con hash.

## 2. Significado exacto de aprobar M4

Aprobar significa aceptar un alcance documental congelado para M5.
No significa que las reglas ya sean predictivas, rentables o aptas
para produccion. Los coeficientes y probabilidades pertenecen a M6;
la verificacion a M7 y la validacion independiente a M8.

## 3. Resultado tecnico

- Formula, datos, unidades y condiciones: completos 27/27.
- Fuente y limite de transferencia: completos 27/27.
- Traza y regla de refutacion: completas 27/27.
- Hipotesis enlazadas con ficha: 15/15.
- Reconciliacion antigua: 30/30, sin efecto heredado.
- Bloques P0: 12/12.
- Pesos, puntos y efectos productivos autorizados: 0.

## 4. Reglas

| ID | Subfase | Nombre | Hipotesis |
|---|---|---|---|
| `M4-RULE-HORIZON-SAMPLING-001` | M4.2 | Seleccion exacta de intervalo para el horizonte | `ninguna` |
| `M4-RULE-PLAN-GEOMETRY-001` | M4.2 | Geometria logaritmica long/short | `ninguna` |
| `M4-RULE-LOG-RETURNS-001` | M4.2 | Retornos logaritmicos de velas cerradas | `ninguna` |
| `M4-RULE-REALIZED-VOLATILITY-001` | M4.2 | Volatilidad realizada del horizonte anterior | `M4-HYP-REACH-001` |
| `M4-RULE-BARRIER-REACHABILITY-001` | M4.2 | Distancia TP/SL normalizada por volatilidad | `M4-HYP-REACH-002` |
| `M4-RULE-PENDING-ACTIVATION-001` | M4.2 | Distancia de activacion para entrada pendiente | `M4-HYP-PENDING-001` |
| `M4-RULE-EXPONENTIAL-SMOOTHER-001` | M4.3 | Operador de suavizado exponencial | `ninguna` |
| `M4-RULE-PATH-STRUCTURE-001` | M4.3 | Desplazamiento y eficiencia de trayectoria | `M4-HYP-STRUCTURE-001` |
| `M4-RULE-PRIOR-EXTREMA-001` | M4.3 | Extremos observados del horizonte anterior | `M4-HYP-LEVEL-001` |
| `M4-RULE-VOLATILITY-RANK-001` | M4.3 | Percentil continuo de volatilidad | `M4-HYP-REGIME-001` |
| `M4-RULE-MTF-HIERARCHY-001` | M4.3 | Jerarquia multi-timeframe H, 2H y 4H | `M4-HYP-MTF-001` |
| `M4-RULE-CONTINUOUS-REGIME-001` | M4.3 | Vector continuo de regimen | `M4-HYP-REGIME-002` |
| `M4-RULE-AGGRESSOR-IMBALANCE-001` | M4.4 | Desequilibrio de operaciones agresoras ejecutadas | `M4-HYP-FLOW-001` |
| `M4-RULE-OPEN-INTEREST-CHANGE-001` | M4.4 | Cambio logaritmico de open interest | `M4-HYP-OI-001` |
| `M4-RULE-PRICE-OI-STATE-001` | M4.4 | Estado conjunto precio y open interest | `M4-HYP-PRICE-OI-001` |
| `M4-RULE-SPOT-FUTURES-BASIS-001` | M4.4 | Intervalo observable spot-Futures | `M4-HYP-BASIS-001` |
| `M4-RULE-MARK-INDEX-PREMIUM-001` | M4.4 | Prima sincronizada mark-index | `M4-HYP-PREMIUM-001` |
| `M4-RULE-FUNDING-STATE-001` | M4.4 | Estado temporal y carga realizada de funding | `M4-HYP-FUNDING-001` |
| `M4-RULE-DERIVATIVES-CONTEXT-001` | M4.4 | Vector continuo de contexto de derivados | `M4-HYP-DERIVATIVES-001` |
| `M4-RULE-QUOTED-SPREAD-001` | M4.5 | Spread cotizado en el instante de llegada | `ninguna` |
| `M4-RULE-DEPTH-SWEEP-001` | M4.5 | Barrido visible e implementation shortfall | `ninguna` |
| `M4-RULE-FEE-SCENARIOS-001` | M4.5 | Comision por rol de liquidez autenticado | `ninguna` |
| `M4-RULE-FUNDING-CASHFLOW-001` | M4.5 | Flujo monetario firmado de funding | `ninguna` |
| `M4-RULE-PLAN-EXPOSURE-001` | M4.5 | Exposicion monetaria lineal del plan | `ninguna` |
| `M4-RULE-NET-PAYOFFS-001` | M4.5 | Vector monetario neto por resultado | `ninguna` |
| `M4-RULE-EXPECTED-VALUE-001` | M4.5 | Identidad de valor esperado por resultados | `ninguna` |
| `M4-RULE-EVALUATION-READINESS-001` | M4.5 | Estado explicito de disponibilidad economica | `ninguna` |

## 5. Combinaciones

| ID | Capa | Estado |
|---|---|---|
| `M4-COMB-REACHABILITY-BASE-001` | market_probability_candidate | no verificada |
| `M4-COMB-PENDING-TREE-001` | market_probability_tree | no verificada |
| `M4-COMB-STRUCTURE-001` | market_probability_candidate | no verificada |
| `M4-COMB-FLOW-001` | market_probability_candidate | no verificada |
| `M4-COMB-PRICE-OI-001` | market_probability_candidate | no verificada |
| `M4-COMB-DERIVATIVES-001` | market_probability_candidate | no verificada |
| `M4-COMB-FULL-MARKET-001` | market_probability_candidate | no verificada |
| `M4-COMB-ECONOMIC-EVALUATION-001` | economic_evaluation | no verificada |

## 6. Decisiones solicitadas

- `M4-OWNER-DECISION-001`: Aceptar las 27 reglas formales como alcance documental P0 que M5 podra implementar.
  Significa: Se aceptan sus formulas, datos, unidades, fuentes, limites, bloqueos y trazas; no se afirma valor predictivo.
- `M4-OWNER-DECISION-002`: Aceptar las 15 hipotesis como universo candidato no verificado para M6-M8.
  Significa: No podran agregarse efectos retrospectivamente sin nueva version y nueva aprobacion.
- `M4-OWNER-DECISION-003`: Aceptar los 15 slots, 16 relaciones y 8 combinaciones prerregistradas de M4.6.
  Significa: Se prohibe contar dos veces padres, etiquetas, contenedores o fuentes alternativas.
- `M4-OWNER-DECISION-004`: Aceptar la disposicion final de los 30 elementos antiguos.
  Significa: Ningun punto, penalizacion o ajuste antiguo pasa al motor nuevo por herencia.
- `M4-OWNER-DECISION-005`: Aceptar los limites que permanecen bloqueados para fases posteriores.
  Significa: Probabilidades, coeficientes, validacion, riesgo de cuenta y politica de decision siguen sin resolverse en M4.
- `M4-OWNER-DECISION-006`: Cerrar M4 y autorizar el inicio separado de M5.
  Significa: Solo autoriza implementar variables y reglas trazables; no autoriza produccion, pesos, rentabilidad ni trading real.

## 7. Puerta de cierre

- Puerta tecnica: SUPERADA.
- Aprobacion del propietario: PENDIENTE.
- M4 cerrada: NO.
- Inicio de M5 autorizado: NO.

El propietario puede aprobar el conjunto o formular objeciones
identificadas por regla, hipotesis, combinacion o decision.

SHA-256: `bb35d13431b8d92d4c2c2e592f8bf601736248f143503fa685afa952dfecd966`.
