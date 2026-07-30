# Quinta familia: breadth y sentimiento en observacion

Fecha: 2026-07-30
Estado: IMPLEMENTADA EN OBSERVACION; SIN EFECTO PROBABILISTICO

## Objetivo

Registrar dos contextos generales que pueden condicionar el primer toque de
TP, SL o la expiracion, sin asumir de antemano que son tendenciales o
contrarian:

1. participacion transversal del mercado cripto;
2. Fear & Greed actual relativo a sus 60 dias anteriores.

## Breadth

Fuente: CoinGecko `/coins/markets`, actualmente accesible sin suscripcion de
pago. Se solicita una sola pagina con los primeros 100 activos ordenados por
capitalizacion actual y los cambios 1h, 24h y 7d.

El universo incluye stablecoins porque la respuesta de mercado no incorpora
una clasificacion fiable para excluirlas reproduciblemente. La decision queda
registrada para evitar un filtro manual cambiante.

```text
U_t = primeros 100 activos por capitalizacion actual
breadth_w = count(return_i_w > 0) / count(valid_return_i_w)
median_return_w = median(valid_return_i_w)
w in {1h, 24h, 7d}
```

Tambien se guarda la transformacion centrada `2*breadth_w-1` y su vista
relativa al lado del plan. No se recuperan los umbrales antiguos 58/42 ni el
ajuste de puntos asociado.

La regla exige exactamente 100 identificadores unicos, timestamps no
posteriores a la captura y al menos un retorno valido en cada ventana. Guarda
el denominador y cobertura exactos de cada calculo.

## Sentimiento

Fuente: API publica Alternative.me `/fng/`. El proveedor permite solicitar
historico mediante `limit` y devuelve timestamp Unix diario.

```text
p_sent = (count(v_i < v_t) + 0.5*count(v_i = v_t)) / 60
MAD = median(abs(v_i - median(v_i)))
z_robusto = (v_t - median(v_i)) / (1.4826*MAD)
alineacion_lado = side_sign*(v_t-50)/50
```

Se exige el valor actual y 60 dias estrictamente anteriores, timestamps
unicos, continuidad diaria y antiguedad inferior a dos periodos diarios.
`MAD=0` no invalida el percentil; solo deja el robust z como nulo.

La clasificacion textual del proveedor se conserva como dato descriptivo.
Los umbrales antiguos 75/25 y sus penalizaciones quedan descartados.

## Casos historicos preservados

El inventario de base de datos contiene:

- 874 recomendaciones con algun contexto;
- 718 observaciones antiguas de breadth;
- 874 observaciones antiguas de sentimiento;
- 242 casos vinculados a operaciones;
- 233 operaciones cerradas.

Artefacto:

```text
auditorias_motor/market_context_historical_cases_v0_1.json
d1a49379ae1e5072881a3caa1e1ee67b141b3343affb3110bec5abee3d12f672
```

Los valores antiguos no se mezclan directamente con la regla nueva. Breadth
no conserva los 100 constituyentes y sentimiento no conserva en cada
snapshot la referencia de 60 dias. El sentimiento historico puede
reconstruirse posteriormente desde la serie publica.

## Trazabilidad

Ambas trazas conservan inputs, timestamps, universo o referencia, valores
normalizados, formula, hash de fuente, causas de bloqueo y:

```text
probability_effect = none_shadow_observation
```

Los cierres futuros quedaran enlazados con estas observaciones por el contrato
estructurado existente. El aprendizaje no modifica produccion.
