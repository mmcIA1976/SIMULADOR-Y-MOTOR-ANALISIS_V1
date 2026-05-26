# Fuentes de datos y analisis

Este documento define de donde recoger informacion actualizada para el motor de entrenamiento y que fuentes pueden ayudar a interpretar esos datos.

El objetivo es construir un sistema que no dependa de una sola senal. El motor debe cotejar precio, flujo, derivados, macro, noticias, contexto de riesgo y comportamiento del usuario.

## Principio de diseno

No todas las fuentes deben entrar desde el primer dia.

Se recomienda trabajar por capas:

1. Datos gratuitos y robustos para el MVP.
2. Datos agregados de derivados y liquidez cuando el sistema ya registre operaciones.
3. Datos institucionales o premium cuando necesitemos precision profesional.
4. Analisis experto para contrastar interpretaciones, no para copiar senales.

## Capa 1: Mercado base

### Binance

Uso:

- precio actual
- velas OHLCV
- order book
- trades agregados
- volumen
- volumen taker buy
- futuros USDT-M
- funding
- open interest
- ratios long/short disponibles

Valor:

- fuente directa del exchange
- buena para empezar
- datos de alta frecuencia
- sin necesidad de API privada para endpoints publicos

Limitacion:

- representa principalmente Binance, no todo el mercado
- puede sesgar el analisis si se usa como unica fuente

Fuente:

- https://developers.binance.com/en

## Capa 2: Derivados agregados

### CoinGlass

Uso:

- open interest multi-exchange
- funding rates
- liquidaciones
- liquidation heatmap
- long/short ratios
- datos de opciones y contratos

Valor:

- muy util para entender posicionamiento
- permite cotejar Binance contra el mercado agregado
- clave para detectar exceso de apalancamiento

Limitacion:

- algunas funciones requieren API key o plan de pago
- hay que validar latencia y cobertura segun plan

Fuente:

- https://docs.coinglass.com/v3.0/reference

### Coinalyze

Uso:

- open interest
- funding
- CVD
- liquidaciones
- long/short ratios

Valor:

- muy practico para traders
- bueno para validar rapidamente lectura de derivados

Limitacion:

- revisar condiciones de API y limites antes de integrarlo.

Fuente:

- https://coinalyze.net/

## Capa 3: Liquidez y microestructura profesional

### Kaiko

Uso:

- trades historicos y en tiempo real
- order book nivel 1 y nivel 2
- profundidad de mercado
- spread
- slippage
- liquidez por exchange
- datos normalizados multi-exchange

Valor:

- enfoque institucional
- muy util para medir liquidez real
- permite estudiar si una entrada tiene buena ejecucion o riesgo de barrido

Limitacion:

- orientado a planes profesionales
- puede ser excesivo para el MVP

Fuentes:

- https://www.kaiko.com/products/market-data/derivatives-data
- https://research.kaiko.com/insights/centralized-exchange-liquidity
- https://docs.kaiko.com/explore-our-data/data-dictionary

## Capa 4: On-chain

### Glassnode

Uso:

- MVRV
- SOPR
- actividad on-chain
- flujos hacia/desde exchanges
- metricas de holders
- metricas de entidades
- contexto de ciclo de mercado

Valor:

- referencia fuerte para analisis on-chain
- util para entender contexto estructural de BTC
- aporta datos que no se ven en el grafico

Limitacion:

- muchas metricas avanzadas/API requieren plan profesional
- menos util para scalping puro que para contexto de mercado

Fuentes:

- https://docs.glassnode.com/
- https://docs.glassnode.com/basic-api/api
- https://docs.glassnode.com/data/metric-catalog
- https://insights.glassnode.com/tag/newsletter/

### CryptoQuant

Uso:

- exchange reserves
- miner flows
- stablecoin flows
- whale activity
- on-chain alerts

Valor:

- muy seguido por traders crypto
- util para detectar presion potencial de oferta/demanda

Limitacion:

- revisar disponibilidad de API, plan y limites.

Fuente:

- https://cryptoquant.com/

## Capa 5: Macro y mercados cruzados

### Trading Economics

Uso:

- calendario economico
- datos macro
- indices bursatiles
- bonos
- divisas
- commodities
- eventos en tiempo real por API

Valor:

- fuente muy completa para eventos macro
- util para marcar riesgo antes de CPI, FOMC, NFP, PMI, etc.

Fuentes:

- https://docs.tradingeconomics.com/
- https://docs.tradingeconomics.com/economic_calendar/streaming/

### FRED

Uso:

- tipos de interes
- inflacion
- desempleo
- liquidez
- spreads
- datos macro historicos

Valor:

