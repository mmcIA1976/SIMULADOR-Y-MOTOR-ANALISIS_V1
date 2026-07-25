# Fase 5 - Contrato de reevaluacion legacy append-only

Fecha: 2026-07-25
Estado: VIGENTE
Version: `legacy-review-v0.1-modern-taxonomy`

## 1. Universo

Una evaluacion es legacy cuando carece de `learning_schema_version` o
`data_contract_version` registrado. El conteo se obtiene de la base actual y
no de cifras historicas del plan.

Baseline F5.1:

- evaluaciones totales: 234;
- evaluaciones legacy: 232;
- evaluaciones modernas: 2;
- legacy con recomendacion y snapshot: 232;
- legacy con evidencia historica completa: 232;
- legacy con normalizacion economica: 232.

## 2. Inmutabilidad

No se actualiza `learning_evaluations`. Cada caso crea una fila nueva en
`learning_legacy_reevaluations`, identificada por:

```text
operation_id + reevaluation_version
```

La fila conserva:

- evaluacion y operacion de origen;
- version original registrada, incluso cuando es nula;
- version de reevaluacion;
- timestamps de origen y revision;
- SHA-256 canonico del bundle de fuentes;
- interpretacion legacy;
- contrato moderno;
- ausencias;
- elegibilidad predictiva.

Una misma version no puede insertarse dos veces. UPDATE y DELETE quedan
bloqueados mediante reglas de base de datos.

## 3. Separacion moderna

Cada revision contiene:

- `pre_trade_features`;
- `post_trade_outcomes`;
- `diagnostic_labels`.

Los datos retrospectivos no pueden aparecer dentro de `pre_trade_features`.
Las probabilidades antiguas se renombran como scores heuristicos legacy; no se
reinterpretan como probabilidades calibradas.

## 4. Ausencias

No se rellenan campos ausentes con defaults actuales. Cada ausencia usa:

```json
{
  "status": "not_available",
  "reason": "motivo verificable",
  "source_checked": "fuente revisada"
}
```

En particular:

- un horizonte que no existe en el snapshot pre-trade no se obtiene de una
  columna rellenada posteriormente;
- la duracion concreta del horizonte se marca ausente en los 232 casos;
- versiones no registradas permanecen ausentes;
- contextos de ordenes pendientes no existentes no se inventan.

## 5. Outcome moderno

La taxonomia de primera barrera es:

| Reconstruccion | Clase moderna |
|---|---|
| `plan_success` | `tp_first` |
| `plan_failure` | `sl_first` |
| `plan_unresolved` | `expiry_unresolved` |
| `plan_would_succeed` | `tp_first`, observado tras cierre manual |
| `plan_would_fail` | `sl_first`, observado tras cierre manual |
| `contest_expiry_mark_to_market` | `expiry_unresolved` |
| `ambiguous_same_candle` | `ambiguous`, excluido |

La etiqueta legacy y la reconstruida se conservan simultaneamente. Una
discrepancia no sobrescribe ninguna de las dos.

## 6. Uso permitido

Los casos legacy pueden utilizarse para:

- aprendizaje descriptivo;
- auditoria de reglas historicas;
- generacion de hipotesis;
- analisis de calidad de datos;
- comparaciones separadas por version del engine.

No se autorizan directamente para calibrar el challenger E1.5 porque no
registraron una duracion concreta del horizonte pre-trade. Esta limitacion se
guarda por caso como `predictive_eligibility`.

## 7. Reconciliacion obligatoria

El proceso debe demostrar:

```text
procesadas + idempotentes + errores = candidatas
```

Criterios de cierre:

- 232 casos insertados o justificados individualmente;
- 0 actualizaciones de evaluaciones originales;
- 0 duplicados por version;
- 0 fugas retrospectivas;
- 211 consistencias, 20 discrepancias y 1 ambiguedad preservadas;
- segunda ejecucion con 232 skips idempotentes;
- RLS, revocaciones y reglas append-only verificadas.
