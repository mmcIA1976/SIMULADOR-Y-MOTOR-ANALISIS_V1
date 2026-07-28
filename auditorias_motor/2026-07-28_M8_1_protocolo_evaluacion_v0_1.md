# M8.1 - Protocolo de evaluacion pre-registrado

Fecha: 2026-07-28
Estado: M8 INICIADA; PROTOCOLO CONGELADO

## Embargo

- Resultados de operaciones cerradas inspeccionados: NO.
- Base de datos consultada en M8.1: NO.
- Porcentajes antiguos como etiqueta o entrenamiento: PROHIBIDO.
- Comparacion con el motor antiguo: solo en la prueba final.

## Particiones

1. Desarrollo: estimacion de coeficientes.
2. Calibracion: calibracion y seleccion unica.
3. Prueba final: una evaluacion sin retoques posteriores.

Los timestamps exactos se fijaran con inventario de cobertura,
sin consultar outcomes, PnL ni probabilidades.

## Metricas primarias

- Brier multiclase no escalado.
- Log-loss multiclase.
- Curvas y error de calibracion por clase.
- Intervalos emparejados mediante bootstrap por dia UTC.

## Decisiones posibles

- Aprobado para considerar M9.
- Rechazado.
- Devuelto a una fase anterior.
- Evidencia insuficiente.

## Limites

- M8 no activa produccion.
- M9 permanece bloqueada.

Siguiente subfase: M8.2.

SHA-256 del payload canonico: `68cc3f968e9f93a716b50a6307253e877036125b61bed79ee2fba8b9556ebea8`.