- fuente oficial/academica para macro historica
- muy buena para backtesting de regimenes macro

Fuente:

- https://fred.stlouisfed.org/

### CME FedWatch

Uso:

- probabilidades implicitas de decisiones de tipos de la Fed
- contexto de expectativas monetarias

Valor:

- muy relevante para BTC cuando el mercado opera como activo de riesgo

Fuentes:

- https://www.cmegroup.com/fedwatch
- https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html

### Nasdaq Data Link

Uso:

- datos de indices
- datos financieros
- datasets macro/mercado
- datos gratuitos y premium

Valor:

- buena fuente para mercado tradicional y datasets institucionales

Fuente:

- https://docs.data.nasdaq.com/

## Capa 6: Noticias y sentimiento

### Alpha Vantage

Uso:

- noticias de mercado
- sentimiento
- indicadores tecnicos
- cripto, forex, commodities, indices y acciones

Valor:

- buena fuente inicial para noticias/sentimiento por API
- puede filtrar temas como blockchain, mercados financieros, macro y politica monetaria

Fuente:

- https://www.alphavantage.co/documentation/

### Fuentes periodisticas y especializadas

Uso:

- validar eventos relevantes
- guerras
- regulacion
- hackeos
- problemas de exchanges
- ETF flows
- contexto institucional

Fuentes candidatas:

- Reuters
- Bloomberg
- Financial Times
- CoinDesk
- The Block
- Decrypt
- Cointelegraph solo como fuente secundaria

Regla:

El sistema no debe basar una conclusion en una sola noticia. Debe cruzar fuente, hora, impacto y relacion con BTC.

## Capa 7: Analisis experto para interpretar

Estas fuentes no deben alimentar directamente el score como si fueran senales automaticas. Sirven para contrastar interpretaciones y construir reglas.

### Glassnode Insights

Valor:

- lectura profesional de on-chain y estructura de mercado
- buena para aprender como interpretar MVRV, SOPR, oferta en beneficio/perdida, ETF flows, etc.

Fuente:

- https://insights.glassnode.com/tag/newsletter/

### Kaiko Research

Valor:

- investigacion sobre liquidez, spreads, profundidad, slippage y estructura de mercado crypto

Fuente:

- https://research.kaiko.com/

### Coinbase Institutional Research

Valor:

- perspectiva institucional
- posicionamiento de mercado
- relacion entre macro, renta variable y crypto

Fuente:

- https://www.coinbase.com/institutional/research-insights/research

### CME

Valor:

- entender futuros regulados
- open interest institucional
- expectativas de tipos
- relacion macro/riesgo

Fuente:

- https://www.cmegroup.com/

## MVP recomendado

Para empezar sin coste excesivo:

1. Binance:
   - precio
   - velas
   - volumen
   - order book simple
   - funding
   - open interest
   - taker buy volume

2. CoinGecko:
   - universo de activos crypto
   - ranking por capitalizacion
   - datos basicos para activos top
   - validacion de disponibilidad de pares

3. Trading Economics o calendario alternativo:
   - eventos macro relevantes
   - impacto estimado
   - hora del evento

4. Alpha Vantage u otra fuente gratuita viable:
   - noticias/sentimiento basico

5. Registro interno:
   - resultado de operaciones
   - comportamiento por usuario
   - estado emocional al cierre
   - acierto de recomendaciones

Condicion:

Las fuentes iniciales deben tener uso gratuito o demo suficiente para conectividad recurrente durante desarrollo. Si una API gratuita no es estable, se encapsula como conector opcional y el sistema sigue funcionando con las fuentes disponibles.

## Fase profesional

Cuando el sistema tenga suficientes operaciones:

1. CoinGlass o Coinalyze para derivados agregados.
2. Glassnode o CryptoQuant para on-chain.
3. Kaiko para liquidez y microestructura institucional.
4. Nasdaq Data Link/Trading Economics para macro y mercado tradicional.

## Como convertir datos en conclusion

El motor no debe decir:

```text
Funding positivo, comprar/vender.
```

Debe decir:

```text
Funding positivo + open interest subiendo + precio extendido + evento macro cercano = riesgo de long tardio.
```

Ejemplo de salida:

```text
Probabilidad TP: 52%
Probabilidad SL: 41%
Probabilidad rango: 7%
Riesgo: medio-alto
Confianza: media

Motivos:
- Tendencia corta favorable.
- Funding demasiado alto para perseguir precio.
- OI subiendo indica apalancamiento fresco.
- Stop actual queda dentro del ruido de volatilidad.
- No hay evento macro critico en los proximos 90 minutos.
```

## Regla final

Una fuente aporta datos. El sistema debe aportar criterio.
