# Fase 4 - Metricas economicas normalizadas

Fecha: 2026-07-24
Estado: EN CURSO - PENDIENTE DE DESPLIEGUE
Commit de entrada: `42596ef79efd961124e93aa238ae5fcf9c3ad9de`

## 1. Objetivo autorizado

Separar la calidad de la senal del margen, apalancamiento, usuario y modalidad.
El PnL absoluto se conserva, pero deja de ser la unica medida economica usada
para comparar patrones.

Esta fase no autoriza cambios de scoring, probabilidades, TP, SL, riesgo,
decision o grado del setup.

## 2. Contrato economico

Metricas principales:

- `r_multiple`: PnL real dividido por riesgo monetario inicial.
- `unleveraged_return_pct`: variacion de precio equivalente sin apalancamiento.
- `margin_return_pct`: PnL dividido por margen.
- `economic_plan_outcome`: resultado TP, SL, ambiguo, no resuelto o mark-to-market.
- `max_cumulative_r_drawdown`: perdida maxima desde un pico de la curva
  acumulada de R.

Metricas secundarias:

- `economic_final_pnl`: PnL actual de la operacion usado por la normalizacion.
- `total_pnl` y `avg_pnl`: conservados en informes con
  `pnl_metric_role = secondary`.

Formula:

`riesgo inicial = margen * apalancamiento * distancia entrada-stop`

`R = economic_final_pnl / riesgo inicial`

Una operacion se excluye si lado, entrada, margen, apalancamiento, stop, PnL o
direccion adversa del stop no permiten calcular un riesgo inicial valido. El
motivo queda en `economic_exclusion_reason`.

## 3. Versiones

| Dimension | Version |
|---|---|
| Aplicacion | `app-v0.15.0-economic-normalization` |
| Motor champion | `rules-v0.12.1-liquidations-readable` |
| Scoring champion | `scoring-v0.11-underweighted-risk-cluster` |
| Esquema de aprendizaje | `learning-schema-v0.5-economic-normalization` |
| Contrato de datos | `data-contract-v0.3-economic-normalization` |
| Normalizacion | `economics-v0.1-risk-normalized` |

El scoring champion permanece sin cambios.

## 4. Base de datos y seguridad

Se anadieron columnas anulables a `learning_evaluations` y la tabla de auditoria
`learning_economic_normalizations`, unica por operacion y version.

Las columnas numericas nuevas usan `DOUBLE PRECISION`. Las tablas internas
`learning_evidence_reconstructions` y `learning_economic_normalizations` tienen
RLS habilitado y privilegios revocados para `anon` y `authenticated`.

Asesores de Supabase:

- Seguridad: solo avisos informativos por RLS sin politicas. Es el diseno
  esperado para tablas internas sin acceso cliente.
- Rendimiento: se anadieron los indices de `evaluation_id` que faltaban en las
  dos tablas de auditoria. Los avisos restantes son preexistentes o indices
  nuevos todavia sin uso.
