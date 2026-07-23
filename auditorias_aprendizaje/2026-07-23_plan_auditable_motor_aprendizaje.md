# Plan auditable del motor de aprendizaje

Fecha de propuesta: 2026-07-23  
Estado general: ACTIVO Y APROBADO  
Motor champion congelado: `rules-v0.12.1-liquidations-readable`  
Commit de partida: `5135245`

## 1. Objetivo

Mejorar la calidad del aprendizaje y la validacion del motor sin introducir
cambios de scoring basados en muestras pequenas, datos incompletos o resultados
usados fuera de contexto.

Este plan no autoriza por si mismo ninguna modificacion de probabilidades,
riesgo, TP, SL, decision o grado del setup.

## 2. Reglas de ejecucion

1. Solo puede existir una fase en curso.
2. No se inicia una fase hasta aprobar el cierre de la anterior.
3. Cada fase debe tener un commit propio y un alcance identificable.
4. No se mezclan refactorizaciones o mejoras ajenas al objetivo de la fase.
5. Toda migracion debe ser compatible hacia atras y tener procedimiento de
   reversion.
6. Los backfills deben ser idempotentes y generar un informe antes/despues.
7. Ningun dato retrospectivo puede convertirse en variable pre-trade.
8. Los cambios de aprendizaje no modifican produccion automaticamente.
9. No se cambia el scoring champion antes de la fase 7.
10. Una fase desplegada debe verificarse en local, base de datos y Railway.

## 3. Evidencias obligatorias por fase

Cada cierre de fase debe registrar:

- Objetivo y alcance real ejecutado.
- Archivos, tablas y endpoints modificados.
- Estado Git anterior y posterior.
- Pruebas ejecutadas y resultados.
- Reconciliacion de conteos de base de datos.
- Metricas antes y despues.
- Casos excluidos y motivo.
- Riesgos o limitaciones que permanezcan.
- Commit publicado en `main`.
- Estado del despliegue online.
- Decision: aprobada, rechazada o requiere correccion.

Los informes se guardaran en `auditorias_aprendizaje/` con el formato:

`AAAA-MM-DD_fase_N_nombre_resultado.md`

## 4. Baseline inicial

Datos observados el 2026-07-23:

| Indicador | Valor |
|---|---:|
| Recomendaciones registradas | 857 |
| Evaluaciones de aprendizaje | 232 |
| Evaluaciones legacy | 190 |
| Evaluaciones `learning-v0.2-underweighted-risk` | 42 |
| Operaciones de concurso | 171 |
| Operaciones de entrenamiento | 72 |
| Cerradas de concurso | 163 |
| Cerradas de entrenamiento | 69 |
| Cerradas sin evaluacion | 0 |
| Evaluaciones duplicadas | 0 |
| Evaluaciones con menos de 5 ticks | 5 |
| Apalancamiento observado | 1x a 10x |
| Margen observado | 20 a 799,98 |
| Analisis v0.12 con liquidaciones | 69 |
| Mapas de liquidaciones validos | 67 |
| Casos de liquidaciones resueltos | 17 |
| Precision provisional del mapa | 25% |

Estos valores se volveran a consultar al abrir cada fase. Una variacion natural
por nuevas operaciones no invalida el baseline, pero debe quedar documentada.

## 5. Fases

### Fase 0 - Baseline y gobernanza

Estado: COMPLETADA

Objetivo:

- Congelar el scoring champion.
- Adoptar este documento como contrato de ejecucion.
- Crear la plantilla comun de informe por fase.
- Confirmar que `main` esta limpio y coincide con produccion.

Permitido:

- Documentacion, consultas de auditoria y plantilla de informes.

Prohibido:

- Cambios de codigo, esquema, datos o scoring.

Criterio de salida:

- Baseline reconciliado.
- Documento aprobado por el usuario.
- Plan y plantilla versionados en Git.

### Fase 1 - Madurez de senales

Estado: COMPLETADA

Objetivo:

- Evitar que tres casos reciban el nombre `candidate_risk_filter`.

Clasificacion propuesta:

| Muestra | Estado |
|---|---|
| Menos de 10 | `early_observation` |
| 10 a 29 | `signal_to_monitor` |
| 30 a 49 | `candidate_for_formal_review` |
| 50 o mas y minimo 10/10 | `eligible_for_validation` |

Alcance:

- Etiquetas, ordenacion de informes, interfaz y pruebas.

Prohibido:

- Cambiar pesos o decisiones del motor.

Criterio de salida:

- Ninguna senal con menos de 50 casos aparece como elegible.
- Pruebas de limites 9/10, 29/30 y 49/50.

### Fase 2 - Contratos de datos y versionado

Estado: EN CURSO - VERIFICACION DE DESPLIEGUE

Objetivo:

- Separar datos disponibles antes de operar de etiquetas posteriores.
- Evitar fragmentar muestras por cambios visuales o tecnicos.

Versiones obligatorias:

- `app_version`
- `scoring_version`
- `learning_schema_version`
- `data_source_version`

Categorias de datos:

- `pre_trade_features`
- `post_trade_outcomes`
- `diagnostic_labels`

Alcance:

- Estructura, persistencia, compatibilidad y pruebas de no fuga.

Criterio de salida:

- El analisis solo puede consumir `pre_trade_features`.
- Dos versiones de app con el mismo scoring comparten cohorte estadistica.
- Los registros existentes siguen siendo legibles.

### Fase 3 - Reconstruccion MFE/MAE

