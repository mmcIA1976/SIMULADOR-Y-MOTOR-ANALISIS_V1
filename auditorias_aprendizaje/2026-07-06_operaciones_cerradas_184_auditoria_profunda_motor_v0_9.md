# Auditoria profunda del motor de analisis

Fecha: 2026-07-06

Estado: auditoria en lectura, sin cambios aplicados al motor ni a Supabase.

## Alcance

Se revisaron todas las operaciones cerradas guardadas en Supabase hasta la fecha de la auditoria.

Resumen de cobertura:

- Operaciones totales registradas: 198.
- Operaciones cerradas revisadas: 184.
- Operaciones cerradas con analisis/recomendacion enlazada: 184 / 184.
- Operaciones cerradas con `learning_evaluations`: 182 / 184.
- Operaciones cerradas resueltas usadas para porcentajes duros: 170.
- Operaciones resueltas del motor actual `rules-v0.9-pending-zone-adjusted`: 67.

Las 170 operaciones resueltas son las que permiten medir acierto/fallo con limpieza:

- Acierto: `plan_success` o `plan_would_succeed`.
- Fallo: `plan_failure` o `plan_would_fail`.

Quedan fuera de los porcentajes duros, pero no de la revision general:

- `plan_unresolved`.
- `contest_expiry_mark_to_market`.
- cierres manuales/parciales sin desenlace TP/SL limpio.

## Alertas de consistencia detectadas

No se modifico ningun dato.

Casos a revisar antes de cualquier correccion:

- Operacion `#1`: cierre `stop_loss` con `close_price` distinto del nivel exacto de SL. Operacion antigua.
- Operacion `#3`: cierre `stop_loss` con `close_price` distinto del nivel exacto de SL. Operacion antigua.
- Operacion `#185`: cerrada manualmente, sin `learning_evaluation` en el momento de la auditoria.
- Operacion `#190`: cerrada como `take_partial`, sin `learning_evaluation` en el momento de la auditoria.

Interpretacion:

- `#1` y `#3` parecen pertenecer a logica antigua de cierre con precio real/posterior, no necesariamente error de PnL.
- `#185` y `#190` requieren evaluacion estructurada futura si se decide incluir manuales/parciales en aprendizaje limpio.
- No se recomienda corregir nada sin auditoria individual de cada caso.

## Resultado global

Muestra resuelta total: 170 operaciones.

- Aciertos: 65.
- Fallos: 105.
- Acierto global: 38.2%.
- Fallo global: 61.8%.
- PnL total: -1869.53 USDT.
- PnL medio: -11.00 USDT.

Muestra resuelta v0.9: 67 operaciones.

- Aciertos: 23.
- Fallos: 44.
- Acierto v0.9: 34.3%.
- Fallo v0.9: 65.7%.
- PnL total v0.9: -37.83 USDT.
- PnL medio v0.9: -0.56 USDT.

Lectura:

- El motor actual v0.9 tiene PnL casi plano, pero una tasa de fallo alta.
- La mejora prioritaria no debe ser buscar mas senales positivas, sino endurecer filtros de riesgo.
- El aprendizaje muestra que muchas perdidas ya estaban advertidas por el analisis, pero se operaron igualmente.

## Calibracion de probabilidades

### Probabilidad TP

Historico completo resuelto:

| TP estimada | Casos | TP real/acierto | Error frente a prediccion | PnL |
|---|---:|---:|---:|---:|
| <35% | 47 | 21.3% | -6.7 pp | -1198.02 |
| 35-45% | 39 | 35.9% | -4.7 pp | -937.20 |
| 45-55% | 55 | 45.5% | -4.5 pp | +21.66 |
| 55-65% | 27 | 51.9% | -7.2 pp | +136.02 |

Motor v0.9:

| TP estimada | Casos | TP real/acierto | Error frente a prediccion | PnL |
|---|---:|---:|---:|---:|
| <35% | 14 | 35.7% | +7.0 pp | +110.61 |
| 35-45% | 17 | 23.5% | -16.6 pp | -158.24 |
| 45-55% | 18 | 33.3% | -16.4 pp | -37.13 |
| 55-65% | 17 | 41.2% | -18.4 pp | +0.40 |

