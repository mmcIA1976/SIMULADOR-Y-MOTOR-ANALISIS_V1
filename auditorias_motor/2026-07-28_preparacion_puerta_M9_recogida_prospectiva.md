# Preparacion de la puerta M9 - Recogida prospectiva

Estado: IMPLEMENTADA EN LOCAL; M9 NO AUTORIZADA.

## Motivo

M6-R1 corrigio el defecto numerico, pero M8 no aprobo el candidato porque 200
de 201 registros historicos carecian del horizonte exacto almacenado antes del
outcome. Activar el motor con esos datos violaria la hoja de ruta.

## Resultado implementado

- Cada analisis manual conserva la salida visible del motor productivo actual.
- El punto de ejecucion en sombra lanza tambien M5 y M6-R1.
- Solo se admiten entradas MARKET para esta evidencia.
- Se consultan exclusivamente velas Binance USD-M cerradas antes del analisis.
- Se guardan `analysis_at`, corte real de datos, horizonte y expiracion exactos.
- Se guardan las cinco variables pretrade, sus fuentes y el hash de las velas.
- Se guardan la traza M5, el resultado M6 y la masa TP/SL/no-resuelto.
- La tabla `m6_prospective_runs` es privada, append-only e idempotente.
- El endpoint existente `/api/learning/challenger-audit` incorpora el bloque
  `prospective_validation`.
- El interruptor `M6_PROSPECTIVE_VALIDATION_ENABLED=false` detiene la recogida.

## Limites

- Las probabilidades M6 no se muestran al usuario.
- `production_effect` permanece forzado a `none`.
- No se han reajustado coeficientes con el periodo final abierto de julio.
- No se ha autorizado M9 ni M10.
- No se ha realizado despliegue online en este cambio local.

## Verificacion

- Prueba real de lectura Binance: evaluada con corte de vela cerrada.
- Masa probabilistica observada: 1 dentro de precision numerica.
- El hash historico de `app.py` de M5-M7 permanece intacto.
- Suite automatizada completa: 609/609 pruebas correctas.
