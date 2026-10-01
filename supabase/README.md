# Supabase online database

Proyecto Supabase:

- Project ref: `hfjygvdcmdgnjqugegfg`
- URL: `https://hfjygvdcmdgnjqugegfg.supabase.co`
- Base: PostgreSQL

## Objetivo

La version online de la app usa Supabase PostgreSQL como base principal.
SQLite queda solo como origen temporal para migrar datos locales existentes.

## Archivos

- `schema.sql`: esquema versionado de tablas, relaciones e indices.
- `../migrate_sqlite_to_postgres.py`: migra datos locales a Supabase.
- `../validate_migration_counts.py`: valida conteos SQLite vs Supabase.
- `../backfill_legacy_reevaluations.py`: genera y aplica revisiones legacy
  append-only, con dry-run e idempotencia.
- `../manage_challenger_shadow.py`: registra artefactos y administra seleccion,
  kill switch y rollback mediante eventos append-only.
- `../verify_shadow_runtime_canary.py`: valida el recorrido sombra dentro de
  una transaccion que siempre se revierte.
- `../limit_learning_persistence.py`: compacta y deduplica los tres eventos de
  una operacion LIMIT seleccionada antes de cualquier escritura.
- `../run_counterfactual_learning.py`: reconstruye TP/SL/expiracion para
  analisis a mercado sin operacion y persiste solo evidencia compacta.
- `../run_counterfactual_episode_grouping.py`: crea una foto de auditoria que
  agrupa intervalos de mercado solapados y reparte su peso estadistico.
- `../audit_counterfactual_rule_evidence.py`: cruza esa foto con las ablaciones
  y trazas de reglas, siempre separadas por horizonte y contrato de motor.

## Flujo

1. Aplicar `schema.sql` en Supabase.
2. Migrar datos desde `data/trading_trainer.db`.
3. Validar conteos.
4. Configurar `SUPABASE_DATABASE_URL` en el servidor de la app.
5. Arrancar la app en modo produccion.

## Seguridad

El backend usa conexion privada a PostgreSQL. No se usa Supabase Auth, anon key ni cliente publico desde navegador en esta fase.

Las tablas internas tienen RLS activo y no conceden privilegios a `anon` ni
`authenticated`. Antes de exponer cualquier cliente Supabase en frontend, hay
que definir politicas RLS por usuario y rol.

`learning_legacy_reevaluations` es una excepcion deliberadamente privada: usa
RLS, revoca acceso a `anon` y `authenticated`, limita `service_role` a SELECT e
INSERT y bloquea UPDATE/DELETE para preservar la auditoria.

Las tablas `challenger_model_artifacts`,
`challenger_shadow_config_events` y `challenger_shadow_runs` siguen el mismo
modelo privado append-only. La administracion del challenger se realiza desde
backend o CLI, nunca desde el navegador.

`limit_learning_snapshots` conserva como maximo tres filas compactas por
operacion LIMIT seleccionada. El esquema limita la colocacion a 50 casos por dia
UTC y rechaza payloads que excedan el presupuesto del evento.

`recommendation_counterfactual_evaluations` conserva resultados historicos
append-only sin crear operaciones ficticias ni almacenar velas completas. El
payload de variables reconstruidas tiene un limite de 4 KiB por analisis.
Los casos exactos y los proxies legacy quedan separados mediante
`contract_quality` y `formal_learning_eligible`; los proxies nunca obtienen
peso formal ni alteran produccion. Se revisan con:

```powershell
python run_counterfactual_learning.py --contract-mode legacy_proxy
```

`counterfactual_episode_grouping_runs` y
`counterfactual_episode_memberships` conservan fotos append-only solicitadas
de forma manual, no un proceso continuo. Cada analisis sigue presente, pero
los que comparten un intervalo futuro solapado reparten un peso total de 1 por
episodio. El bloque UTC se conserva para el bootstrap definido en M8 y el peso
formal solo incluye contratos exactos evaluados:

```powershell
python run_counterfactual_episode_grouping.py --persist
```

La auditoria posterior de reglas es solo lectura para Supabase y escribe sus
artefactos versionados en `auditorias_motor/`. Exige 50 episodios efectivos y
10 unidades efectivas por clase antes de ejecutar inferencia formal:

```powershell
python audit_counterfactual_rule_evidence.py
```

`operation_observation_sessions` agrupa todos los controles de una misma
operacion (`404o`). Cada control futuro (`404o1`, `404o2`, etc.) guarda su
recomendacion completa en `recommendations` con
`analysis_type = 'operation_observation'` y una referencia compacta e inmutable
en `operation_observation_checkpoints`. Asi se puede comparar con los analisis
de apertura sin contarlo como una nueva operacion independiente.

Las reconstrucciones historicas incompletas, como la de la operacion 404, se
marcan `reconstructed_partial` y nunca entran en las metricas formales. Las
decisiones hipoteticas de cierre se conservan aparte en
`operation_exit_counterfactuals`; ninguna de estas tablas cambia reglas,
probabilidades ni operaciones de produccion.

El monitor de observacion consulta una vista compacta de esos controles para
mostrar, debajo de la grafica de la operacion, la evolucion TP/SL, PnL, reglas
principales y observacionales, y los candidatos de cierre. Pausar y reanudar
conserva la sesion; finalizarla detiene definitivamente nuevos controles sin
cerrar la operacion. Cada cambio queda registrado de forma append-only en
`operation_observation_session_events`. El monitor es informativo: no cierra
operaciones ni modifica la probabilidad calculada por el motor.

## Auditoria compacta de escaneos de bots

`autonomous_scan_runs.candidate_audit_json` guarda todos los resultados escalares
del escaneo en su misma fila: alternativas, confirmacion final e intentos sin
datos. El contrato `autonomous-scan-audit-v1` incluye niveles y probabilidades sin
redondear, soporte historico, elegibilidad, motivo de descarte y los umbrales
vigentes. Los nombres de campos se guardan una sola vez; no incluye velas,
snapshots ni trazas de reglas. Este registro no tiene limite diario de analisis.
El muestreo detallado de `autonomous_candidate_observations` sigue independiente,
sin multiplicar los trabajos de evaluacion ni sus descargas historicas.

`GET /api/bots/scan-audit` permite a MauricioMC consultar manualmente un bot,
`start_at` y `end_at` con zona horaria, y paginas de 6 escaneos (maximo 12).
`before_id` recibe el `next_cursor` de la pagina anterior. La consulta no lee
snapshots, no hace analisis nuevos ni se incorpora al refresco periodico de la
app. Los escaneos anteriores a la migracion muestran `coverage=legacy_sample`
y el numero de propuestas cuyo resultado no fue conservado; no se reconstruyen
como si fueran resultados originales.
