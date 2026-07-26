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