Conclusion:

- En el historico total, TP esta moderadamente optimista.
- En v0.9, los rangos medios de TP estan sobreestimando el acierto real.
- No conviene subir TP por nuevas confluencias sin exigir confirmacion adicional.

### Probabilidad SL

Historico completo resuelto:

| SL estimada | Casos | Fallo real | Error frente a prediccion | PnL |
|---|---:|---:|---:|---:|
| <35% | 15 | 53.3% | +22.1 pp | +45.10 |
| 35-45% | 50 | 48.0% | +7.9 pp | +202.14 |
| 45-55% | 49 | 59.2% | +9.8 pp | -457.37 |
| 55-65% | 26 | 84.6% | +24.3 pp | -1160.09 |
| >=65% | 30 | 73.3% | +5.6 pp | -499.31 |

Motor v0.9:

| SL estimada | Casos | Fallo real | Error frente a prediccion | PnL |
|---|---:|---:|---:|---:|
| <35% | 11 | 63.6% | +32.2 pp | -87.79 |
| 35-45% | 16 | 56.2% | +17.6 pp | +87.31 |
| 45-55% | 21 | 71.4% | +22.8 pp | -127.60 |
| 55-65% | 13 | 76.9% | +16.7 pp | -25.01 |
| >=65% | 6 | 50.0% | -18.0 pp | +115.27 |

Conclusion:

- La probabilidad de SL esta infraestimando el fallo real, especialmente en v0.9.
- `sl_probability >= 0.50` debe activar degradacion fuerte de decision.
- `sl_probability >= 0.55` debe tratarse como zona roja salvo confluencia excepcional.

## Rendimiento por medidor

### Decision del motor

Historico resuelto:

| Decision | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| observar | 133 | 36.8% | 63.2% | -1852.92 |
| simular con tamano prudente | 22 | 45.5% | 54.5% | +27.85 |
| simular | 14 | 42.9% | 57.1% | -38.96 |

Interpretacion:

- `observar` funciona como advertencia real.
- Operar contra `observar` explica buena parte del deterioro.
- Una operacion ganadora contra `observar` no debe reforzar automaticamente el analisis; debe clasificarse como exito contra advertencia.

### Setup grade

| Setup | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| D | 110 | 36.4% | 63.6% | -1864.34 |
| C | 45 | 42.2% | 57.8% | +55.24 |
| B | 14 | 42.9% | 57.1% | -45.83 |

Interpretacion:

- El grade por si solo no discrimina suficientemente.
- Setup D es claramente debil, pero B/C aun mezclan buenos y malos casos.
- El grade debe depender menos de EV/RR y mas de direccion, SL, alcanzabilidad del TP y alertas de zona.

### Risk level

| Riesgo | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| alto | 84 | 38.1% | 61.9% | -1835.47 |
| medio-alto | 57 | 36.8% | 63.2% | +66.09 |
| medio | 24 | 41.7% | 58.3% | -87.94 |
| bajo | 5 | 40.0% | 60.0% | -12.21 |

Interpretacion:

- El riesgo visible no esta separando tan bien como deberia.
- El riesgo debe incorporar mas fuerza cuando SL estimado, direccion, distancia al stop/TP y zona pendiente estan mal.

### Confianza

| Confianza | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| media | 63 | 47.6% | 52.4% | -873.84 |
| alta | 41 | 36.6% | 63.4% | -156.11 |
| media-baja | 35 | 37.1% | 62.9% | -323.33 |
| baja | 31 | 22.6% | 77.4% | -516.26 |

Interpretacion:

- `baja` si marca peligro.
- `alta` no esta demostrando fiabilidad suficiente.
- La confianza alta debe bloquearse si hay contradicciones internas fuertes.

## Scores internos

### Direction score

| Direction score | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| <40 | 62 | 21.0% | 79.0% | -1786.57 |
| 40-50 | 46 | 43.5% | 56.5% | -329.25 |
| 50-60 | 45 | 57.8% | 42.2% | +304.03 |
| 60-70 | 12 | 50.0% | 50.0% | +63.03 |

Conclusion:

- Es uno de los mejores medidores de la auditoria.
- `direction_score < 40` debe degradar fuerte.
- `direction_score 40-50` no debe permitir que RR alto compense direccion debil.

