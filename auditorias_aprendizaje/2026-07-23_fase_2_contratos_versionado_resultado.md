# Fase 2 - Contratos de datos y versionado

Fecha: 2026-07-23  
Estado: COMPLETADA
Commit de entrada: `50e1ce0737370c774d0694f1d6288769e0d28b5b`  
Commit funcional: `814755fea5f37cc8cf0123a6a350149cfed98b31`

## 1. Objetivo autorizado

Separar los datos conocidos antes de operar de los resultados y etiquetas
retrospectivas, y versionar de forma independiente aplicacion, scoring,
esquema de aprendizaje y fuentes de datos.

## 2. Versiones establecidas

| Dimension | Version |
|---|---|
| Aplicacion | `app-v0.13.0-data-contracts` |
| Motor historico visible | `rules-v0.12.1-liquidations-readable` |
| Scoring estadistico | `scoring-v0.11-underweighted-risk-cluster` |
| Evaluador | `learning-v0.2-underweighted-risk` |
| Esquema de aprendizaje | `learning-schema-v0.3-pre-post-diagnostics` |
| Fuentes | `data-sources-v0.12.1-binance-hyperperps` |
| Contrato de datos | `data-contract-v0.1` |

Las versiones 0.12 y 0.12.1 no cambiaron el scoring. Por eso los analisis que
usen esas aplicaciones permanecen en la cohorte estadistica de scoring 0.11.

## 3. Alcance ejecutado

- Registro central de versiones en `versioning.py`.
- Contrato con `pre_trade_features`, `post_trade_outcomes` y
  `diagnostic_labels`.
- Lector predictivo que solo entrega `pre_trade_features`.
- Persistencia de versiones en recomendaciones y evaluaciones.
- Endpoint publico `/api/version` con versionado y SHA de Railway.
- Lectura compatible de snapshots antiguos.
- Conservacion temporal de campos legacy usados por los informes existentes.
- Pruebas de no fuga, compatibilidad, cohortes e INSERT SQL.

## 4. Base de datos

Columnas nuevas y anulables:

- `recommendations`: `app_version`, `scoring_version`,
  `learning_schema_version`, `data_source_version`,
  `data_contract_version`.
- `learning_evaluations`: las cinco anteriores y
  `learning_evaluator_version`.

Reconciliacion:

| Indicador | Antes | Despues |
|---|---:|---:|
| Recomendaciones | 857 | 857 |
| Operaciones | 243 | 243 |
| Operaciones cerradas | 232 | 232 |
| Evaluaciones | 232 | 232 |
| Recomendaciones historicas versionadas artificialmente | 0 | 0 |
| Evaluaciones historicas versionadas artificialmente | 0 | 0 |
| Columnas nuevas | 0 | 11 |

No se hizo backfill. Las columnas historicas permanecen nulas y la lectura
compatible infiere el scoring solo para versiones conocidas 0.11/0.12, sin
reescribir la base.

## 5. Prevencion de fuga

`pre_trade_features` incluye:

- Plan propuesto.
- Contexto de entrada solicitado.
- Probabilidades, riesgo, confianza y decision.
- Tecnico, regimen, Fibonacci y zonas conocidos en el analisis.
- Versiones de origen.

Quedan fuera:

- Activacion real.
- Motivo y precio de cierre.
- PnL.
- MFE y MAE.
- Resultado del plan.
- Contrafactual manual.
- Veredicto, leccion, tipo de fallo y diagnosticos retrospectivos.

El lector `predictive_features_from_contract` devuelve exclusivamente una
copia de `pre_trade_features`.

## 6. Pruebas

- Compilacion Python: correcta.
- Suite completa: 38/38.
- No fuga retrospectiva recursiva: correcta.
- Cohortes por scoring, no por app: correcta.
- Registro legacy sin versiones nuevas: legible.
- INSERT de recomendacion: 24 columnas y 24 parametros.
- INSERT de evaluacion: 44 columnas y 44 parametros.
- Scoring y decisiones existentes: sin cambios; pruebas previas verdes.

Prueba local:

| Componente | Resultado |
|---|---|
| Arranque completo | Correcto |
| `/api/version` | 200 |
| `/api/price?symbol=BTCUSDT&record=false` | 200 |
| `/api/diagnostics/binance-futures?symbol=BTCUSDT` | 200 |
| Precio Binance no obsoleto | Correcto |

Prueba online de Railway:

| Componente | Resultado |
|---|---|
| Commit servido por `/api/version` | `814755fea5f37cc8cf0123a6a350149cfed98b31` |
| Entorno | `production` |
| Servicio | `SIMULADOR-Y-MOTOR-ANALISIS_V1` |
| Portada | 200 |
| `/api/version` | 200 |
| Precio BTC Binance Futures | 200, no obsoleto |
| Diagnostico Binance Futures | 200 |

## 7. Casos excluidos

- No se reetiquetaron las 857 recomendaciones antiguas.
- No se regeneraron las 232 evaluaciones existentes.
- No se aplico el esquema moderno a casos legacy; corresponde a la fase 5.
- No se cambiaron pesos, probabilidades, TP, SL, riesgo o decision.

## 8. Riesgos y limitaciones

- Los registros anteriores carecen de `app_version` y `data_source_version`
  verificables; se mantienen como desconocidos.
- Los campos legacy mezclados siguen presentes para compatibilidad, pero no son
  el contrato autorizado para futuros consumidores predictivos.
- La separacion contractual evita fuga accidental, pero cualquier futuro
  modelo debera usar expresamente el lector predictivo probado.

## 9. Reversion

El codigo puede revertirse sin transformar datos. Las columnas son anulables y
pueden permanecer sin uso; no es necesario eliminarlas para volver al
comportamiento anterior.

## 10. Criterios de aceptacion

| Criterio | Resultado |
|---|---|
| Analisis predictivo limitado a `pre_trade_features` | Cumplido |
| App y scoring versionados de forma independiente | Cumplido |
| Misma regla de scoring comparte cohorte | Cumplido |
| Registros existentes legibles | Cumplido |
| Sin backfill destructivo | Cumplido |
| Suite completa verde | Cumplido |
| Railway verificado | Cumplido |

## 11. Decision de cierre

Decision: COMPLETADA.

Siguiente fase desbloqueada, pero no iniciada: Fase 3 - Reconstruccion MFE/MAE.

Aprobacion del usuario para iniciar la fase 3: pendiente.
