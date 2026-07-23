# Fase 1 - Madurez de senales

Fecha: 2026-07-23  
Estado: COMPLETADA  
Commit de entrada: `0902416aec20ab993134f5936e4405f1b023fd2c`  
Commit de salida: commit funcional de esta fase

## 1. Objetivo autorizado

Evitar que una senal con tres casos sea presentada como filtro candidato y
separar madurez estadistica de interpretacion observada.

## 2. Alcance ejecutado

- Nueva clasificacion de madurez por numero de casos.
- Requisito minimo de exitos y fallos para validacion.
- Separacion entre `learning_read` y `pattern_read`.
- Gate de validacion explicito en los informes.
- Ordenacion por madurez y despues por patron observado.
- Pruebas de limites y de separacion conceptual.

## 3. Cambios realizados

### Archivos

- `app.py`
- `tests/test_pending_zone_analysis.py`
- Plan maestro e informe de esta fase.

### Base de datos

Ningun cambio de esquema o datos. La clasificacion se calcula al generar el
informe.

### Endpoints e interfaz

Los informes de riesgo infraponderado ahora devuelven:

- `learning_read`: madurez estadistica.
- `pattern_read`: riesgo, ganador o contexto mixto observado.
- `validation_gate`: minimos y elegibilidad.

No existian consumidores visibles en `app.js` o `index.html` de las etiquetas
retiradas.

### Scoring

Ningun cambio. `ENGINE_VERSION` permanece:
`rules-v0.12.1-liquidations-readable`.

## 4. Evidencias

### Pruebas

- Pruebas especificas de aprendizaje: 8/8.
- Suite completa: 31/31.
- Compilacion Python: correcta.
- Busqueda de etiquetas antiguas en codigo e interfaz: sin coincidencias.

### Limites comprobados

| Casos | Exitos | Fallos | Resultado |
|---:|---:|---:|---|
| 9 | 4 | 5 | `early_observation` |
| 10 | 5 | 5 | `signal_to_monitor` |
| 29 | 14 | 15 | `signal_to_monitor` |
| 30 | 15 | 15 | `candidate_for_formal_review` |
| 49 | 24 | 25 | `candidate_for_formal_review` |
| 50 | 9 | 41 | `candidate_for_formal_review` |
| 50 | 40 | 10 | `eligible_for_validation` |

### Datos reales

Se evaluaron 189 grupos de senales existentes.

Antes:

| Etiqueta | Grupos |
|---|---:|
| `candidate_risk_filter` | 42 |
| `mixed_context_needs_review` | 26 |
| `sample_too_small` | 115 |
| `ambiguous_or_winner_signal` | 6 |

Despues:

| Madurez | Grupos |
|---|---:|
| `early_observation` | 189 |
| `signal_to_monitor` | 0 |
| `candidate_for_formal_review` | 0 |
| `eligible_for_validation` | 0 |

El grupo mas numeroso tiene 9 casos.

Interpretacion preservada:

| Patron observado | Grupos |
|---|---:|
| `observed_risk_pattern` | 93 |
| `observed_winner_pattern` | 53 |
| `mixed_context_needs_review` | 43 |

## 5. Metricas antes y despues

| Metrica | Antes | Despues | Diferencia |
|---|---:|---:|---:|
| Filtros candidatos con muestra actual | 42 | 0 | -42 |
| Grupos elegibles para validacion | No existia gate | 0 | Gate incorporado |
| Casos minimos para candidatura formal | 3 | 30 | +27 |
| Casos minimos para elegibilidad | 3 | 50 | +47 |
| Minimo de exitos/fallos | No exigido | 10/10 | Incorporado |

## 6. Casos excluidos

Ninguno. Todos los grupos conservan su interpretacion observada aunque no
alcancen madurez suficiente.

## 7. Riesgos y limitaciones

- Ninguna senal actual supera 9 casos.
- La madurez no demuestra utilidad predictiva; solo autoriza avanzar a la
  siguiente etapa de revision.
- La elegibilidad no activa produccion y seguira requiriendo validacion
  temporal en la fase 7.

## 8. Reversion

Revertir el commit funcional de esta fase restaura las etiquetas anteriores.
No requiere reversion de base de datos.

## 9. Criterios de aceptacion

| Criterio | Resultado | Evidencia |
|---|---|---|
| Menos de 50 no es elegible | Cumplido | Pruebas de limites |
| Minimo 10 exitos y 10 fallos | Cumplido | Casos 50/9/41 y 50/40/10 |
| Interpretacion preservada | Cumplido | Campo `pattern_read` |
| Scoring sin cambios | Cumplido | `ENGINE_VERSION` intacta |
| Sin cambios de datos | Cumplido | Diff y consultas |
| Suite completa verde | Cumplido | 31/31 |

## 10. Decision de cierre

Decision: COMPLETADA  
Siguiente fase desbloqueada: Fase 2 - Contratos de datos y versionado  
Aprobacion del usuario: pendiente de aceptar el cierre y autorizar fase 2

