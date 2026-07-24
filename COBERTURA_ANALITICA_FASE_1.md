# Cobertura analitica objetivo - Fase 1

Fecha: 2026-07-24
Contrato rector: `CONTRATO_FASE_1_MOTOR_ANALISIS.md`
Origen: listado de 34 bloques aportado por el propietario del proyecto

## 1. Uso de este documento

Esta matriz evita dos errores:

- afirmar que la aplicacion ya obtiene datos que realmente no posee;
- incorporar familias completas sin definir y validar cada variable.

Estados:

- `actual`: existe una implementacion util, aunque deba reauditarse;
- `parcial`: existe una parte limitada o una proxy;
- `ausente`: no existe;
- `investigacion`: no debe entrar en produccion sin definicion y evidencia.

Prioridades:

- `P0`: necesaria para el nucleo probabilistico de Fase 1;
- `P1`: ampliacion fiable de alto valor;
- `P2`: contexto adicional despues del nucleo;
- `P3`: especializada o de fases posteriores.

## 2. Matriz de los 34 bloques

| # | Bloque | Estado real | Prioridad | Decision de Fase 1 |
|---:|---|---|---|---|
| 1 | Estructura del precio | parcial | P0 | Formalizar pivotes, tendencia, BOS/CHoCH, rangos, rupturas, niveles y sesiones con reglas reproducibles |
| 2 | Indicadores tecnicos | parcial | P1 | Seleccionar pocos indicadores no redundantes; corregir definiciones antes de ampliar catalogo |
| 3 | Multi-timeframe | parcial | P0 | Redisenar jerarquicamente; no usar cada timeframe como voto independiente |
| 4 | Patrones y metodologias discrecionales | investigacion | P3 | Solo formulas reproducibles; Fibonacci actual queda en cuestion |
| 5 | Velas japonesas | datos disponibles, reglas ausentes | P1 | Convertir cuerpo, rango, mechas y secuencias en variables; no usar nombres visuales aislados |
| 6 | Volumen y subasta | ausente salvo volumen simple | P1 | Construir VWAP primero; Volume Profile despues con datos adecuados |
| 7 | Order flow | parcial | P0 | CVD Futures actual es proxy corta; crear historico persistente, delta por intervalo y calidad |
| 8 | Libro y microestructura | parcial | P1 | Top-20 snapshot actual; estudiar streams, microprecio, resiliencia y slippage sin asumir permanencia |
| 9 | Open interest | parcial | P0 | Ya existe OI y cambio 5m/1h/1d; faltan historico, percentiles, aceleracion y normalizacion |
| 10 | Funding | parcial | P0 | Ya existe actual y media corta; faltan cambio, percentil, acumulado y contexto |
| 11 | Prima, basis y curva | parcial | P1 | Mark e index existen; calcular premium/basis y validar spot/futuros con unidades coherentes |
| 12 | Liquidaciones | parcial | P1 | Hyperliquid observacional; separar ejecutadas de mapas estimados y validar proveedor/alcance |
| 13 | Posicionamiento long/short | parcial | P1 | Ratio global y taker existen; faltan top traders, posiciones, percentiles y comparacion |
| 14 | Opciones | ausente | P2 | Evaluar API publica Deribit para IV, skew, term structure y OI; contexto, no disparador inicial |
| 15 | Spot contra futuros | ausente | P0 | Incorporar spot real y CVD spot antes de afirmar divergencias spot-futures |
| 16 | Cross-exchange y arbitraje | ausente | P3 | Requiere normalizacion y sincronizacion estrictas; no es nucleo inicial |
| 17 | On-chain | ausente | P2 | Solo fuentes gratuitas fiables; contexto por marco temporal, no disparador |
| 18 | Tokenomics y fundamental | ausente | P2 | Prioridad mayor para altcoins; necesita eventos versionados y fuentes verificables |
| 19 | Macroeconomia | ausente | P1 | Calendario, sorpresa, DXY, yields e indices; controlar timestamps y revisiones |
| 20 | Intermercado | ausente | P1 | Correlaciones moviles y por regimen; nunca relaciones fijas |
| 21 | Amplitud y rotacion | parcial | P1 | Top-100 CoinGecko actual; convertir en regimen de participacion y auditar sesgos |
| 22 | Sentimiento | parcial | P2 | Solo Fear & Greed actual; no usar como señal aislada ni asumir contrarian |
| 23 | Noticias y eventos | ausente | P2 | Requiere fuente, timestamp, credibilidad, sorpresa e impacto por activo |
| 24 | Regimen de mercado | parcial y primitivo | P0 | Redisenar como capa que habilita/bloquea reglas, no como bonus aislado |
| 25 | Estacionalidad y tiempo | ausente como analisis | P1 | Derivar sesiones y eventos temporales; validar estadisticamente |
| 26 | Estadistica y cuantitativo | parcial | P0 | Base de alcanzabilidad, volatilidad, distribuciones, bootstrap y modelos interpretables |
| 27 | Machine learning e IA | ausente | P3 | Solo despues de dataset limpio; empezar interpretable, sin redes/RL prematuros |
| 28 | Probabilidad TP/SL | implementacion actual no valida | P0 | Reconstruir completamente; triple-barrier para outcomes y calibracion real |
| 29 | Ejecucion y costes | parcial | P0 | Spread y coste fijo actuales son insuficientes; modelar fees, slippage, funding y tipo de orden |
| 30 | Gestion de riesgo | parcial | P0 | Separar probabilidad tecnica de exposicion; definir limites y riesgo de liquidacion |
| 31 | Cartera | parcial operativo | P3 | Importante para Fases 2/3; correlacion y riesgo agregado aun ausentes |
| 32 | Evaluacion de rendimiento | parcial | P0 | Ya existe normalizacion economica; completar calibracion, costes y desglose por regla |
| 33 | Psicologia y conducta | parcial | P3 | Solo para usuario/intervencion; nunca reducir probabilidad de mercado por conducta |
| 34 | Riesgo operativo y contraparte | parcial | P1 | Diagnosticos y backoff existen; faltan WebSocket, calidad, failover, claves y cambios de contrato |

