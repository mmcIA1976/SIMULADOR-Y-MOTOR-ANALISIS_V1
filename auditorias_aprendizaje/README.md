# Auditorias de aprendizaje

Esta carpeta guarda auditorias periodicas del motor de analisis y sus hipotesis de mejora.

El objetivo es separar tres cosas:

- datos observados en una fecha concreta;
- hipotesis candidatas que todavia no se aplican al motor;
- comprobaciones futuras para decidir si una hipotesis merece convertirse en cambio real.

## Convencion de nombres

Formato recomendado:

`YYYY-MM-DD_operaciones_verificadas_NNN_resumen.md`

Ejemplo:

`2026-06-26_operaciones_verificadas_130_hipotesis_motor_v0_9.md`

Para una hipotesis individual:

`hipotesis_01_operaciones_verificadas_130_sl_probability.md`

## Reglas de uso

- No aplicar cambios al motor solo por una auditoria inicial.
- Cada hipotesis debe guardar:
  - fecha;
  - numero de operaciones cerradas verificadas;
  - numero de evaluaciones de aprendizaje;
  - dato observado;
  - mejora candidata;
  - criterio de validacion futura;
  - estado: `pendiente`, `validada`, `descartada` o `aplicada`.
- Para aplicar una hipotesis al motor debe existir una nueva auditoria que compare casos posteriores.
- Las hipotesis aplicadas deben pasar tambien a `HISTORIAL_CAMBIOS_MOTOR_ANALISIS.md`.

## Auditorias registradas

| Fecha | Archivo | Operaciones cerradas verificadas | Evaluaciones | Estado |
|---|---|---:|---:|---|
| 2026-06-26 | `2026-06-26_operaciones_verificadas_130_hipotesis_motor_v0_9.md` | 130 | 127 | Hipotesis pendientes, no aplicadas |

## Proxima revision recomendada

Repetir auditoria cuando se alcance al menos una de estas condiciones:

- 180 operaciones cerradas verificadas, es decir, unas 50 operaciones cerradas nuevas;
- 230 operaciones cerradas verificadas, para una revision mas fiable;
- 30 casos nuevos comparables para una hipotesis concreta;
- suficientes ordenes pendientes cerradas para separar `limit_pullback`, `stop_breakout` y `stop_breakdown`.