Objetivo:

- Sustituir recorridos incompletos por evidencia reproducible de Binance
  Futures.

Alcance:

- Velas de 1 minuto desde apertura hasta cierre u horizonte de observacion.
- MFE, MAE, TP/SL, recorrido posterior y calidad de evidencia.
- Marca `ambiguous_same_candle` cuando no pueda conocerse el primer toque.
- Backfill idempotente.

Prohibido:

- Cambiar el resultado para ocultar ambiguedades.
- Usar velas posteriores al horizonte evaluado.

Criterio de salida:

- 100% de evaluaciones con `evidence_source` y `evidence_quality`.
- Reconciliacion individual de todos los resultados que cambien.
- Informe de diferencias antes/despues.

### Fase 4 - Metricas economicas normalizadas

Objetivo:

- Separar calidad de senal de margen, apalancamiento y usuario.

Metricas:

- R-multiple.
- Retorno sin apalancar.
- Retorno sobre margen.
- Resultado TP/SL.
- Drawdown acumulado.
- PnL absoluto conservado como metrica secundaria.

Segmentos:

- Concurso y entrenamiento.
- Cierre automatico y manual.
- Usuario, lado, horizonte y scoring version.

Criterio de salida:

- Ninguna comparacion de senales depende solo de PnL absoluto.
- Casos sin riesgo inicial valido quedan excluidos con motivo explicito.

### Fase 5 - Reevaluacion legacy append-only

Objetivo:

- Aplicar la taxonomia moderna a las 190 evaluaciones antiguas sin destruir la
  interpretacion original.

Alcance:

- Revisiones inmutables vinculadas a `operation_id`.
- Version original, nueva version y fecha de reevaluacion.
- Campos ausentes marcados como `not_available`.

Prohibido:

- Sobrescribir silenciosamente la evaluacion original.
- Inventar features que el analisis antiguo no registro.

Criterio de salida:

- 190 casos procesados o justificados individualmente.
- Conteos antes/despues reconciliados.
- Reejecucion sin duplicados.

### Fase 6 - Champion, challenger y reversion

Objetivo:

- Calcular nuevas reglas sin permitir que intervengan en produccion.

Alcance:

- Champion actual congelado.
- Challenger calculado sobre las mismas operaciones reales.
- Registro de ambas probabilidades y decisiones.
- Feature flag, kill switch y rollback.

No se crearan operaciones sombra para los 857 analisis.

Criterio de salida:

- Desactivar el challenger restaura exactamente el champion.
- El challenger no altera TP, SL, scoring ni decision visible.
- Pruebas deterministas de activacion y reversion.

### Fase 7 - Validacion temporal

Objetivo:

- Decidir con evidencia fuera de muestra si un challenger puede sustituir al
  champion.

Minimos:

- 50 operaciones nuevas comparables.
- Al menos 10 exitos y 10 fallos.
- Casos posteriores a la definicion del challenger.

Metricas:

- Brier score.
- Log-loss.
- Curva de calibracion.
- R-multiple.
- Drawdown.
- Intervalos de confianza.
- Resultados por lado y horizonte.

Regla de activacion:

- No basta con mejorar PnL.
- Debe mejorar calibracion o riesgo sin deterioro material en las demas
  metricas.
- La activacion requiere aprobacion humana explicita y una nueva
  `scoring_version`.

Criterio de salida:

- Challenger aprobado, rechazado o prolongado con motivo cuantificado.

### Fase 8 - Liquidaciones y multi-exchange

Objetivo:

- Validar el mapa Hyperliquid y estudiar un mapa estimado de Binance/Bybit.

Condiciones previas:

- Fases 0 a 7 cerradas.
- Pipeline champion/challenger operativo.

Alcance:

- Hyperliquid permanece como `real_onchain`.
- Binance/Bybit se etiquetan `estimated_from_oi`.
- Fuentes, antiguedad, cobertura y confianza visibles.
- Sin scoring inicial.

Gate de revision:

- 30 casos permiten auditoria formal.
- 50 casos comparables y 10/10 permiten validacion.
- Ajuste inicial maximo, si se aprueba: +/-2 o 3 puntos.

Criterio de salida:

- Comparacion fuera de muestra contra el champion.
- Kill switch probado.
- Decision documentada de activar, mantener en sombra o retirar.

## 6. Estado de seguimiento

| Fase | Estado | Commit | Informe | Aprobacion |
|---|---|---|---|---|
| 0 | Completada | Commit documental de fase 0 | `2026-07-23_fase_0_baseline_gobernanza_resultado.md` | Aprobada |
| 1 | Completada | `50e1ce0` | `2026-07-23_fase_1_madurez_senales_resultado.md` | Aprobada |
| 2 | En curso | Pendiente de publicar | `2026-07-23_fase_2_contratos_versionado_resultado.md` | Verificacion local completada |
| 3 | Bloqueada por fase 2 | - | - | - |
| 4 | Bloqueada por fase 3 | - | - | - |
| 5 | Bloqueada por fase 4 | - | - | - |
| 6 | Bloqueada por fase 5 | - | - | - |
| 7 | Bloqueada por fase 6 | - | - | - |
| 8 | Bloqueada por fase 7 | - | - | - |

## 7. Cambios al plan

Cualquier cambio de alcance debe registrarse en este documento antes de
implementarse, indicando:

- Motivo.
- Fase afectada.
- Riesgo nuevo.
- Criterio de aceptacion actualizado.
- Aprobacion del usuario.
