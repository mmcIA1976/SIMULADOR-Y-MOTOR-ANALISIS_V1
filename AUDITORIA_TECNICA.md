# Auditoria tecnica del proyecto

Fecha: 2026-05-25

## Resumen

El proyecto ya tiene una base funcional sólida para desarrollo local: autenticacion, operaciones, cartera, concurso mensual, avatares en base de datos, motor de analisis por temporalidad, registro de recomendaciones, ticks y conclusiones de aprendizaje.

La prioridad antes de seguir creciendo es mantener tres separaciones claras:

- Simulacion y visualizacion de operaciones.
- Motor de analisis probabilistico.
- Aprendizaje descriptivo basado en resultados reales.

## Cambios aplicados en esta auditoria

- Se añadieron archivos de preparacion para repositorio y servidor: `.gitignore`, `.env.example`, `Procfile`, `runtime.txt`.
- Se actualizo `README.md` para reflejar el estado real de la app y el camino a despliegue.
- Se excluyeron de Git los datos locales: `.venv/`, `data/`, bases SQLite, avatares y caches.
- Se corrigieron consultas que podian duplicar operaciones si habia varias recomendaciones asociadas.
- Se eliminaron variables y helpers sin uso en `analysis_engine.py`.
- Se reforzo el frontend escapando datos dinamicos en paneles criticos de analisis, ranking, operaciones y aprendizaje.
- Se aumento la version de carga de `app.js` para evitar cache del navegador.

## Riesgos corregidos

### Duplicacion por recomendaciones

Antes, algunos `LEFT JOIN recommendations` podian devolver mas de una fila por operacion si existian varias recomendaciones asociadas. Ahora se selecciona solo la recomendacion mas reciente por operacion.

Impacto: evita conclusiones de aprendizaje duplicadas y rankings/informes contaminados.

### Datos locales en repositorio

El proyecto tenia base de datos, avatares y entorno virtual dentro de la carpeta. Ahora quedan ignorados.

Impacto: evita subir datos personales, sesiones, operaciones reales de prueba y archivos pesados.

### HTML dinamico

El frontend generaba muchas secciones con `innerHTML`. Se ha saneado la salida de las zonas mas expuestas.

Impacto: reduce riesgo al pasar de usuario unico local a app compartida.

## Puntos aun pendientes antes de produccion

### Base de datos

SQLite sirve para desarrollo, pero no es la opcion adecuada para Railway/Replit con usuarios reales salvo que exista volumen persistente y backups. El siguiente salto serio debe ser PostgreSQL.

Pendiente:

- Crear capa de repositorio para aislar SQL.
- Sustituir SQL especifico de SQLite por consultas compatibles o usar un ORM ligero.
- Migrar avatares BLOB y operaciones a PostgreSQL.

### Seguridad

Pendiente:

- Configurar `TRADING_TRAINER_SECRET` obligatorio en produccion.
- Activar cookie `secure` cuando se use HTTPS.
- Añadir limites de frecuencia a login, registro, analisis y subida de avatar.
- Revisar politicas de expiracion de sesion.

### Arquitectura frontend

`app.js` ya concentra demasiada responsabilidad: estado, red, render, grafica, concurso, operaciones y analisis.

Pendiente:

- Dividir en modulos: api, state, chart, analysisView, operationsView, contestView.
- Reducir `innerHTML` restante mediante helpers o render DOM directo.
- Añadir tests de calculo para PnL, TP/SL, cartera y concurso.

### Motor de analisis

El motor v0.5 ya separa temporalidad, probabilidad, confianza y esperanza matematica. Sigue siendo un motor de reglas, no un modelo estadistico calibrado.

Pendiente:

- Backtesting con historico real.
- Calibracion por rangos, no precision decimal.
- Medir desempeño por patron compuesto.
- Aprendizaje descriptivo con minimo de casos antes de sugerir cambios.

## Recomendacion inmediata

Antes de crear el repositorio GitHub, hacer una segunda fase corta:

- Modularizar las consultas de base de datos mas repetidas.
- Crear pruebas unitarias para calculos financieros esenciales.
- Preparar migracion PostgreSQL.
- Documentar claramente que la app es educativa y no ejecuta trading real.
