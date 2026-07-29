# Contrato maestro de biblioteca de reglas v0.1

Fecha: 2026-07-29
Estado: IMPLEMENTADO; SIN NUEVOS EFECTOS PREDICTIVOS

## 1. Objetivo

Materializar una biblioteca unica y validable para la Fase 1:

- separar operadores base, evidencia predictiva, interacciones, bloqueos y
  reglas economicas;
- documentar las 11 reglas predictivas actuales sin presentarlas como
  validadas;
- registrar hipotesis recuperables del motor antiguo y de la revision externa;
- impedir que una candidata incompleta o sin aprobacion afecte TP/SL;
- preparar atribucion por regla y por familia para el aprendizaje futuro.

## 2. Catalogo resultante

Version:

```text
TP-SL-RULE-LIBRARY-v0.1
```

Composicion:

| Estado | Cantidad |
|---|---:|
| Operadores base activos | 5 |
| Reglas predictivas activas provisionales | 11 |
| Candidatas, limitadas o bloqueadas por datos | 22 |
| Total de fichas | 38 |

El catalogo estructurado se encuentra en:

```text
auditorias_motor/catalogo_maestro_biblioteca_predictiva_v0_1.json
```

Su SHA-256 canonico es:

```text
f84951292caa89ae92adcff4dbb3680b1ebf70d636f35a3256bc0a61416d576f
```

## 3. Cinco operadores base

No se cuentan como senales independientes:

1. muestreo exacto del horizonte;
2. geometria long/short del plan;
3. retornos logaritmicos pre-trade;
4. volatilidad realizada;
5. barreras normalizadas por volatilidad.

Su traza se incorpora al registro estructurado de aprendizaje como baseline,
pero no recibe puntos ni peso aditivo.

## 4. Once reglas predictivas actuales

Se migraron sin cambiar su efecto numerico:

1. estructura de trayectoria;
2. extremo previo entre entrada y TP;
3. percentil de volatilidad;
4. jerarquia multi-timeframe;
5. regimen continuo;
6. desequilibrio agresor;
7. cambio de open interest;
8. estado precio-OI;
9. basis Spot-Futures;
10. prima mark-index;
11. funding.

Las tres familias ajustadas historicamente conservan sus coeficientes. Los
ocho pesos manuales quedan declarados como:

```text
origin = project_hypothesis
status = unvalidated_provisional
```

Ninguna fuente publicada se atribuye esos pesos.

## 5. Veintidos fichas no activas

Se registraron, sin efecto probabilistico:

- tendencia EMA y pendiente normalizada;
- RSI de Wilder;
- extension EMA/ATR;
- volumen relativo estacional;
- imbalance visible del libro;
- trayectoria CVD de ventana exacta;
- breadth;
- distancia y confluencia Fibonacci;
- distancia a niveles estructurales;
- percentil y robust z de funding;
- crowding;
- sentimiento;
- compresion;
- shock;
- absorcion flujo-volumen-precio;
- contexto de pullback;
- zonas observadas de liquidacion;
- frescura de datos;
- integridad de velas;
- divergencia sincronizada entre venues;
- spread de ejecucion;
- cobertura de profundidad.

`shock` queda bloqueada hasta disponer de una serie fiable de liquidaciones
realizadas. `liquidation-zone` conserva evidencia historica limitada:
107 analisis, 104 observaciones disponibles y 24 operaciones cerradas
resueltas. La divergencia entre venues queda bloqueada hasta aprobar y
sincronizar fuentes.

## 6. Formulas corregidas

El catalogo conserva las expresiones en direccion canonica:

```text
spread_fraction = (ask-bid)/mid
depth_coverage = available_notional/order_notional
ATRNorm = ATR14/price
efficiency = abs(net_displacement)/total_path_variation
extension = (close-EMA20)/ATR14
relative_volume_H = volume_H/median(previous_60_non_overlapping_volume_H)
taker_imbalance = (buy_taker-sell_taker)/(buy_taker+sell_taker)
delta_i = buy_taker_volume_i-sell_taker_volume_i
CVD_t = cumsum(delta_i)
cvd_slope = TheilSenSlope(CVD_t)
obi_D = (bid_notional_D-ask_notional_D)/(bid_notional_D+ask_notional_D)
```

No se incorporaron los puntos `+6`, `-10`, los scores `70/20` ni los
horizontes 3-60 h. Las 38 fichas declaran los tres horizontes vigentes.

## 7. Atribucion por regla

Para cada una de las 11 reglas activas se conserva ahora:

- senal y formula aplicada;
- coeficiente o peso y su procedencia;
- log-efecto TP, SL y expiracion cuando existe;
- probabilidades completas;
- probabilidades recalculadas retirando la regla;
- delta de ablacion para TP, SL y expiracion;
- familia, padres, fuentes, formula y hash de traza.

El delta de ablacion sustituye como medida analitica al delta secuencial
dependiente del orden. El delta secuencial se conserva solo por compatibilidad
y explicacion del recorrido ejecutado.

## 8. Atribucion por familia

Cada analisis recalcula tambien el resultado retirando familias completas:

- trayectoria y MTF;
- niveles estructurales;
- volatilidad;
- interaccion trayectoria-volatilidad;
- flujo ejecutado;
- OI y precio-OI;
- dislocacion perpetua: basis, premium y funding.

Esto permite detectar doble conteo y medir valor incremental familiar.

## 9. Aprendizaje

El registro estructurado de cierre enlaza:

- operadores base;
- reglas activas;
- valores brutos y estandarizados;
- formulas, fuentes y hashes;
- ablacion individual;
- ablacion familiar;
- outcome TP, SL o expiracion/censura.

El aprendizaje no puede modificar produccion automaticamente.

Versiones:

```text
app-v0.23.3-probability-display-precision
learning-v0.6-microstructure-observation
learning-schema-v0.9-microstructure-observation
data-contract-v0.11-probability-precision
tp-sl-rule-library-runtime-v0.7
```

## 10. Limites

- Seis reglas candidatas estan implementadas en observacion sin efecto
  probabilistico: EMA/tendencia, RSI Wilder, extension EMA/ATR, volumen
  relativo, CVD de ventana exacta e imbalance visible del libro.
- Las otras dieciseis candidatas no estan implementadas en el runtime actual.
- No se han modificado los pesos ni probabilidades de las 11 actuales.
- No se ha resuelto todavia la doble utilizacion de evidencia; ahora queda
  identificada y medible mediante ablacion familiar.
- No se ha validado financieramente ninguna candidata.
- No se han mezclado reglas de ejecucion o riesgo con probabilidad de mercado.
- No se ha reanudado el aprendizaje automatico.

## 11. Verificacion

```text
645 pruebas ejecutadas
645 correctas
0 fallos
```

La suite cubre catalogo, contratos, reglas, motor probabilistico, ablacion
individual, ablacion familiar, cierre de aprendizaje y compatibilidad de la
aplicacion.

## 12. Siguiente trabajo

Seleccionar e implementar por familias las 22 candidatas, empezando por las
que ya disponen de datos fiables:

1. niveles y Fibonacci;
2. funding relativo y crowding;
3. breadth y sentimiento;
4. liquidaciones, aprovechando primero los 24 casos cerrados preservados;
5. reglas compuestas cuando sus reglas padre ya produzcan observaciones.

Cada familia debe completar formula, captura, traza, invariantes y prueba
antes de recibir cualquier efecto probabilistico.
