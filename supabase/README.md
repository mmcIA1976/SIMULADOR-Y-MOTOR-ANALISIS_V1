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

## Flujo

1. Aplicar `schema.sql` en Supabase.
2. Migrar datos desde `data/trading_trainer.db`.
3. Validar conteos.
4. Configurar `SUPABASE_DATABASE_URL` en el servidor de la app.
5. Arrancar la app en modo produccion.

## Seguridad inicial

El backend usa conexion privada a PostgreSQL. No se usa Supabase Auth, anon key ni cliente publico desde navegador en esta fase.

RLS esta desactivado inicialmente porque habilitarlo sin politicas bloquearia el acceso de la app. Antes de exponer cualquier cliente Supabase en frontend, hay que definir politicas RLS por usuario y rol.

`learning_legacy_reevaluations` es una excepcion deliberadamente privada: usa
RLS, revoca acceso a `anon` y `authenticated`, limita `service_role` a SELECT e
INSERT y bloquea UPDATE/DELETE para preservar la auditoria.
