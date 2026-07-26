# Fase 6 - Resultado champion, challenger y reversion

Fecha: 2026-07-26
Estado: COMPLETADA
Runtime: `challenger-shadow-runtime-v0.1`
Challenger: `challenger-v0.1-contract-only`

## 1. Objetivo cerrado

El evaluador challenger definido en E1.5 ya esta conectado a cada nuevo
analisis real. Su ejecucion, persistencia y administracion estan aisladas del
champion.

La respuesta servida al usuario sigue siendo:

```text
rules-v0.12.1-liquidations-readable
scoring-v0.11-underweighted-risk-cluster
```

No se modificaron formulas, probabilidades, TP, SL, grado, riesgo, confianza ni
decision del champion.

## 2. Horizonte pre-trade

Cada analisis nuevo registra antes de la operacion:

- `analysis_at`;
- `evaluation_horizon_seconds`;
- `evaluation_expires_at`;
- `evaluation_horizon_policy`.
- contexto de activacion de la orden pendiente o de mercado.

Se mantienen los tres marcos de producto:

| Marco | Vencimiento exacto |
|---|---:|
| `intraday_short` | 4 horas |
| `intraday_wide` | 24 horas |
| `short_swing` | 7 dias |

Esto permite etiquetar `tp_first`, `sl_first` o `expiry_unresolved` sin usar la
hora real de cierre como informacion predictiva.

## 3. Ejecucion dual

`/api/analyze` realiza ahora:

1. calculo champion sin cambios;
2. guardado de la recomendacion champion;
3. savepoint independiente;
4. lectura del ultimo evento de configuracion;
5. validacion de artefacto, matriz, plan y features;
6. calculo o bloqueo challenger;
7. registro append-only de la comparacion.

Un error tecnico revierte solo el savepoint sombra. El analisis champion sigue
disponible y el error queda en logs.

## 4. Persistencia y seguridad

Se aplico en Supabase la migracion:

`create_phase_6_challenger_shadow_runtime`

Tablas:

- `challenger_model_artifacts`;
- `challenger_shadow_config_events`;
- `challenger_shadow_runs`.

Verificacion por tabla:

- RLS activo;
- 0 privilegios para `anon`;
- 0 privilegios para `authenticated`;
- `service_role`: solo SELECT e INSERT;
- 2 reglas append-only: sin UPDATE ni DELETE;
- claves foraneas nuevas cubiertas por indices.

Los intentos de actualizar y borrar el evento inicial no tuvieron efecto.

## 5. Kill switch y rollback

La prueba durable en produccion genero:

| Evento | Accion | Estado |
|---:|---|---|
| 1 | `initialize_disabled` | apagado |
| 2 | `kill_switch_disable` | apagado |
| 3 | `rollback`, objetivo evento 1 | apagado |

El rollback creo historia nueva, no borro eventos, y restauro exactamente el
estado del evento inicial.

La herramienta privada es:

```powershell
.\.venv\Scripts\python.exe manage_challenger_shadow.py status
.\.venv\Scripts\python.exe manage_challenger_shadow.py disable --reason "..." --requested-by "..."
.\.venv\Scripts\python.exe manage_challenger_shadow.py select --model-version "..." --reason "..." --requested-by "..."
.\.venv\Scripts\python.exe manage_challenger_shadow.py rollback --reason "..." --requested-by "..."
```

No existe endpoint publico de administracion.

## 6. Canaria transaccional

`verify_shadow_runtime_canary.py` inserto dentro de una transaccion una
recomendacion y su traza, comprobo:

```text
challenger_status = blocked
block_code = shadow_disabled
production_effect = none
```

Despues revirtio la transaccion. Comprobacion final:

```text
recomendaciones canarias persistidas = 0
trazas canarias persistidas = 0
rollback_verified = true
```

No se crearon operaciones sombra.

## 7. Auditoria accesible

El endpoint autenticado:

`GET /api/learning/challenger-audit`

devuelve para el usuario:

- configuracion vigente;
- conteo de predicciones y bloqueos;
- violaciones de `production_effect`;
- comparaciones recientes;
- champion y challenger separados;
- plan, modelo y motivo de bloqueo.

No expone el artefacto interno completo ni permite administrarlo.

## 8. Estado probabilistico real

Estado al cierre:

```text
artefactos registrados = 0
challenger habilitado = false
predicciones challenger reales = 0
```

Por ello, los nuevos analisis registraran inicialmente:

```text
status = blocked
block_code = shadow_disabled
probabilities = null
```

Esto no es un fallo ni una falta de calculo: evita fabricar porcentajes sin un
modelo entrenado, calibrado y validado temporalmente.

Las pruebas con un artefacto sintetico valido demuestran que el carril puede
producir tres probabilidades coherentes, trazar cada contribucion y seguir
sirviendo exclusivamente el champion. El artefacto sintetico no se registro en
Supabase.

## 9. Verificacion

- 132/132 pruebas superadas;
- compilacion Python correcta;
- canaria Supabase correcta;
- asesores de seguridad y rendimiento revisados;
- 0 cambios en `analysis_engine.py`;
- matriz de admisibilidad y hashes del champion intactos.

## 10. Siguiente fase

La Fase 7 queda estructuralmente desbloqueada, pero su gate estadistico no se
ha alcanzado. Debe acumular casos posteriores a esta definicion, comparables y
con outcome completo, antes de entrenar, calibrar y evaluar un artefacto.

Minimos vigentes:

- 50 casos nuevos comparables;
- al menos 10 `tp_first`;
- al menos 10 `sl_first`;
- separacion cronologica de train, calibracion y test;
- resultados por par y horizonte.
