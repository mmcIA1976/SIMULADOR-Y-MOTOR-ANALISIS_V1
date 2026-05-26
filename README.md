# Trading Trainer Learning Model v1

Simulador educativo multiusuario para analizar, registrar y auditar operaciones crypto con datos de mercado reales. No ejecuta ordenes reales, no conecta con cuentas de exchange y no solicita claves API privadas.

## Estado actual

- Registro/login local con cookie de sesion.
- Avatar guardado en base de datos.
- Simulacion de operaciones BTC/USDT y otros pares Binance Spot.
- Maximo de 2 operaciones abiertas por usuario y modo.
- Carteras separadas para entrenamiento y concurso mensual.
- Motor de analisis por temporalidad: intradia corto, intradia amplio y swing corto.
- Registro de recomendaciones, ticks de precio, cierres, observacion y conclusiones de aprendizaje.
- SQLite para desarrollo local.

## Desarrollo local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8766
```

Abre `http://127.0.0.1:8766`.

## Variables de entorno

Copia `.env.example` como referencia:

```text
DATABASE_URL=sqlite:///data/trading_trainer.db
TRADING_TRAINER_SECRET=change-me-before-production
```

Para produccion, `TRADING_TRAINER_SECRET` debe ser una clave larga y privada. `DATABASE_URL` solo soporta SQLite en esta version; PostgreSQL queda como siguiente paso antes de alojar usuarios reales en Railway/Replit sin depender de disco local.

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

## Validacion rapida

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py db.py analysis_engine.py learning_engine.py data_engine.py market_data.py security.py
node --check .\app.js
```

## Script legacy

`trading_simulator.py` conserva el simulador de consola inicial. Es util como referencia, pero la aplicacion principal es `app.py`.
