# Fase 6 - Contrato de ejecucion dual y reversion

Fecha: 2026-07-26
Estado: VIGENTE
Champion congelado: `rules-v0.12.1-liquidations-readable`
Scoring congelado: `scoring-v0.11-underweighted-risk-cluster`
Challenger: `challenger-v0.1-contract-only`

## 1. Objetivo

Cada nuevo analisis real debe conservar la salida del champion y ejecutar un
carril challenger independiente. El carril sombra registra una prediccion
solo cuando existe un artefacto entrenado, calibrado y aprobado. En cualquier
otro caso registra el bloqueo exacto y no inventa probabilidades.

La ejecucion sombra:

- no crea operaciones;
- no modifica TP, SL, margen, apalancamiento ni entrada;
- no modifica probabilidades, grado, riesgo, confianza ni decision champion;
- no aparece como recomendacion alternativa para el usuario;
- no puede promocionarse automaticamente a produccion.

## 2. Baseline F6.1

Estado de Supabase al inicio:

- 884 analisis reales;
- 246 analisis vinculados a operaciones;
- 27 analisis con contrato de datos versionado;
- 9 analisis de `app-v0.16.0-legacy-append-only`;
- 0 ejecuciones sombra persistidas;
- 0 artefactos challenger aprobados.

E1.5 ya implementa el evaluador, invariantes, trazabilidad matematica y
bloqueos. No estaba conectado a `app.py` ni a la base de datos.

## 3. Horizonte exacto

No se introduce un selector de horas ni se recupera la propuesta descartada de
3 a 60 horas. Se mantienen los tres marcos de la aplicacion y se fija un
vencimiento reproducible en su limite superior:

| Marco | Ventana vigente | Vencimiento de evaluacion |
|---|---|---:|
| `intraday_short` | 30 min-4 h | 14.400 segundos |
| `intraday_wide` | 4-24 h | 86.400 segundos |
| `short_swing` | 1-7 dias | 604.800 segundos |

El vencimiento queda registrado antes de la operacion en el snapshot y en la
traza sombra. Asi, TP, SL y `expiry_unresolved` tienen una etiqueta futura
inequivoca sin usar la hora real de cierre como dato predictivo.

## 4. Persistencia append-only

Se crean tres registros internos:

1. `challenger_model_artifacts`
   - artefacto completo, hash, version y estado de despliegue;
   - una version no puede sobrescribirse.
2. `challenger_shadow_config_events`
   - cada seleccion, apagado o rollback es un evento nuevo;
   - el estado vigente es el ultimo evento;
   - conserva evento y modelo anteriores, motivo y responsable.
3. `challenger_shadow_runs`
   - una comparacion por analisis y configuracion;
   - champion, challenger, plan, features y comparacion separados;
   - `production_effect` siempre es `none`.

Las tres tablas son privadas. RLS queda activo, `anon` y `authenticated` no
tienen privilegios y UPDATE/DELETE quedan bloqueados.

## 5. Estado seguro inicial

La configuracion inicial es:

```json
{
  "enabled": false,
  "selected_model_version": null,
  "action": "initialize_disabled"
}
```

Por tanto, el primer resultado sombra esperado es:

```text
status = blocked
block_code = shadow_disabled
probabilities = null
production_effect = none
```

Activar el carril sin modelo seleccionado debe producir
`shadow_model_not_selected`. Seleccionar una version inexistente o no aprobada
queda prohibido.

## 6. Kill switch y rollback

No se expone un endpoint publico de administracion. Una herramienta local
auditada inserta eventos append-only:

- `disable`: apaga inmediatamente el carril sombra;
- `select`: selecciona y activa un artefacto registrado en estado `shadow`;
- `rollback`: copia exactamente el estado de un evento anterior en un evento
  nuevo y conserva el objetivo de reversion.

El rollback no borra historia. La salida del usuario sigue siendo el champion
en todos los estados.

## 7. Aislamiento de fallos

La recomendacion champion se guarda primero. La ejecucion sombra usa un
savepoint independiente:

- si el challenger funciona, se guarda su comparacion;
- si se bloquea por contrato, se guarda el bloqueo;
- si falla tecnicamente, se revierte solo el savepoint sombra y la
  recomendacion champion permanece disponible.

Un fallo de persistencia sombra debe quedar en logs, pero no puede convertir un
analisis champion valido en error para el usuario.

## 8. Condiciones para producir porcentajes challenger

No existe todavia un artefacto valido. Fase 6 no autoriza fabricar uno con la
muestra insuficiente actual.

Para producir porcentajes debe existir un artefacto que supere:

- identidad, dataset, codigo y corte temporal versionados;
- matriz de admisibilidad exacta;
- train, calibracion y test cronologicos;
- soporte declarado por par y horizonte;
- calibracion multinomial;
- invariantes de distancia y horizonte;
- aprobacion humana para estado `shadow`.

Hasta entonces, la ausencia de porcentaje es un resultado correcto y
auditable.

## 9. Criterios de salida

- cada nuevo analisis genera una traza sombra o un error aislado verificable;
- desactivar el carril deja exactamente la salida champion;
- seleccionar y revertir configuracion es determinista y append-only;
- ningun registro sombra puede actualizarse ni borrarse;
- no se crean operaciones sombra;
- pruebas cubren prediccion, bloqueo, kill switch, rollback e idempotencia;
- Supabase, aplicacion local y despliegue online quedan verificados.