- Referencias: [RLS sin politica](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
  e [indices de claves foraneas](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys).

Entorno verificado:

| Indicador | Valor |
|---|---|
| PostgreSQL Supabase | 17.6 |
| Evaluaciones antes del backfill | 234 |
| Filas economicas antes del backfill | 0 |
| Auditorias economicas antes del backfill | 0 |

## 5. Backfill y reconciliacion

Resultado final:

| Indicador | Valor |
|---|---:|
| Evaluaciones | 234 |
| Incluidas | 234 |
| Excluidas | 0 |
| R ausente | 0 |
| Errores de formula | 0 |
| Registros individuales de auditoria | 234 |
| Operaciones auditadas distintas | 234 |
| Fugas economicas a `pre_trade_features` | 0 |
| Etiquetas estructuradas modificadas | 0 |

Tipos de cierre:

| Tipo | Casos |
|---|---:|
| Automatico TP/SL | 192 |
| Manual | 40 |
| Fin de concurso | 2 |

Resultado economico del plan:

| Resultado | Casos |
|---|---:|
| Stop loss | 128 |
| Take profit | 85 |
| No resuelto | 18 |
| Mark-to-market | 2 |
| Ambiguo | 1 |

Idempotencia final:

- Candidatos: 234.
- Procesados: 0.
- Aplicados: 0.
- Saltados por version: 234.
- Errores: 0.

## 6. Metricas globales

| Metrica | Resultado |
|---|---:|
| R medio | -0,02755165 |
| R mediano | -0,99999178 |
| R acumulado | -6,44708583 |
| Retorno sin apalancar medio | -0,25916129% |
| Retorno sobre margen medio | -2,77637154% |
| Drawdown maximo acumulado | 21,80319701 R |
| PnL total secundario | -2404,7275 USDT |

Ejemplo de la distorsion corregida:

- La cohorte `scoring-v0.11-underweighted-risk-cluster` tiene 39 casos.
- Su PnL total es negativo: -228,7919 USDT.
- Su R medio es positivo: +0,11254631 R.

El PnL bruto daba mas peso a operaciones con mayor margen. R muestra el
resultado en relacion con el riesgo que cada operacion asumio.

## 7. Discrepancia historica preservada

La operacion 81 presenta dos valores distintos:

| Fuente | PnL |
|---|---:|
| Evaluacion historica | -36,5448 |
| Operacion actual | +147,5291 |
| `economic_final_pnl` | +147,5291 |
| R normalizado | +4,03693715 |

No se sobrescribio `learning_evaluations.final_pnl`. La normalizacion conserva
el dato historico y registra explicitamente el PnL actual que utiliza. La Fase 5
podra estudiar la causa mediante una revision append-only.

## 8. Informes actualizados

- Auditoria economica: `/api/learning/economic-audit`.
- Fibonacci.
- Zonas de entrada.
- Riesgo subponderado.
- Liquidaciones.
- Efectividad de senales y pares de senales.

Cuando existe muestra, los informes incluyen:

- R medio, mediano y acumulado.
- Retorno sin apalancar.
- Retorno sobre margen.
- Drawdown acumulado en R.
- Casos incluidos y excluidos.
- Resultado TP/SL.
- PnL marcado como secundario.

Segmentos disponibles:

- Concurso y entrenamiento.
- Automatico, manual y fin de concurso.
- Usuario.
- Lado.
- Horizonte.
- Version de scoring.

Los informes se ejecutaron contra los seis usuarios con evaluaciones. No se
produjeron errores de consulta ni respuestas incompatibles.

## 9. Evidencias generadas

- `2026-07-24_fase_4_dry_run_completo.json`
- `2026-07-24_fase_4_apply_operacion_1.json`
- `2026-07-24_fase_4_idempotencia_operacion_1.json`
- `2026-07-24_fase_4_apply_completo.json`
- `2026-07-24_fase_4_apply_reconciliacion_pnl.json`
- `2026-07-24_fase_4_verificacion_idempotencia.json`

## 10. Pruebas

- Suite completa: 58/58.
- Compilacion Python: correcta.
- Largos y cortos: correcto.
- Independencia de margen y apalancamiento: correcta.
- Exclusiones con motivo: correctas.
- Resultado TP/SL: correcto.
- Drawdown acumulado sobre R: correcto.
- PnL economico frente a PnL legacy: correcto.
- Serializacion de timestamps PostgreSQL: correcta.
- Sin fuga a `pre_trade_features`: correcto.
- INSERT de evaluacion: 76 columnas y parametros alineados.
- Informes reales de seis usuarios: correctos.

Prueba local:

| Componente | Resultado |
|---|---|
| Arranque completo | Correcto |
| `/api/version` | 200, app 0.15 y normalizacion 0.1 |
| `/api/price?symbol=BTCUSDT&record=false` | 200, USD-M Futures no obsoleto |
| `/api/diagnostics/binance-futures?symbol=BTCUSDT` | 200 |
| `/api/learning/economic-audit` sin sesion | 401 esperado |
| `/api/learning/economic-audit` con sesion local | 200 |
| Usuario de prueba | 117 evaluaciones, 117 normalizadas, 0 excluidas |
| Roles del informe | Economia principal, PnL secundario |

## 11. Riesgos y limitaciones

- R evalua el resultado real frente al stop inicial; no convierte cierres
  manuales en resultados del plan. Por eso se segmentan por tipo de cierre.
- Los 18 planes no resueltos, el ambiguo y los dos mark-to-market no deben
  mezclarse con TP/SL al estimar tasa de exito.
- Drawdown en R es una medida normalizada, no sustituye el drawdown monetario de
  una cartera real.
- Las cohortes legacy se infieren por version de motor sin reescribir su
  `scoring_version` historico.

## 12. Reversion

- El scoring no necesita reversion porque no cambio.
- Las columnas nuevas son anulables.
- El PnL y las etiquetas historicas no fueron sobrescritos.
- La tabla de auditoria conserva antes, despues, version y metricas.
- Los informes anteriores siguen recibiendo `total_pnl` y `avg_pnl`.

## 13. Criterios de salida

| Criterio | Resultado |
|---|---|
| Ninguna comparacion depende solo del PnL absoluto | Cumplido |
| Casos sin riesgo valido excluidos con motivo | Cumplido; 0 casos actuales |
| Segmentacion completa | Cumplido |
| Backfill individual e idempotente | Cumplido |
| PnL historico preservado | Cumplido |
| Scoring champion congelado | Cumplido |
| Suite completa verde | Cumplido |
| Verificacion local | Cumplido |
| Commit publicado en `main` | Pendiente |
| Railway sirve el commit exacto | Pendiente |

## 14. Decision de cierre

Decision provisional: IMPLEMENTACION Y DATOS VALIDADOS; DESPLIEGUE PENDIENTE.

La Fase 5 no se inicia hasta completar y aprobar este cierre.