### Technical score

| Technical score | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| <40 | 45 | 20.0% | 80.0% | -836.46 |
| 40-50 | 12 | 41.7% | 58.3% | -477.37 |
| 50-60 | 8 | 25.0% | 75.0% | -235.58 |
| 60-70 | 18 | 33.3% | 66.7% | -37.79 |
| >=70 | 76 | 55.3% | 44.7% | -99.89 |

Conclusion:

- `technical_score < 40` es filtro negativo robusto.
- `technical_score >= 70` mejora acierto pero no garantiza PnL.
- Conviene usarlo como filtro de descarte mas que como permiso automatico para operar.

### Technical label

| Label | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| favorable | 94 | 51.1% | 48.9% | -137.67 |
| neutral | 20 | 35.0% | 65.0% | -712.95 |
| desfavorable | 45 | 20.0% | 80.0% | -836.46 |

Conclusion:

- `desfavorable` debe penalizar mas.
- `favorable` ayuda, pero no basta sin gestion de riesgo.

### Operation quality y EV

`operation_quality_score` y `expected_value_score` muestran inversion peligrosa:

- `operation_quality_score <40`: 60.4% acierto, +249.92.
- `operation_quality_score 60-70`: 21.6% acierto, -1340.31.
- `expected_value_score 40-50`: 52.9% acierto, +498.11.
- `expected_value_score >=70`: 21.1% acierto, -1628.15.

Conclusion:

- Estas formulas no deben ganar peso.
- Hay que revisar como estan combinando RR, distancia al TP, EV y riesgo.
- Probable causa: se premia demasiado la recompensa teorica aunque el TP no sea alcanzable.

## Distancias y relacion riesgo/beneficio

### Risk reward ratio

| RR | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| <1 | 34 | 58.8% | 41.2% | -107.52 |
| 1-1.5 | 47 | 48.9% | 51.1% | +32.29 |
| 1.5-2 | 21 | 28.6% | 71.4% | -18.30 |
| 2-3 | 32 | 37.5% | 62.5% | -345.61 |
| >=3 | 36 | 11.1% | 88.9% | -1430.41 |

Conclusion:

- RR alto esta funcionando como trampa.
- `RR >= 3` debe penalizar si no existe camino tecnico claro al TP.
- El motor no debe premiar RR alto por si solo.

### Distancia al stop

| Distancia SL | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| <0.25% | 16 | 6.2% | 93.8% | -41.14 |
| 0.25-0.75% | 28 | 32.1% | 67.9% | +8.71 |
| 0.75-1.5% | 46 | 43.5% | 56.5% | -51.95 |
| 1.5-3% | 44 | 50.0% | 50.0% | +437.46 |
| >=3% | 36 | 36.1% | 63.9% | -2222.61 |

Conclusion:

- Stop demasiado cerca: ruido.
- Stop demasiado lejos: riesgo estructural y PnL muy negativo.
- La zona mas sana fue 1.5-3%, pero depende de activo y temporalidad.

### Distancia al TP

| Distancia TP | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| 0.25-0.75% | 16 | 37.5% | 62.5% | +34.28 |
| 0.75-1.5% | 43 | 41.9% | 58.1% | +220.84 |
| 1.5-3% | 60 | 43.3% | 56.7% | +9.30 |
| >=3% | 48 | 29.2% | 70.8% | -2133.41 |

Conclusion:

- TP por encima de 3% esta fallando mucho.
- Se debe medir `target_path_quality` y barreras antes de permitir TP lejano.

## Tendencia y contexto direccional

### Regimen alineado con el lado

| Alineacion regimen | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| a favor | 107 | 46.7% | 53.3% | -442.40 |
| en contra | 51 | 23.5% | 76.5% | -1367.65 |

Conclusion:

- Operar contra regimen es muy negativo.
- Long en tendencia bajista y short en tendencia alcista deben exigir confirmacion fuerte.

### EMA stack contra el lado

Historico:

- 15m contra lado: 52 casos, 80.8% fallo, -1878.94.
- 1h contra lado: 55 casos, 76.4% fallo, -1503.67.
- 4h contra lado: 51 casos, 76.5% fallo, -787.83.

