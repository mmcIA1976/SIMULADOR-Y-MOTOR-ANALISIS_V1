# Trading Trainer Learning Model v1

Simulador educativo multiusuario para analizar, registrar y auditar operaciones crypto con datos de mercado reales. No ejecuta ordenes reales, no conecta con cuentas de exchange y no solicita claves API privadas.

## Norte estrategico

El documento [`NORTE_ESTRATEGICO_AUTONOMIA.md`](NORTE_ESTRATEGICO_AUTONOMIA.md) fija el objetivo real del proyecto: evolucionar desde simulador asistido por usuario hacia motor autonomo de analisis, simulacion, aprendizaje y futura base de bot.

Antes de priorizar nuevas mejoras, contrastar la tarea contra ese documento. La prioridad actual es fiabilidad operativa autonoma, auditoria historica y aprendizaje limpio.

Para cualquier cambio del motor de analisis prevalece el
[`CONTRATO_FASE_1_MOTOR_ANALISIS.md`](CONTRATO_FASE_1_MOTOR_ANALISIS.md).
Define el objetivo TP/SL, la ficha obligatoria de cada regla, la trazabilidad por
analisis, las reglas combinadas y la funcion exacta del aprendizaje. La
[`COBERTURA_ANALITICA_FASE_1.md`](COBERTURA_ANALITICA_FASE_1.md) registra los 34
bloques de analisis objetivo y el estado real de los datos actuales.

La auditoria extraordinaria mantiene congelado el champion mientras se
documenta y prueba. E1.1 inventario sus reglas, E1.2 registro su procedencia y
E1.3 demostro sus incoherencias matematicas mediante
[`auditorias_motor/informe_coherencia_motor.md`](auditorias_motor/informe_coherencia_motor.md).
E1.4 midio su impacto historico mediante
[`auditorias_motor/informe_impacto_historico_reglas.md`](auditorias_motor/informe_impacto_historico_reglas.md).
E1.5 separo datos calculables de afirmaciones predictivas, fijo el contrato
probabilistico y dejo un challenger aislado que se bloquea sin modelo calibrado:
[`auditorias_motor/contrato_challenger_alcanzabilidad.md`](auditorias_motor/contrato_challenger_alcanzabilidad.md).
La auditoria E1 esta completada. La Fase 5 tambien esta cerrada: las 232
evaluaciones legacy se conservaron y reinterpretaron en revisiones append-only
sin autorizar su uso para calibracion predictiva directa. El resultado esta en
[`auditorias_aprendizaje/2026-07-25_fase_5_reevaluacion_legacy_resultado.md`](auditorias_aprendizaje/2026-07-25_fase_5_reevaluacion_legacy_resultado.md).
La siguiente fase, aun no iniciada, es la Fase 6 de ejecucion paralela
champion/challenger con reversion.

## Estado actual

- Registro/login local con cookie de sesion.
- Avatar guardado en base de datos.
- Simulacion de operaciones BTC/USDT y otros pares Binance USD-M Futures usando endpoints publicos.
- Maximo de 2 operaciones abiertas por usuario y modo.
- Carteras separadas para entrenamiento y concurso mensual.
- Recarga automatica de entrenamiento en bloques ficticios de 1000 USDT cuando el usuario agota el saldo libre. Cada recarga queda registrada en `wallet_events` como `training_recharge`.
- Motor de analisis por temporalidad: intradia corto, intradia amplio y swing corto.
- Ordenes pendientes simuladas con activacion por nivel: pullback limite, ruptura y breakdown.
- Motor v0.9 con analisis de zonas pendientes, aprendizaje estructurado y auditoria agregada.
- Registro de recomendaciones, ticks de precio, cierres, observacion y conclusiones de aprendizaje.
- Reevaluacion legacy append-only con 232 revisiones historicas separadas de las evaluaciones fuente.
- La app online usa Supabase PostgreSQL. El entorno local se usa solo para desarrollo y puede conectar con Supabase si esta configurado.

## Desarrollo local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8766
```

Abre `http://127.0.0.1:8766`.

Nota: en este proyecto, el arranque local usado para desarrollo puede conectar con Supabase durante el startup. Si trabajas desde Codex/local, usa el procedimiento local acordado y no subas archivos auxiliares locales.

## Variables de entorno

Copia `.env.example` como referencia:

```text
DATABASE_URL=sqlite:///data/trading_trainer.db
SUPABASE_DATABASE_URL=postgresql://USER:PASS@HOST:5432/postgres
TRADING_TRAINER_SECRET=change-me-before-production
```

Para produccion, `TRADING_TRAINER_SECRET` debe ser una clave larga y privada. La version online debe usar `SUPABASE_DATABASE_URL`; SQLite queda como entorno local o fuente temporal de migracion.

## Despliegue

El proyecto incluye `Procfile` y `runtime.txt` para facilitar el salto a servidor:

```text
web: uvicorn app:app --host 0.0.0.0 --port ${PORT:-8766}
```

Antes de publicar:

- No subir `.venv/`, `data/`, bases de datos, avatares ni caches.
- Configurar `TRADING_TRAINER_SECRET`.
- Migrar persistencia a PostgreSQL o asegurar volumen persistente si se usa SQLite temporalmente.
- Revisar politicas de backup para operaciones, recomendaciones, concursos y aprendizaje.

## Migracion SQLite a PostgreSQL

1. Aplica `supabase/schema.sql` en el proyecto Supabase.
2. Ejecuta migracion:

```powershell
.\.venv\Scripts\python.exe .\migrate_sqlite_to_postgres.py --sqlite-path .\data\trading_trainer.db --postgres-url "postgresql://USER:PASS@HOST:PORT/postgres"
```

3. Reinicia la app con `APP_ENV=production` y `SUPABASE_DATABASE_URL`.

Validacion de conteos:

```powershell
.\.venv\Scripts\python.exe .\validate_migration_counts.py --sqlite-path .\data\trading_trainer.db --postgres-url "postgresql://USER:PASS@HOST:PORT/postgres"
```

## Validacion rapida

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_pending_zone_analysis
.\.venv\Scripts\python.exe -m unittest tests.test_training_recharge
.\.venv\Scripts\python.exe -m unittest tests.test_engine_coherence_audit
.\.venv\Scripts\python.exe -m py_compile app.py analysis_engine.py data_engine.py market_data.py security.py tests\test_pending_zone_analysis.py tests\test_training_recharge.py
node --check .\app.js
```

Auditoria reproducible de coherencia:

```powershell
.\.venv\Scripts\python.exe audit_engine_coherence.py
```

## Script legacy

`trading_simulator.py` conserva el simulador de consola inicial. Es util como referencia, pero la aplicacion principal es `app.py`.
