# Sexta familia: liquidaciones en observacion

Fecha: 2026-07-30
Estado: IMPLEMENTADA EN OBSERVACION; SIN EFECTO PROBABILISTICO

## Fuente y alcance

La aplicacion consulta gratuitamente:

```text
GET https://trade.hyperperps.app/api/public/heatmap/{BTC|ETH|SOL}
```

HyperPerps agrega posiciones publicas observables de Hyperliquid y publica
clusters de liquidacion para BTC, ETH y SOL. El endpoint devuelve schema,
timestamp, precio de referencia, muestra, clusters, masa por bandas,
apalancamiento medio y sesgo de OI.

No es un mapa de todos los exchanges ni una enumeracion completa garantizada
de todas las cuentas de Hyperliquid. Hyperliquid permite consultar
`clearinghouseState` por usuario; el agregado depende del universo observado
por HyperPerps.

## Gates heredados de captura

La captura actual rechaza:

- datos con mas de 600 segundos por defecto;
- diferencia superior a 1,5% entre referencia HyperPerps y precio del plan;
- payload sin clusters;
- simbolos distintos de BTC, ETH y SOL.

Los limites son gates operativos configurables, no senales predictivas.
Cuando fallan, la regla queda bloqueada y el resto del analisis continua.

## Formula nueva

Para LONG:

- clusters short por encima son el lado del camino al TP;
- clusters long por debajo son el lado del camino al SL.

Para SHORT se invierten.

```text
d_entry_j = log(cluster_price_j/entry)/sigma_h
d_barrier_j = abs(log(cluster_price_j/barrier))/sigma_h
mass_b = sum(notional_j para clusters entre entry y barrier_b)
target_fraction = target_mass/(target_mass+adverse_mass)
```

Si no existe masa en ninguno de los dos caminos, `target_fraction` queda
nulo. No se introduce pseudocount ni se convierte infinito en un valor
artificial.

La traza conserva hasta diez clusters publicados por lado, sus nocionales,
wallets, distancias normalizadas, masas agregadas 1%, 2% y 5%, muestra,
antiguedad y hash de la observacion.

## Elementos descartados

No se reutilizan:

- `map_read = favorable/desfavorable/mixto`;
- `adverse_squeeze_risk = bajo/medio/alto`;
- umbrales de ratio 1,2x, 2x o 4x como senal;
- scores 25/50/75;
- ajustes directos de TP, SL o riesgo.

Son etiquetas y puntos del motor antiguo, no efectos estimados.

## Casos historicos

Se conservan:

- 107 analisis;
- 104 mapas disponibles;
- 24 operaciones vinculadas, cerradas y resueltas.

Artefacto:

```text
auditorias_motor/heatmap_historical_cases_v0_1.json
243101dbf49d380baa123d085113429d4aaf63451a7b180b80ad61c721f3f7c4
```

Los 24 casos mantienen identidad y outcome, pero sus etiquetas antiguas no
son numericamente comparables con la formula continua nueva porque el snapshot
historico no conserva todos los clusters normalizados necesarios.

## Aprendizaje

Cada analisis nuevo registra la observacion completa con:

```text
probability_effect = none_shadow_observation
```

Al cerrar la operacion se podra relacionar masa, lado, distancia y barreras
con TP_FIRST, SL_FIRST o expiracion. Ningun resultado modifica produccion
automaticamente.