## 3. Inventario real de datos actual

### Disponible actualmente

- precio Binance USD-M Futures;
- klines Futures 5m, 15m, 1h, 4h, 1d y 1w;
- order book top 20 Futures;
- 500 aggTrades Futures por snapshot;
- ticker Futures 24h;
- funding actual e historial corto;
- OI actual y cambios 5m/1h/1d;
- long/short global y taker buy/sell Futures;
- mercado global y top-100 CoinGecko;
- Fear & Greed Alternative.me;
- mapa HyperPerps limitado a posiciones publicas Hyperliquid;
- operaciones, recomendaciones, ticks y outcomes propios.

### Derivados actuales que deben reauditarse

- EMA;
- RSI variante de media simple;
- ATR variante de media simple;
- rango y volumen relativo;
- soportes/resistencias heuristicas;
- Fibonacci heuristico;
- imbalance estatico top-20;
- CVD aproximado de muestra corta;
- breadth;
- regimen primitivo;
- score TP/SL actual no valido como probabilidad.

### No disponible actualmente

- spot y CVD spot;
- CVD persistente;
- VWAP y Volume Profile;
- profundidad historica y eventos del libro;
- liquidaciones ejecutadas multi-exchange;
- OI/funding agregados multi-exchange;
- basis spot-perpetuo completo;
- opciones;
- macro e intermercado;
- on-chain;
- noticias y calendario;
- tokenomics;
- modelos probabilisticos calibrados;
- machine learning predictivo;
- riesgo agregado de cartera.

## 4. Orden de construccion propuesto

### Bloque A - Dataset y outcomes

1. Semantica TP/SL/horizonte.
2. Triple-barrier para verdad historica.
3. Snapshot pre-trade completo.
4. Sincronizacion, frescura y unidades.
5. Costes y evidencia de ejecucion.

### Bloque B - Nucleo de mercado

1. Estructura de precio.
2. Volatilidad y alcanzabilidad.
3. Multi-timeframe jerarquico.
4. Volumen y VWAP.
5. Flujo Futures persistente.
6. OI, funding y premium.
7. Spot contra Futures.
8. Regimen.

### Bloque C - Probabilidad y aprendizaje

1. Baseline matematico interpretable.
2. Features aprobadas.
3. Trazabilidad por regla.
4. Reglas combinadas pre-registradas.
5. Walk-forward.
6. Calibracion.
7. Champion/challenger.
8. Ablation y retirada de reglas.

### Bloque D - Expansiones

1. Liquidaciones.
2. Order book avanzado.
3. Macro e intermercado.
4. Opciones.
5. Cross-exchange.
6. On-chain, noticias y tokenomics.

## 5. Criterio de admision de una variable

Una variable solo entra al challenger si:

1. Tiene fuente fiable y gratuita autorizada.
2. Puede obtenerse en tiempo real y reconstruirse historicamente.
3. Tiene timestamp, unidad y calidad.
4. Su formula es reproducible.
5. Su hipotesis esta documentada.
6. No contiene datos posteriores al analisis.
7. No duplica otra variable sin control.
8. Tiene una prueba de utilidad incremental.
9. Su ausencia tiene comportamiento definido.
10. Su contribucion queda registrada.

## 6. Regla de alcance

El objetivo no es implementar el mayor numero de indicadores. El objetivo es
incorporar todos los puntos de vista para los que existan datos fiables,
formulas defendibles y evidencia medible, conservando solo los que mejoren el
motor.

La cobertura se disena para todos los pares soportados por la aplicacion y para
los tres marcos vigentes: `intraday_short`, `intraday_wide` y `short_swing`.
Cada dato, variable y regla debe declarar su disponibilidad y validez por par y
marco temporal.
