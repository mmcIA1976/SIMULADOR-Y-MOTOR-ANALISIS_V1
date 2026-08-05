# Metodologia LIMIT-2: base de activacion por primer paso

Version: `limit-activation-first-passage-v0.1`.

Estado: evaluacion en sombra. No habilita `/api/analyze` para ordenes pending y
no modifica las probabilidades del motor M6 de entradas market.

## 1. Pregunta que responde

La base calcula la probabilidad implicita de que el log-precio toque una unica
barrera de entrada antes de consumir la ventana de activacion.

No intenta responder si la zona rebotara ni si TP ocurrira antes que SL despues
de activar.

## 2. Geometria

Para LONG limit:

```text
d = log(precio_actual / entrada_solicitada)
```

Para SHORT limit:

```text
d = log(entrada_solicitada / precio_actual)
```

En ambos casos `d` es positiva. La normalizacion relevante es `d / sigma_H`,
donde `sigma_H` es la volatilidad total del horizonte exacto bajo la misma
convencion usada por M6.

## 3. Formula

Bajo un movimiento browniano del log-precio, continuo y sin deriva, el principio
de reflexion da:

```text
P(activar antes de H) = erfc(d / (sigma_H * sqrt(2)))
```

Para una fraccion `u` del horizonte:

```text
P(activar antes de uH) = erfc(d / (sigma_H * sqrt(2u)))
```

En `u = 0`, la probabilidad es cero. La implementacion usa `math.erfc` para
mantener estabilidad numerica en las colas.

El solver vive en `limit_activation_first_passage.py`. Importa las validaciones
numericas de M6, pero no modifica el archivo congelado `m6_first_passage.py` ni
sus artefactos de auditoria.

## 4. Interpretacion correcta

La salida es una probabilidad implicita del modelo, no una probabilidad calibrada
para el usuario. Es la referencia minima contra la que se evaluaran las reglas
posteriores.

Por construccion:

- una entrada mas cercana tiene mayor probabilidad de activacion;
- mas volatilidad aumenta la probabilidad de activacion;
- mas tiempo aumenta la incidencia acumulada;
- un LONG y un SHORT con distancia logaritmica espejo tienen la misma base.

## 5. Lo que todavia excluye

- tendencia y regimen;
- soportes, resistencias y Fibonacci;
- order book, CVD y flujo agresor;
- open interest, funding y basis;
- mapas y eventos de liquidaciones;
- saltos, gaps y latencia de proveedor;
- calidad del rebote tras tocar la entrada.

Estas ausencias son deliberadas. LIMIT-3 probara si cada familia aporta valor
incremental sobre esta referencia sin confundir llegada con reaccion.

## 6. Trazabilidad

La salida registra:

- contrato LIMIT que origina el calculo;
- distancia logaritmica;
- distancia en unidades de volatilidad;
- volatilidad total del horizonte;
- probabilidades de activacion y no activacion;
- CDF en 0%, 25%, 50%, 75% y 100% de la ventana;
- version del modelo y del solver;
- metodo numerico, supuestos y efectos excluidos.

## 7. Puerta a LIMIT-3

LIMIT-3 podra comenzar cuando:

- la masa `activacion + no activacion` sea uno en todos los casos;
- monotonicidad, simetria long/short y extremos esten probados;
- la suite completa de mercado siga verde;
- la API de produccion siga rechazando pending hasta disponer de integracion y
  validacion suficientes.