Conclusion:

- EMA stack contextualizado por lado es mucho mas util que leerlo de forma aislada.
- 15m y 1h son especialmente relevantes.

### Precio vs EMA21 contra el lado

Historico:

- 1h precio vs EMA21 contra lado: 63 casos, 79.4% fallo, -2068.57.
- 15m precio vs EMA21 contra lado: 65 casos, 70.8% fallo, -2051.79.
- 4h precio vs EMA21 contra lado: 57 casos, 77.2% fallo, -1336.00.

Conclusion:

- El precio frente a EMA21 contextualizado por lado debe subir peso como filtro negativo.

### Movimiento 24h contra el lado

Ticker 24h contra el lado:

- 62 casos.
- 82.3% fallo.
- PnL -2448.12.

Conclusion:

- `ticker_24h.price_change_pct` contextualizado por lado es un gran filtro de riesgo.
- Debe pesar mas que order book/CVD aislados.

## Order book, CVD y flujo

### Order book

| Order book alineado | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| a favor | 83 | 36.1% | 63.9% | -1324.21 |
| en contra | 80 | 40.0% | 60.0% | -563.25 |

Conclusion:

- No discrimina bien.
- Mantener peso bajo.
- Usarlo como contexto micro, no como senal de decision.

### CVD / trade flow

CVD alineado:

- A favor: 41.4% acierto.
- En contra: 36.8% acierto.

Trade buy ratio:

- Neutral: 50.0% acierto y +564.98.
- Extremos no mejoran de forma fiable.

Conclusion:

- CVD y flujo tienen valor limitado con la muestra actual.
- No deben dominar probabilidad direccional.
- Pueden servir para confirmar momentum si tambien acompanan tendencia y estructura.

## Ordenes pendientes y zonas

### Entrada pendiente

| Tipo entrada | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| market | 143 | 43.4% | 56.6% | -1704.26 |
| pending | 27 | 11.1% | 88.9% | -165.27 |

### Tipo de orden pendiente

| Tipo orden | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| limit_pullback | 10 | 20.0% | 80.0% | -121.30 |
| stop_breakdown | 10 | 0.0% | 100.0% | -48.23 |
| stop_breakout | 7 | 14.3% | 85.7% | +4.25 |

### Zona pendiente

| Medidor zona | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| zone available true | 25 | 8.0% | 92.0% | -135.62 |
| zone adjustment negativo | 21 | 9.5% | 90.5% | -29.22 |
| sweep risk alto | 20 | 10.0% | 90.0% | -25.71 |
| falsa ruptura riesgo | 13 | 7.7% | 92.3% | -31.60 |

Conclusion:

- La capa de zona pendiente detecta riesgo real.
- `stop_breakdown` debe pasar a modo muy restrictivo.
- Si hay ajuste negativo de zona, riesgo de barrida alto o falsa ruptura, la decision deberia degradarse hacia observar salvo confirmacion muy fuerte.

## Fibonacci

| Bias Fibonacci | Casos | Acierto | Fallo | PnL |
|---|---:|---:|---:|---:|
| neutral | 45 | 33.3% | 66.7% | -193.35 |
| desfavorable | 24 | 37.5% | 62.5% | +57.70 |
| favorable | 13 | 23.1% | 76.9% | -234.97 |

Conclusion:

- Fibonacci favorable no esta validado.
- No debe subir peso.
- Puede seguir como confluencia secundaria.
- Se debe vigilar `target_zone = extension`, que aparece debil cuando el TP queda demasiado lejos.

## Fallos no anticipados

Se revisaron 16 casos `analysis_missed_risk`.

Familias detectadas:

1. TP demasiado lejano:
   - Casos con `reward_distance_pct >= 3%`.
   - El motor apoyo planes con objetivo poco alcanzable.

2. Stop demasiado lejos:
   - Casos con `risk_distance_pct >= 3%`.
   - Gran impacto negativo en PnL y MAE.

3. RR alto enganoso:
   - Casos con `RR >= 3`.
   - El ratio parecia atractivo pero el camino al TP era debil.

4. EMA/timeframe contra el lado:
   - Especialmente 15m e 1h.
   - El motor no penalizo suficiente contradiccion interna.

