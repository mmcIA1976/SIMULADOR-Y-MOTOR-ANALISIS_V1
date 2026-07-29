# Segunda familia implementada: volumen y microestructura

Fecha: 2026-07-29
Estado: IMPLEMENTADA EN OBSERVACION; SIN EFECTO PROBABILISTICO

## 1. Alcance

Se han incorporado tres reglas candidatas de la biblioteca:

```text
LIB-CAND-RELATIVE-VOLUME-001
LIB-CAND-CVD-SLOPE-001
LIB-CAND-ORDERBOOK-IMBALANCE-001
```

Las tres se calculan antes de la operacion, quedan trazadas y se enlazan con
el resultado posterior. No modifican todavia P(TP), P(SL) ni P(expiracion).

## 2. Volumen relativo

Datos:

- volumen quote de velas cerradas de Binance Futures;
- volumen base como alternativa si el quote no esta disponible;
- 61 ventanas consecutivas del mismo horizonte H.

Formula:

```text
V_H = suma del volumen en la ventana exacta H
referencia = 60 ventanas H anteriores, consecutivas y no solapadas
relative_volume_H = V_H / mediana(referencia)
midrank_60 = (menores + 0.5 * iguales) / 60
```

El volumen es una medida de actividad y no se invierte por LONG/SHORT. No se
le atribuye por si solo una direccion favorable.

## 3. CVD de ventana exacta

Fuente primaria:

```text
Binance taker buy/sell volume history
```

Fuente alternativa:

```text
taker buy quote volume y quote volume de velas cerradas
```

Formula:

```text
delta_i = buy_taker_volume_i - sell_taker_volume_i
CVD_t = suma acumulada(delta_i)
cvd_slope = mediana de todas las pendientes entre pares (Theil-Sen)
normalized_cvd_slope = cvd_slope / actividad taker media
terminal_imbalance = suma(delta_i) / suma(buy_i + sell_i)
```

La ventana debe coincidir exactamente con H. Si no existe cobertura periodica
completa ni fallback de velas, la regla queda bloqueada y no se rellena con un
valor inventado. La pendiente y el imbalance si se alinean con LONG/SHORT.

## 4. Desequilibrio visible del libro

Datos:

- snapshot de 100 niveles de profundidad de Binance Futures;
- timestamp de captura;
- bids y asks validos y libro no cruzado.

Formula para cada profundidad D:

```text
bid_notional_D = suma(precio_bid * cantidad_bid)
ask_notional_D = suma(precio_ask * cantidad_ask)
OBI_D = (bid_notional_D - ask_notional_D)
        / (bid_notional_D + ask_notional_D)
```

Se guardan cinco medidas distintas:

```text
top 5 niveles
top 20 niveles
dentro de 10 bps del mid
dentro de 20 bps del mid
dentro de 50 bps del mid
```

No se suman entre ellas ni se convierten en puntos. Se conserva tambien la
version alineada con el lado de la operacion.

## 5. Trazabilidad

Cada ejecucion registra:

- regla, version, familia y reglas padre;
- formulas aplicadas;
- inputs, outputs y unidad de la fuente;
- horizonte e intervalo;
- timestamp y hash de datos;
- hash completo de la traza;
- estado evaluado o bloqueado y motivo;
- `probability_effect = none_shadow_observation`.

El cierre de la operacion conserva estas observaciones junto al outcome:
TP primero, SL primero o ni TP ni SL/censura.

## 6. Relacion con reglas existentes

- El CVD declara como padre el imbalance agresor existente porque ambos usan
  flujo taker. Esto permite medir duplicacion en lugar de contar dos veces la
  misma evidencia.
- El volumen relativo es neutral respecto al lado y puede actuar mas adelante
  como condicion de intensidad o interaccion.
- El libro es una fotografia visible, no una garantia de ejecucion. Se evaluara
  por bandas y no como una unica verdad sobre oferta y demanda.

## 7. Resultado actual

La biblioteca mantiene 38 fichas:

- 5 operadores base;
- 11 reglas predictivas provisionales actuales;
- 6 candidatas implementadas en observacion;
- 16 candidatas pendientes, limitadas o bloqueadas.

Catalogo canonico:

```text
auditorias_motor/catalogo_maestro_biblioteca_predictiva_v0_1.json
f84951292caa89ae92adcff4dbb3680b1ebf70d636f35a3256bc0a61416d576f
```

El siguiente bloque funcional de la hoja de ruta es niveles estructurales y
Fibonacci, sin perder los 24 casos cerrados de heatmap ya preservados.
