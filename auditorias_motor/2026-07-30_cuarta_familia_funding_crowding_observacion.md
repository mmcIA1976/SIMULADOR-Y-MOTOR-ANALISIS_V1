# Cuarta familia: funding relativo y crowding en observacion

Fecha: 2026-07-30
Estado: IMPLEMENTADA EN OBSERVACION; SIN EFECTO PROBABILISTICO

## Objetivo

Sustituir los umbrales absolutos y los puntos heredados por dos mediciones
relativas al historial del propio par:

1. funding actual frente a sus 60 liquidaciones de funding anteriores;
2. ratio global de cuentas long/short frente a sus 60 periodos anteriores.

Ninguna de las dos reglas modifica TP, SL o expiracion. Sus efectos deben
estimarse con resultados posteriores y aprobarse expresamente.

## Fuentes

- Binance USD-M `GET /fapi/v1/premiumIndex`: funding actual publicado.
- Binance USD-M `GET /fapi/v1/fundingRate`: funding liquidado historico,
  ordenado por tiempo y con limite oficial de 1000 registros.
- Binance USD-M `GET /futures/data/globalLongShortAccountRatio`: proporcion
  de cuentas long y short de todos los operadores; periodos hasta 1d,
  limite 500 y disponibilidad de los ultimos 30 dias.
- NIST Median Absolute Deviation: definicion de MAD robusta.

No se usan ratios de top traders porque la documentacion actual exige API key.

## Regla de funding relativo

La observacion actual es `lastFundingRate` de `premiumIndex`. La referencia
son exactamente las ultimas 60 tasas liquidadas con timestamp estrictamente
anterior:

```text
p_funding = (count(r_i < r_t) + 0.5*count(r_i = r_t)) / 60
MAD = median(abs(r_i - median(r_i)))
z_robusto = (r_t - median(r_i)) / (1.4826*MAD)
coste_lado_plan = side_sign * r_t
```

`side_sign=+1` para long y `-1` para short. Este ultimo valor expresa coste o
ingreso de funding para el lado, no una prediccion direccional.

Si faltan 60 observaciones, hay timestamps duplicados, el dato actual es
invalido o su timestamp supera la captura, la regla queda bloqueada. Si
`MAD=0`, se conserva el percentil y `z_robusto` queda nulo con causa explicita.

## Regla de crowding relativo

Binance define el ratio global como numero de cuentas long dividido por numero
de cuentas short. Se transforma con logaritmo para que ratios reciprocos sean
simetricos:

```text
x_t = log(longShortRatio_t)
p_long = (count(x_i < x_t) + 0.5*count(x_i = x_t)) / 60
p_lado = p_long                    si side=long
p_lado = 1-p_long                  si side=short
z_robusto = (x_t - median(x_i)) / (1.4826*MAD(x_i))
```

Se exige el periodo actual y 60 periodos anteriores, unicos, contiguos y no
posteriores al corte del analisis. `p_lado` solo describe cuanto se concentra
el posicionamiento en el lado elegido; no presupone si ese crowding ayuda o
perjudica al TP.

## Trazabilidad

Cada regla registra:

- proveedor, semantica y ventana exacta;
- timestamps primero, ultimo y actual;
- valores actuales, mediana, MAD, percentil y robust z;
- vista neutral y vista relativa al lado del plan;
- hash SHA-256 de los 60 datos usados;
- estado, causas de bloqueo y efecto probabilistico `none_shadow_observation`.

El cierre de la operacion conservara estas trazas mediante el contrato
estructurado ya existente. El aprendizaje no puede modificar produccion.

## Decisiones descartadas

- no se usan los antiguos umbrales absolutos de funding;
- no se asignan puntos por funding alto, bajo o por crowding;
- no se llama extremo a ningun percentil sin estimacion posterior;
- no se interpreta crowding como contrarian ni tendencial por defecto;
- no se mezclan ratios globales con ratios de top traders;
- no se sustituyen datos ausentes por cero o por valores neutrales.
