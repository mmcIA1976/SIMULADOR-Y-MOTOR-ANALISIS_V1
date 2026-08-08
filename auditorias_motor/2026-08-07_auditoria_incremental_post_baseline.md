# Auditoria incremental posterior al baseline

Fecha: 2026-08-07T17:38:26.165217+00:00

## Alcance

Esta auditoria conserva sin cambios el baseline del 30 de julio y evalua exclusivamente las operaciones cerradas que no estaban incluidas en aquel artefacto.

- Operaciones del baseline: 244.
- Operaciones incrementales encontradas: 42.
- Horizontes exactos preoperacion: 42.
- Casos resueltos utilizables: 38.
- Casos ambiguos o excluidos: 4.
- Operaciones cerradas originalmente por v0.5: 0.

Todos los modelos se comparan contra la misma reconstruccion de primera barrera con velas cerradas de un minuto.

## Resultados agregados

| Modelo | N | Brier | Log-loss | Acierto principal |
|---|---:|---:|---:|---:|
| v0.4 servido | 38 | 0.382817 | 0.572392 | 76.32% |
| M6 global congelado | 38 | 0.372968 | 0.561942 | 76.32% |
| v0.5 nucleo por horizonte | 38 | 0.383914 | 0.580799 | 78.95% |
| v0.5 completo | 38 | 0.394406 | 0.591334 | 76.32% |

## Resultados por horizonte

### intraday_short

| Modelo | N | Brier | Log-loss | Acierto principal |
|---|---:|---:|---:|---:|
| v0.4 servido | 12 | 0.263213 | 0.391871 | 75.00% |
| M6 global congelado | 12 | 0.263816 | 0.395098 | 75.00% |
| v0.5 nucleo por horizonte | 12 | 0.268420 | 0.408501 | 83.33% |
| v0.5 completo | 12 | 0.267519 | 0.404448 | 83.33% |

### intraday_wide

| Modelo | N | Brier | Log-loss | Acierto principal |
|---|---:|---:|---:|---:|
| v0.4 servido | 15 | 0.385299 | 0.594753 | 80.00% |
| M6 global congelado | 15 | 0.388258 | 0.599968 | 80.00% |
| v0.5 nucleo por horizonte | 15 | 0.375855 | 0.580893 | 80.00% |
| v0.5 completo | 15 | 0.373473 | 0.575992 | 80.00% |

### short_swing

| Modelo | N | Brier | Log-loss | Acierto principal |
|---|---:|---:|---:|---:|
| v0.4 servido | 11 | 0.509910 | 0.738831 | 72.73% |
| M6 global congelado | 11 | 0.471192 | 0.692099 | 72.73% |
| v0.5 nucleo por horizonte | 11 | 0.520898 | 0.768632 | 72.73% |
| v0.5 completo | 11 | 0.561375 | 0.816131 | 63.64% |

## Comparaciones directas

Los deltas son candidato menos referencia. Un valor negativo en Brier o log-loss significa menor error.

| Candidato | Referencia | Delta Brier | Delta log-loss | Delta acierto |
|---|---|---:|---:|---:|
| M6 global congelado | v0.4 servido | -0.009850 | -0.010450 | +0.00% |
| v0.5 nucleo por horizonte | M6 global congelado | +0.010947 | +0.018857 | +2.63% |
| v0.5 completo | M6 global congelado | +0.021439 | +0.029392 | +0.00% |
| v0.5 completo | v0.5 nucleo por horizonte | +0.010492 | +0.010535 | -2.63% |

## Hallazgos

- Frente al nucleo M6 global, v0.5 completo aumenta el Brier en +0.021439 y el log-loss en +0.029392.
- En el bootstrap por bloques de calendario, el intervalo del 95 % para el empeoramiento de log-loss de v0.5 completo es [+0.004389, +0.063037].
- v0.5 mejora la muestra intraday_wide, pero empeora intraday_short y especialmente short_swing frente al nucleo M6 global. La calibracion no mejora de forma consistente los tres marcos temporales.
- Los overlays de v0.5 empeoran su propio nucleo en +0.010535 de log-loss y +0.010492 de Brier en el agregado.
- La evidencia de aprendizaje almacenada coincide con la reconstruccion exacta en 31 casos, discrepa en 1 y no es comparable en 10.
- La discrepancia es la operacion #263: el aprendizaje la corto como `no_plan_touch` tras el cierre manual, pero la observacion hasta el vencimiento exacto registro SL primero en 2026-08-04T23:18:00+00:00.

## Lectura metodologica

El menor log-loss observado en este incremento corresponde a **M6 global congelado**. Esto describe la muestra; no autoriza automaticamente una promocion.

La salida v0.4 es evidencia preoperacion real. El nucleo M6 global ya estaba congelado antes del primer caso incremental y se reproduce sobre trazas preoperacion exactas. v0.5 fue creado despues de estos casos, por lo que sus dos columnas son replay retrospectivo, aunque no utilicen datos posteriores a cada entrada.

No existe todavia ninguna operacion cerrada cuya recomendacion original proceda de v0.5. Por ello esta auditoria no autoriza declarar v0.5 validado ni sustituir el baseline historico.

## Decision

- Promocion automatica de v0.5: **NO**.
- Cambios de pesos derivados de esta muestra: **NO**.
- Modificaciones en Supabase o produccion: **NINGUNA**.
- Siguiente evidencia necesaria: operaciones cerradas analizadas originalmente por v0.5, evaluadas por horizonte y sin recalibrar el motor durante la cohorte.
