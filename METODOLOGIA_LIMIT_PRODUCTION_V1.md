# Metodologia LIMIT-5: analisis online en dos etapas

Version de motor: `LIMIT-TWO-STAGE-ENGINE-v0.1`.

Version de contrato: `limit-order-contract-v1.4`.

Estado: conectado al endpoint productivo de analisis. La orden solo puede crearse
si conserva el analisis LIMIT que el usuario acaba de seleccionar.

## 1. Alcance soportado

LIMIT v1 admite exclusivamente ordenes de retroceso:

- LONG con entrada solicitada por debajo del precio actual y `price_lte`;
- SHORT con entrada solicitada por encima del precio actual y `price_gte`.

Las ordenes stop de ruptura siguen fuera de alcance. No se degradan ni se hacen
pasar por una LIMIT.

## 2. Calculo en dos etapas

El endpoint obtiene un precio nuevo de Binance Futures y separa:

1. `P(activacion)`: referencia first-passage por distancia logaritmica,
   volatilidad total del horizonte y tiempo disponible;
2. `P(TP|activacion)`, `P(SL|activacion)` y `P(sin barrera|activacion)`: vista
   condicional de M6 usando la geometria de la entrada solicitada.

El precio actual se usa para recoger el contexto vivo. La entrada solicitada se
usa como origen de la geometria TP/SL. No se sustituye uno por otro.

El arbol completo conserva cuatro clases mutuamente excluyentes:

- activacion y TP primero;
- activacion y SL primero;
- activacion y ninguna barrera antes del vencimiento posterior;
- no activacion antes del vencimiento de la orden.

Las masas se componen por multiplicacion condicional y deben sumar uno.

## 3. Semantica visible

Las tres tarjetas historicas se mantienen por compatibilidad con la interfaz y
la tabla `recommendations`, pero en una LIMIT se rotulan:

- `TP si activa`;
- `SL si activa`;
- `Sin barrera si activa`.

La activacion aparece separada en el titular y en los destacados. El resultado
tambien muestra una referencia `activacion + TP`, pero no la presenta como una
probabilidad calibrada.

La activacion first-passage todavia no esta calibrada con casos LIMIT cerrados.
La vista M6 posterior es una previsualizacion hecha al colocar la orden; el
contrato obliga a recalcularla con datos frescos en la activacion real.

## 4. Contexto LIMIT

Se ejecutan los cuatro descriptores de LIMIT-3:

- trayectoria hacia la activacion y reaccion posterior;
- flujo con doble orientacion;
- estructura de soporte/resistencia y Fibonacci;
- caminos compactos de liquidaciones cuando la fuente esta disponible.

Siguen sin coeficientes y con efecto probabilistico cero. Su ausencia degrada
solo la regla afectada y nunca se rellena con valores inventados.

## 5. Persistencia controlada

Analizar una propuesta crea la recomendacion normal que necesita la interfaz,
pero no crea una fila en `limit_learning_snapshots`.

La fotografia `placement` se inserta unicamente cuando el usuario crea la orden
LIMIT enlazada a esa recomendacion. La insercion es atomica con la operacion:
si falta el contrato, se supera el cupo diario o falla el presupuesto compacto,
la operacion no se crea.

Se mantienen:

- maximo de 50 casos seleccionados por dia UTC;
- una fotografia de colocacion por operacion;
- maximo de 3584 bytes para colocacion;
- ausencia de velas, trades, order books y mapas crudos.

## 6. Compatibilidad

El camino `market` sigue llamando directamente a M6 y conserva sus
probabilidades y comportamiento. El hook interno que comparte contexto con
LIMIT solo se devuelve de forma transitoria y se elimina antes de responder o
persistir.

## 7. Continuacion en LIMIT-6

LIMIT-6 conecta el recalculo M6 en la activacion real, los dos vencimientos y
las fotografias compactas `activation` y `closure`. La metodologia detallada se
encuentra en `METODOLOGIA_LIMIT_LIFECYCLE_V1.md`.
