# Matriz de fuentes, teorias y limites de transferencia

Fecha: 2026-07-24
Fase: E1.2

## 1. Criterio

Cada referencia responde solo a una de estas preguntas:

1. Que significa el dato.
2. Como se define un indicador.
3. Si existe evidencia empirica de una familia de senales.
4. Como se valida una probabilidad.
5. De donde salio una regla interna.

Ninguna referencia se usa para afirmar mas de lo que demuestra.

## 2. Fuentes de datos oficiales

| Fuente | Acredita | No acredita |
|---|---|---|
| [Binance USD-M Futures Market Data](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) | Endpoints y campos de precio, klines, depth, aggTrades, funding, OI, long/short y taker buy/sell | Ventanas, umbrales, signos predictivos o pesos del motor |
| [CoinGecko Coins Markets](https://docs.coingecko.com/reference/coins-markets) | Variaciones y datos de mercado del universo consultado | Que top 100, 58/42 o +/-2 puntos predigan BTC |
| [CoinGecko Global](https://docs.coingecko.com/reference/crypto-global) | Capitalizacion, volumen y dominancia | Uso direccional concreto |
| [Alternative.me Fear & Greed](https://alternative.me/crypto/fear-and-greed-index/) | Escala, metodologia, API y composicion del indice | Penalizacion 75/25; el propio proveedor declara que no es recomendacion |

Conclusion: DAT-001 a DAT-011 tienen procedencia de campos. Sus
interpretaciones predictivas siguen siendo internas.

## 3. Manuales e indicadores

| Fuente | Acredita | Diferencia con el motor |
|---|---|---|
| [Wilder, New Concepts in Technical Trading Systems (1978)](http://dspace.lib.uom.gr/handle/2159/29408) | Procedencia de RSI y ATR | El codigo usa media simple de la ultima ventana, no todo el suavizado Wilder |
| [CFA Institute, Technical Analysis](https://www.cfainstitute.org/sites/default/files/-/media/documents/book/curriculum-update/2021-member-guide-refresher-readings.PDF) | Medias, cruces y osciladores como herramientas descriptivas | No ofrece nuestros pesos, caps ni probabilidad TP |

Conclusion:

- EMA: definicion reconocida; inicializacion y fallback propios.
- RSI/ATR: variantes implementadas, no replica exacta del original.
- Stack EMA, umbrales RSI y combinacion multi-TF: heuristicas.

## 4. Evidencia empirica sobre analisis tecnico

| Fuente primaria | Hallazgo transferible | Limite |
|---|---|---|
| [Brock, Lakonishok y LeBaron (1992)](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x) | Algunas reglas simples de medias y trading range mostraron estructura en una muestra historica del DJIA | Otro mercado, otro periodo; no valida BTC ni nuestros coeficientes |
| [Lo, Mamaysky y Wang (2000)](https://www.mit.edu/people/wangj/pap/LoMamayskyWang00.pdf) | Los patrones tecnicos pueden formalizarse y probarse estadisticamente | La formalizacion no prueba por si sola poder predictivo |
| [Osler (2000), Federal Reserve Bank of New York](https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.html) | Algunos soportes/resistencias ayudaron a anticipar interrupciones intradia en FX | No valida media de cinco extremos, barreras 35/55/85% ni BTC |
| [Cont, Kukanov y Stoikov](https://arxiv.org/abs/1011.6402) | El OFI dinamico en mejor bid/ask se relaciono con cambios de precio de corto plazo | Nuestro notional top-20 estatico y CVD de 500 aggTrades son proxies distintas |
| [Tsinaslanidis, Guijarro y Voukelatos (2022)](https://doi.org/10.1016/j.eswa.2021.115893) | Automatizo y evaluo retrocesos Fibonacci | No encontro diferencia estadistica frente a zonas no Fibonacci; no respalda bonus/penalizaciones |

Conclusion: hay fundamento para **investigar** tendencia, niveles y flujo. No
hay fundamento externo para convertirlos directamente en los puntos actuales.

## 5. Probabilidad y calibracion

| Fuente primaria | Exigencia | Situacion actual |
|---|---|---|
| [Brier (1950)](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2) | Comparar probabilidades con outcomes observados | Aun no existe validacion independiente suficiente |
| [Gneiting y Raftery (2007)](https://doi.org/10.1198/016214506000001437) | Usar scoring rules propios para previsiones probabilisticas | El score actual es suma manual de biases |
| [Dimitriadis, Gneiting y Jordan (2020/2021)](https://arxiv.org/abs/2008.03033) | Calibracion significa correspondencia entre probabilidad y frecuencia observada | La etiqueta `tp_probability` no ha demostrado esa correspondencia |

Conclusion: un numero acotado entre 0 y 1 no es automaticamente probabilidad.
El motor necesita outcomes mutuamente excluyentes, holdout temporal, Brier,
log-loss, curvas de fiabilidad e incertidumbre.

## 6. Evidencia interna

| Fuente | Reglas originadas | Fuerza |
|---|---|---|
| `auditorias_aprendizaje/2026-07-06_operaciones_cerradas_184_auditoria_profunda_motor_v0_9.md` | Frenos v0.10 sobre SL, TP distante, R/R, stops, 24h, EMA y zonas | Provisional: 67 operaciones v0.9 resueltas y muchos subgrupos pequenos |
| `HISTORIAL_CAMBIOS_MOTOR_ANALISIS.md` | Versiones, motivacion, clusters v0.11 y heatmap v0.12 | Trazabilidad, no validacion |
| `ESPECIFICACION_MOTOR_ANALISIS.md` | Intencion funcional y separacion de capas | Especificacion, no evidencia |
| Auditoria `learning-v0.2` de 93 casos recalculados | Cluster Fibonacci extremo + sentimiento, CVD y RSI contextual | Muy provisional: el cluster principal tenia tres fallos |

Conclusion: los frenos v0.10/v0.11 son la unica modificacion del analisis
procedente del aprendizaje hasta la fecha. Se implementaron manualmente y deben
compararse con casos nuevos de la misma version; no son aprendizaje automatico.

## 7. Clasificacion por familia

| Familia | Concepto | Implementacion exacta | Peso exacto | Decision |
|---|---|---|---|---|
| Precio/velas | fundamentada | fundamentada | no aplica | mantener |
| EMA | fundamentada | fundamentada con supuestos | heuristica | auditar ventanas |
| RSI/ATR | fundamentada | variante heuristica | heuristica | corregir o renombrar |
| Tendencia multi-TF | evidencia mixta | heuristica | heuristica | calibrar |
| Soporte/resistencia | evidencia parcial | heuristica | heuristica | comparar detectores |
| Fibonacci | evidencia no concluyente | heuristica | heuristica | ablation/posible retirada |
| Order book/flujo | evidencia microestructural | proxy provisional | heuristica | peso bajo y validacion |
| Funding/OI/ratios | dato fundamentado | ventanas internas | heuristica | validar por horizonte |
| Breadth/sentimiento | dato fundamentado | universo/umbrales internos | heuristica | validar o retirar |
| Zonas pendientes | intuicion operativa | heuristica | empirica_provisional | sombra y holdout |
| Frenos v0.10/v0.11 | evidencia interna | reproducible | empirica_provisional | no ampliar |
| Heatmap | tercero Hyperliquid | normalizacion heuristica | fuera de scoring | seguir observacional |
| TP/SL/rango | objetivo correcto | suma residual incoherente | no calibrado | sustituir en challenger |
| EV | formula fundamentada | costes simplificados | depende de TP/SL no calibrados | mantener solo orientativa |
| Grado/confianza/decision | gobernanza util | heuristica | heuristica | separar de probabilidad |
| Etiquetas aprendizaje | taxonomia util | retrospectiva | no predictiva | mantener fuera de features |

## 8. Reglas sin fuente exacta demostrable

No se encontro publicacion, manual o metodologia oficial que justifique:

- Base TP de 50%.
- Caps TP 22%-74%.
- Salto precio/entrada de +3/-2 puntos.
- Pesos temporales y multiplicadores micro/derivados/macro.
- Cada umbral y delta de SCO-001 a SCO-026.
- Formulas de activacion, rechazo, ruptura y barrida.
- Suma de riesgo y cortes 0.12/0.24/0.42.
- Notas A/B/C/D y cortes de confianza.
- Bandas visuales de 4/6/8 puntos.
- Fee fijo, un unico funding y slippage minimo usados para todos los usuarios.

Procedencia de todos ellos: diseno interno o auditoria interna provisional.
Estado: `heuristica` o `empirica_provisional`, nunca `fundamentada`.

## 9. Resultado de cobertura

La matriz JSON generada enlaza las 185 funciones con:

- archivo y lineas;
- huella de la funcion;
- rol;
- estado;
- declaracion de procedencia;
- fuentes que aplican;
- decision propuesta;
- literales y formulas del inventario E1.1.

Conteos:

```text
funciones                         185
funciones con regla/convencion    105
fundamentadas                      72
empiricas provisionales            14
heuristicas                        99
literales numericos              1528
fragmentos de formula            3317
```

SHA-256 de matriz:
`8a99436bc183a30bc5470a4fb423382dee4b1484ec951e175e5d001093490142`

## 10. Dictamen E1.2

El motor no esta construido al azar: combina familias reconocibles de analisis
tecnico, microestructura, derivados y gestion de riesgo. El problema es mas
preciso:

1. Los datos suelen tener fuente identificable.
2. Varias transformaciones tienen una definicion reconocida.
3. La mayoria de umbrales y pesos son convenciones internas.
4. La unica evidencia propia que ya modifico el motor es pequena, retrospectiva
   y no independiente.
5. La salida principal se denomina probabilidad sin haber superado una prueba
   de calibracion.

Por ello E1.3 debe atacar primero monotonicidad, discontinuidades, doble conteo
y semantica probabilistica antes de medir impacto historico en E1.4.