5. Fibonacci favorable fallido:
   - Fibonacci marco favorable en casos que terminaron mal.
   - Refuerza mantenerlo como secundario.

6. Fallos realmente no explicados:
   - Algunas operaciones tenian buenos medidores y aun asi fallaron.
   - No deben provocar sobreajuste; una probabilidad nunca garantiza acierto.

## Exitos contra advertencia

Se revisaron 43 casos `success_against_analysis`, de los cuales 22 pertenecen a v0.9.

Lectura:

- 37 de 43 tenian decision `observar`.
- 35 de 43 eran setup D.
- 21 de 43 tenian riesgo alto.
- 30 de 43 eran BTCUSDT.

En v0.9:

- 17 de 22 eran `observar`.
- 15 de 22 eran setup D.
- 20 de 22 eran entradas a mercado.
- Solo 2 eran pendientes.

Conclusion:

- El motor fue conservador en algunos ganadores, especialmente BTC a mercado.
- Pero no conviene convertir esos casos en refuerzo automatico.
- Si una operacion gana contra advertencia, debe investigarse si hubo momentum posterior, barrida favorable o evento no capturado.
- Estos casos sirven para evitar que el afinado sea demasiado restrictivo.

## Simulacion de filtros candidatos

No se aplico ningun filtro. Solo se simulo impacto hipotetico si se hubieran bloqueado operaciones.

Historico completo:

| Filtro hipotetico | Casos bloqueados | Fallo | PnL del grupo | Mejora neta si se bloquea |
|---|---:|---:|---:|---:|
| SL >= 0.50 | 75 | 76.0% | -2434.58 | +2434.58 |
| SL >= 0.55 | 56 | 78.6% | -1659.40 | +1659.40 |
| direction_score < 40 | 62 | 79.0% | -1786.57 | +1786.57 |
| direction_score < 50 | 108 | 69.4% | -2115.82 | +2115.82 |
| RR >= 3 | 36 | 88.9% | -1430.41 | +1430.41 |
| RR >= 2 | 68 | 76.5% | -1776.01 | +1776.01 |
| ticker24h contra lado | 62 | 82.3% | -2448.12 | +2448.12 |
| 1h price EMA contra lado | 63 | 79.4% | -2068.57 | +2068.57 |
| 15m EMA stack contra lado | 52 | 80.8% | -1878.94 | +1878.94 |
| technical_score < 40 | 45 | 80.0% | -836.46 | +836.46 |
| pending entry | 27 | 88.9% | -165.27 | +165.27 |
| stop_breakdown | 10 | 100.0% | -48.23 | +48.23 |

Motor v0.9:

| Filtro hipotetico | Casos bloqueados | Fallo | PnL del grupo | Mejora neta si se bloquea |
|---|---:|---:|---:|---:|
| reward_distance >= 3% | 18 | 66.7% | -410.10 | +410.10 |
| risk_distance >= 3% | 14 | 57.1% | -224.50 | +224.50 |
| RR >= 3 | 16 | 93.8% | -120.48 | +120.48 |
| pending entry | 25 | 92.0% | -135.62 | +135.62 |
| stop_breakdown | 10 | 100.0% | -48.23 | +48.23 |
| risk_distance < 0.25% | 10 | 100.0% | -38.87 | +38.87 |
| zone adjustment negativo | 21 | 90.5% | -29.22 | +29.22 |

Advertencia:

- Algunas reglas historicas fuertes pierden claridad en v0.9.
- No deben aplicarse como veto ciego sin comprobar impacto sobre operaciones futuras.

## Propuesta exacta de afinado del motor

Propuesta para una futura version `rules-v0.10-risk-gated-calibration`, pendiente de aprobacion e implementacion.

### 1. Recalibrar probabilidad SL

Aplicar ajuste conservador:

- Si `sl_probability >= 0.50`: aumentar riesgo y degradar decision un nivel.
- Si `sl_probability >= 0.55`: degradar decision hacia `observar` salvo que se cumplan todas:
  - `direction_score >= 55`;
  - `technical_score >= 70`;
  - `reward_distance_pct < 3`;
  - sin zona pendiente negativa;
  - sin EMA/timeframe principal contra el lado.

No aplicar como cambio automatico al historico.

