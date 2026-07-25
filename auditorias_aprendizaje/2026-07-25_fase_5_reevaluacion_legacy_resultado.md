# Fase 5 - Resultado de reevaluacion legacy append-only

Fecha: 2026-07-25
Estado: COMPLETADA
Version: `legacy-review-v0.1-modern-taxonomy`

## 1. Objetivo cerrado

Se aplico la taxonomia moderna a todas las evaluaciones legacy existentes sin
modificar su contenido original. El universo real fue de 232 casos, no de los
190 estimados al redactar el plan.

La reevaluacion se almacena en `learning_legacy_reevaluations` y conserva por
separado:

- datos conocidos antes de la operacion;
- resultados observados despues;
- etiquetas diagnosticas retrospectivas;
- interpretacion y versiones originales;
- ausencias explicitas y motivo de cada ausencia;
- hash SHA-256 del bundle fuente.

## 2. Reconciliacion

Estado final en Supabase:

| Control | Resultado |
|---|---:|
| Evaluaciones totales | 234 |
| Evaluaciones legacy | 232 |
| Revisiones legacy creadas | 232 |
| Operaciones unicas revisadas | 232 |
| Revisiones descriptivas | 231 |
| Revisiones excluidas | 1 |
| Duplicados | 0 |
| Errores de aplicacion | 0 |

Distribucion reconstruida:

| Outcome moderno | Casos |
|---|---:|
| `sl_first` | 127 |
| `tp_first` | 84 |
| `expiry_unresolved` | 20 |
| `ambiguous` | 1 |

Los 232 registros contienen `pre_trade_features`, `post_trade_outcomes` y
`diagnostic_labels`.

## 3. Integridad e idempotencia

Antes y despues de la aplicacion:

```text
learning_evaluations: 234 -> 234
evaluaciones legacy: 232 -> 232
MD5 canonico de evaluaciones: 9d66cc74e6cdf435291e69597895178e
revisiones append-only: 0 -> 232
```

La segunda ejecucion completa produjo:

```text
candidatas: 232
procesadas: 0
aplicadas: 0
omitidas por idempotencia: 232
errores: 0
conciliacion: correcta
```

UPDATE y DELETE fueron probados contra una fila piloto y quedaron bloqueados.
La tabla tiene RLS activo, no concede acceso a `anon` ni `authenticated`, y el
rol de servicio solo dispone de SELECT e INSERT.

## 4. Calidad y uso permitido

Las 232 revisiones son utiles para:

- describir el comportamiento historico de reglas y versiones;
- localizar incoherencias y generar hipotesis;
- estudiar fallos, excursiones MFE/MAE y resultado economico normalizado;
- comparar cohortes legacy sin fingir que eran equivalentes.

Ninguna queda autorizada para calibrar directamente el challenger. En los 232
casos falta la duracion concreta del horizonte registrada antes de la
operacion. Utilizar el cierre observado como horizonte predictivo introduciria
informacion futura.

Esta limitacion no descarta los datos: determina que su peso es descriptivo y
que la validacion predictiva debe realizarse con operaciones modernas cuyo
contrato pre-trade sea completo.

## 5. Evidencias

- `2026-07-25_fase_5_taxonomia_legacy.md`
- `2026-07-25_fase_5_dry_run_completo.json`
- `2026-07-25_fase_5_apply_operacion_1.json`
- `2026-07-25_fase_5_idempotencia_operacion_1.json`
- `2026-07-25_fase_5_apply_completo.json`
- `2026-07-25_fase_5_idempotencia_completa.json`
- `tests/test_legacy_reevaluation.py`

## 6. Cambios expresamente no realizados

- No se modifico el champion.
- No se modificaron formulas, scores ni probabilidades visibles.
- No se promovio ninguna regla.
- No se crearon operaciones sombra ficticias.
- No se sobrescribio ninguna evaluacion historica.

## 7. Siguiente fase

La Fase 6 queda desbloqueada: ejecutar champion y challenger sobre las mismas
operaciones reales, manteniendo el challenger en sombra, con feature flag,
kill switch, trazabilidad dual y reversion determinista.
