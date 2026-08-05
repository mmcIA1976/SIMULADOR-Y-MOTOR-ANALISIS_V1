# Metodologia LIMIT-3: trayectoria y calidad de zona

Version: `limit-context-rule-runtime-v0.1`.

Estado: descriptores en sombra. Ninguna de estas reglas cambia la probabilidad
base de activacion, M6 market, la recomendacion o el tamano de operacion.

## 1. Separacion obligatoria

Una orden limit necesita distinguir:

- movimiento hacia la entrada;
- reaccion esperada despues de tocarla.

Para LONG limit, una caida puede favorecer la activacion y perjudicar el rebote.
Para SHORT limit sucede lo contrario. Por ello, toda variable direccional se
publica con dos orientaciones y nunca se suma automaticamente.

## 2. Reglas trazadas

### `LIMIT-CAND-ACTIVATION-TRAJECTORY-001`

Reorienta estructura de camino H/2H/4H, desplazamiento, pendiente EMA y RSI hacia
la direccion necesaria para activar. Mantiene tambien la orientacion contraria,
que representa la reaccion buscada.

### `LIMIT-CAND-FLOW-DUAL-ROLE-001`

Reorienta ATI, CVD y desequilibrio del libro actual para activacion y reaccion.
OI, funding y crowding permanecen como contexto sin interpretacion causal.

El libro es una fotografia del precio actual. No se presenta como liquidez futura
en la entrada limit.

### `LIMIT-CAND-ZONE-STRUCTURE-001`

Para LONG busca el soporte confirmado mas cercano a la entrada; para SHORT, la
resistencia. Conserva distancia en volatilidad, prominencia, niveles en los
caminos TP/SL y Fibonacci, pero no genera un `zone_score`.

### `LIMIT-CAND-LIQUIDATION-PATH-001`

Divide los clusters visibles en tres regiones:

1. camino desde precio actual hasta entrada;
2. sobrepaso desde entrada hasta SL;
3. camino posterior desde entrada hasta TP.

Solo guarda resumen de numero de clusters, nocional, wallets conocidas y cluster
mas cercano. No persiste el heatmap crudo. La masa se etiqueta como descriptor
visible, no como atraccion causal ni probabilidad.

## 3. Ausencia de datos

- trayectoria requiere estructura H y MTF;
- estructura de zona requiere pivotes estructurales;
- Fibonacci es opcional;
- flujo puede evaluarse parcialmente con las fuentes disponibles;
- liquidaciones son opcionales y solo cubren simbolos soportados por el proveedor.

Una regla bloqueada no inventa datos y no bloquea automaticamente las otras.

## 4. Doble conteo

LIMIT-3 prohibe agregar los componentes a un score. Las mismas señales pueden
aparecer orientadas hacia activacion y reaccion, pero conservan un unico valor
bruto y trazabilidad al padre.

Solo una calibracion posterior podra decidir si una variable entra en el modelo,
con que coeficiente y que variables correlacionadas deben excluirse.

## 5. Puerta a LIMIT-4

LIMIT-4 podra definir la persistencia cuando:

- las cuatro trazas sean deterministas;
- todos los efectos probabilisticos permanezcan en cero;
- fuentes ausentes degraden por regla;
- no se guarden velas, libros o heatmaps crudos;
- la suite completa del motor y los hashes congelados permanezcan verdes.