### 2. Direction score como filtro primario

Reglas candidatas:

- `direction_score < 40`: penalizacion fuerte de TP, subida de SL y decision `observar`.
- `direction_score 40-50`: no permitir que RR alto mejore setup grade.
- `direction_score >= 50`: mantener lectura normal.

### 3. Penalizar RR alto sin camino claro

Reglas candidatas:

- Si `risk_reward_ratio >= 3` y `target_path_quality` no es alta, penalizar.
- Si `risk_reward_ratio >= 3` y `reward_distance_pct >= 3`, degradar decision.
- Si `risk_reward_ratio >= 2` con `direction_score < 50`, tratar como falsa calidad.

### 4. Penalizar distancias extremas

Reglas candidatas:

- `risk_distance_pct < 0.25`: stop dentro de ruido; subir `execution_risk`.
- `risk_distance_pct >= 3`: riesgo excesivo/plan amplio; subir `risk_level`.
- `reward_distance_pct >= 3`: TP poco alcanzable salvo tendencia fuerte multi-TF y camino limpio.

### 5. Subir peso de contexto direccional real

Medidores que deben ganar peso como filtros negativos:

- `ticker_24h.price_change_pct` contra el lado.
- `15m ema_stack` contra el lado.
- `1h ema_stack` contra el lado.
- `15m price_vs_ema_21_pct` contra el lado.
- `1h price_vs_ema_21_pct` contra el lado.

No deben usarse como senales positivas fuertes por si solas; su valor principal esta en advertir contradiccion.

### 6. Endurecer ordenes pendientes

Reglas candidatas:

- `entry_order_type = stop_breakdown`: exigir confirmacion adicional obligatoria.
- `zone_probability_context.probability_adjustment < 0`: degradar decision.
- `liquidity_sweep_risk = alto`: subir riesgo y bajar confianza.
- `reaction_bias = falsa_ruptura_riesgo`: penalizar TP y subir SL.

Confirmacion adicional sugerida para permitir stop breakdown:

- direccion >= 55;
- technical_score >= 70;
- ruptura alineada con 15m y 1h;
- taker/flujo no contrario;
- TP no lejano;
- sin riesgo de barrida alto.

### 7. Mantener Fibonacci secundario

Reglas candidatas:

- No aumentar caps de Fibonacci.
- No premiar `fibonacci_context.bias = favorable` de forma directa.
- Si `target_zone = extension` y `reward_distance_pct >= 3`, considerar TP ambicioso.
- Usar Fibonacci solo para explicar zonas y confluencias, no para validar direccion.

### 8. Revisar operation quality y expected value

Antes de usar estos scores como filtros:

- Quitar premio automatico por RR alto.
- Penalizar TP lejano sin camino tecnico.
- Separar EV monetaria de probabilidad direccional.
- Evitar que `expected_value_score >= 70` eleve confianza si SL/direccion/zona son malas.

## Orden recomendado de implementacion futura

1. Documentar estas hipotesis como candidatas de v0.10.
2. Crear tests unitarios para cada regla de riesgo.
3. Implementar ajustes pequenos y trazables en `analysis_engine.py`.
4. Actualizar `ENGINE_VERSION`.
5. Registrar cambio en `HISTORIAL_CAMBIOS_MOTOR_ANALISIS.md`.
6. Validar sintaxis y tests.
7. Probar analisis reales en local.
8. No tocar operaciones cerradas ni aprendizaje historico.
9. Auditar de nuevo tras 30-50 operaciones nuevas con v0.10.

## Decision final de auditoria

Estado de hipotesis: pendientes, no aplicadas.

Conclusiones principales:

- El motor debe volverse mas conservador.
- La mejora mas rentable esta en bloquear o degradar operaciones con riesgo estructural.
- `sl_probability`, `direction_score`, contexto EMA/ticker, distancia TP/SL y zona pendiente son los medidores mas utiles.
- Order book, CVD y Fibonacci no justifican mas peso actualmente.
- EV y operation quality necesitan revision antes de usarse como argumentos fuertes.

La recomendacion tecnica es preparar una version `rules-v0.10-risk-gated-calibration` centrada en filtros de riesgo, no en aumentar senales positivas.
