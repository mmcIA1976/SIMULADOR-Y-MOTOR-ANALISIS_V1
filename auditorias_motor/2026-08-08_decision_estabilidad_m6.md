# Decisión de estabilidad del motor M6

Fecha de decisión: 2026-08-08

## Decisión

El artefacto global `M6-CANDIDATE-NO-H-RIDGE-10-v0.2`, con temperatura
1.5, queda congelado como único campeón de producción para los tres marcos:

- `intraday_short`: vencimiento exacto de 4 horas.
- `intraday_wide`: vencimiento exacto de 24 horas.
- `short_swing`: vencimiento exacto de 7 días.

Compartir coeficientes no hace idénticos los análisis. Cada marco conserva su
propia ventana, frecuencia de muestreo, volatilidad observada, número de
retornos y geometría TP/SL normalizada por el horizonte.

La calibración por horizonte y las ocho reglas provisionales se ejecutan como
un único challenger en sombra. Su predicción compacta se guarda dentro del
snapshot de recomendación que ya existe. No crea una nueva fila por análisis,
no cambia la probabilidad visible y no puede modificar pesos automáticamente.

## Evidencia que fundamenta la decisión

En la auditoría incremental posterior al baseline se compararon 38 resultados
exactos sobre las mismas operaciones:

| Modelo | Brier 3 clases | Log-loss | Acierto |
|---|---:|---:|---:|
| M6 global congelado | 0.372968 | 0.561942 | 76.32% |
| Núcleo por horizonte v0.5 | 0.383914 | 0.580799 | 78.95% |
| v0.5 completo con overlays | 0.394406 | 0.591334 | 76.32% |

El modelo por horizonte no mejoró de forma consistente los tres marcos. El
overlay empeoró a su propio núcleo en 0.010535 de log-loss. Por tanto, estos
cambios no tienen evidencia suficiente para gobernar producción.

## Qué significa «aprender» desde ahora

Aprender no significa retocar el motor después de unas pocas operaciones. El
sistema conservará una referencia fija y comparará, para cada operación, el
campeón y el challenger contra el mismo resultado exacto: TP primero, SL
primero o ninguno antes del vencimiento.

La API de auditoría `/api/learning/champion-shadow-audit` informa del progreso
sin escribir nuevas filas en Supabase. La lectura usa Brier y log-loss; el
porcentaje de acierto no decide por sí solo porque ignora la calidad de la
probabilidad asignada.

## Contrato para evitar nuevos cambios continuos

- Informe preliminar: 25 resultados exactos por cada marco.
- Revisión de posible promoción: 50 resultados exactos por cada marco.
- El challenger debe mejorar al menos un 2% tanto Brier como log-loss en el
  agregado.
- No puede empeorar materialmente ningún marco por separado.
- La revisión final requiere bootstrap por bloques de calendario al 95%.
- Nunca hay promoción automática: se crea una versión explícita y revisada.
- Mientras no supere todos los criterios, el campeón permanece intacto.

## Corrección del aprendizaje posterior a cierres manuales

Se elimina la espera fija de dos días. Un cierre manual sigue observándose
hasta el vencimiento original del análisis (4 h, 24 h o 7 días). En una LIMIT,
el vencimiento se calcula desde la activación real. Esto evita repetir el fallo
detectado en la operación 263, donde una observación recortada etiquetó
`no_plan_touch` aunque el SL llegó antes del vencimiento exacto.

## Respuesta operativa

Hasta hoy sí se obtuvo aprendizaje útil: se demostró que añadir complejidad no
mejoraba el resultado global y que el etiquetado temporal tenía un defecto.
Pero no existe todavía evidencia prospectiva suficiente para afirmar que el
challenger aprende mejor que el campeón. Desde esta versión, esa pregunta queda
medida con una cohorte estable y deja de responderse mediante cambios de pesos
continuos.
