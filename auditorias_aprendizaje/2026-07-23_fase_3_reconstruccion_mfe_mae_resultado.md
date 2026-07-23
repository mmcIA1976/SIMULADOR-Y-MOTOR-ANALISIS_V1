# Fase 3 - Reconstruccion historica MFE/MAE

Fecha: 2026-07-23
Estado: EN CURSO - PENDIENTE DE DESPLIEGUE
Commit de entrada: `4f2fdade5359305a0534f5809779330b10c7d62c`

## 1. Objetivo autorizado

Sustituir los recorridos incompletos basados en ticks de la aplicacion por
evidencia reproducible de Binance USD-M Futures a un minuto, sin reescribir las
etiquetas historicas ni ocultar los casos ambiguos.

Esta fase no autoriza cambios de scoring, probabilidades, TP, SL, riesgo,
decision o grado del setup.

## 2. Implementacion

- Reconstruccion desde la apertura hasta el cierre o fin de observacion.
- Calculo direccional de MFE y MAE para largos y cortos.
- Recorridos separados durante la operacion, plan completo y poscierre manual.
- Primer toque de TP/SL y resultado reconstruido separado del resultado
  historico.
- Calidad, cobertura, ventana, fuente, huella SHA-256 y limitaciones por caso.
- Resolucion mediante trades agregados cuando Binance aun conserva el dato.
- Marca explicita para velas ambiguas o de borde.
- Backfill con simulacion, aplicacion, auditoria antes/despues e idempotencia.

Versiones:

| Dimension | Version |
|---|---|
| Aplicacion | `app-v0.14.0-historical-evidence` |
| Motor de scoring | `scoring-v0.11-underweighted-risk-cluster` |
| Esquema de aprendizaje | `learning-schema-v0.4-historical-evidence` |
| Contrato de datos | `data-contract-v0.2-historical-evidence` |
| Reconstruccion | `evidence-v0.1-binance-usdm-1m` |

El scoring champion permanece sin cambios.

## 3. Fuente y reproducibilidad

Fuente principal:

- Binance USD-M Futures, velas de 1 minuto.
- Endpoint oficial: `GET /fapi/v1/klines`.
- Trades agregados recientes: `GET /fapi/v1/aggTrades`.

Cada evidencia conserva:

- Inicio y fin solicitados.
- Primera y ultima vela obtenidas.
- Velas esperadas y obtenidas.
- Ratio de cobertura.
- Huella SHA-256 del conjunto normalizado.
- Fecha y version de reconstruccion.

Limitacion oficial: los trades agregados consultados por tiempo solo permiten
historico reciente. Por ello no puede conocerse el orden intravela de extremos
antiguos cuando TP y SL aparecen en la misma vela.

## 4. Base de datos

Se anadieron columnas anulables de evidencia a `learning_evaluations` y la tabla
append-only `learning_evidence_reconstructions`, unica por operacion y version
de reconstruccion.

Reconciliacion final:

| Indicador | Valor |
|---|---:|
| Operaciones cerradas evaluables | 232 |
| Evaluaciones | 232 |
| Evaluaciones con fuente | 232 |
| Evaluaciones con calidad | 232 |
| Evidencias estructuradas | 232 |
| Registros individuales de auditoria | 232 |
| Copias del recorrido legacy preservadas | 232 |
| Etiquetas historicas modificadas | 0 |

Calidad:

| Calidad | Casos |
|---|---:|
| `complete_1m` | 23 |
| `complete_1m_with_boundary_approximation` | 209 |
| Parcial o no disponible | 0 |

Resolucion del recorrido:

| Estado | Casos |
|---|---:|
| `resolved` | 211 |
| `no_plan_touch` | 20 |
| `ambiguous_same_candle` | 1 |

## 5. Diferencias detectadas

El MFE/MAE fue recalculado en los 232 casos porque el dato anterior dependia de
ticks incompletos o muestreos de cierre. El valor anterior se conserva en
`legacy_tick_excursion`.

El resultado reconstruido coincide con la evaluacion original en 211 casos,
difiere en 20 y queda ambiguo en 1:

