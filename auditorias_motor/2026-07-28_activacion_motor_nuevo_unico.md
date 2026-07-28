# Activacion del motor nuevo como unico motor online

Fecha: 2026-07-28

## Decision del propietario

El propietario ordena que los nuevos analisis sean calculados exclusivamente
por el candidato `M6-CANDIDATE-NO-H-RIDGE-10-v0.2`.

## Efecto

- `/api/analyze` no ejecuta `analysis_engine.analyze_trade`.
- El motor anterior no se usa como fallback.
- No se genera una segunda prediccion en sombra.
- TP, SL y ausencia de toque visibles proceden del resultado calibrado M6.
- La recomendacion guarda version, datos, reglas, formulas, coeficientes y
  contribuciones del motor nuevo.
- El aprendizaje posterior queda vinculado a la version que genero la
  recomendacion.

## Tratamiento del historico

Las recomendaciones antiguas se conservan sin modificarlas porque registran el
analisis que realmente recibio el usuario en cada operacion pasada. No se
ejecutan para analisis nuevos, no se mezclan con el nuevo modelo y no autorizan
ningun peso futuro.

## Fallo cerrado

Si el motor nuevo no puede obtener datos suficientes o completar el calculo,
el analisis falla explicitamente. Queda prohibido sustituirlo silenciosamente
por el motor anterior.