- Diferencias: `4, 58, 81, 93, 97, 98, 99, 100, 101, 105, 106, 107, 114,
  123, 130, 172, 177, 190, 217, 227`.
- Ambigua: `121`.
- Sin toque de plan verificable: `29, 68, 96, 97, 98, 99, 101, 105, 106,
  107, 123, 126, 130, 143, 149, 158, 159, 185, 186, 209`.

Las diferencias no se han usado para sobrescribir `plan_result`,
`analysis_verdict` ni `failure_type`. Se guardan en
`reconstructed_plan_result` y `plan_result_consistency` para la reevaluacion
append-only de la Fase 5.

Parte de las discrepancias procede de cierres antiguos respaldados por Binance
Spot; la reconstruccion usa el mercado correcto de la operacion, Binance USD-M
Futures.

## 6. Evidencias generadas

- `2026-07-23_fase_3_dry_run_muestra.json`
- `2026-07-23_fase_3_dry_run_completo.json`
- `2026-07-23_fase_3_apply_operacion_1.json`
- `2026-07-23_fase_3_apply_completo.json`
- `2026-07-23_fase_3_verificacion_idempotencia.json`

La primera aplicacion controlada proceso solo la operacion 1. La aplicacion
completa proceso las 231 restantes, sin errores.

La repeticion posterior encontro 232 candidatos, salto los 232 por version,
proceso 0 y aplico 0. El backfill es idempotente.

## 7. Pruebas

- Compilacion Python: correcta.
- Suite completa: 47/47.
- MFE/MAE de largos y cortos: correcto.
- Cobertura incompleta: marcada como parcial.
- TP y SL en la misma vela antigua: ambiguo.
- Trades agregados recientes: orden de toque resuelto.
- Vela de borde: no presentada como certeza.
- Observacion manual: recorrido poscierre separado.
- Cierre registrado por vela: limite temporal corregido.
- Preservacion legacy e idempotencia estructurada: correctas.
- SQL de evaluacion: 62 columnas y parametros alineados.

Prueba local:

| Componente | Resultado |
|---|---|
| Arranque completo | Correcto |
| `/api/version` | 200, app 0.14 y evidencia 0.1 |
| `/api/price?symbol=BTCUSDT&record=false` | 200, fuente USD-M Futures no obsoleta |
| `/api/diagnostics/binance-futures?symbol=BTCUSDT` | 200 |

## 8. Riesgos y limitaciones

- Una vela de un minuto no revela el orden entre su maximo y minimo.
- Las velas de apertura y cierre pueden incluir segundos fuera de la operacion;
  esos 209 casos se etiquetan con aproximacion de borde.
- Los 20 desacuerdos son evidencia para revisar, no autorizacion para cambiar
  el motor ni para declarar incorrecta la etiqueta original.
- La reconstruccion de una evaluacion nueva requiere consultar su ventana
  historica; puede anadir latencia puntual al cierre, pero no recalcula las ya
  versionadas.

## 9. Reversion

- El scoring no necesita reversion porque no cambio.
- Las columnas son anulables y compatibles con la version anterior.
- La evaluacion original y su recorrido previo permanecen disponibles.
- La tabla de auditoria conserva el antes/despues por operacion y version.
- El codigo puede dejar de consumir la evidencia sin borrar datos.

## 10. Criterios de salida

| Criterio | Resultado |
|---|---|
| 100% con `evidence_source` y `evidence_quality` | Cumplido |
| Reconciliacion individual de diferencias | Cumplido |
| Informe antes/despues | Cumplido |
| Ambiguedades visibles | Cumplido |
| Backfill idempotente | Cumplido |
| Etiquetas originales preservadas | Cumplido |
| Suite completa verde | Cumplido |
| Verificacion local | Cumplido |
| Commit publicado en `main` | Pendiente |
| Railway sirve el commit exacto | Pendiente |

## 11. Decision de cierre

Decision provisional: RECONSTRUCCION VALIDADA; DESPLIEGUE PENDIENTE.

La Fase 4 no se inicia hasta completar y aprobar este cierre.
