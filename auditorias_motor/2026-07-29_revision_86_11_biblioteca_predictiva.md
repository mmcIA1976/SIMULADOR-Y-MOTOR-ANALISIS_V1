# Revision 86 -> 11 para la biblioteca predictiva

Fecha: 2026-07-29
Estado: DIAGNOSTICO; NO MODIFICA PRODUCCION

## 1. Objetivo fijado

La fase 1 global debe construir una biblioteca amplia de hipotesis
predictivas para estimar, antes de operar:

- `P(TP primero dentro del horizonte)`;
- `P(SL primero dentro del horizonte)`;
- `P(ninguna barrera antes del vencimiento)`.

Una regla puede comenzar sin validacion propia, pero no puede comenzar sin:

1. identidad y version;
2. dato y proveedor;
3. formula exacta;
4. fundamento externo o declaracion explicita de hipotesis del proyecto;
5. condiciones de aplicacion y no aplicacion;
6. semantica esperada sobre TP, SL o vencimiento;
7. familia e interacciones declaradas;
8. traza preoperacion y enlace posterior con el outcome.

Una fuente que define un indicador no demuestra su poder predictivo. Una
formula o peso interno nunca debe presentarse como publicado si no lo esta.

## 2. Que eran realmente las 86 entradas

El catalogo exacto
`catalogo_exacto_reglas_formulas_m1_v0_1.json` contiene 86 entradas completas
respecto al codigo antiguo, pero no 86 reglas predictivas independientes:

| Capa antigua | Entradas | Funcion real |
|---|---:|---|
| Contratos de datos | 7 | Transportar observaciones |
| Transformaciones | 14 | Calcular variables |
| Ajustes predictivos | 29 | Alterar el score antiguo |
| Gates de calibracion/riesgo | 19 | Aplicar umbrales y clusters |
| Salidas y politicas | 17 | Convertir, limitar o presentar resultados |

Por tanto:

- `86` es el inventario completo del mecanismo antiguo;
- `48` entradas alteraban el resultado mediante scores o gates;
- varias de esas 48 reutilizaban el mismo dato o eran agregadores;
- ninguna de las 86 tenia autorizacion probatoria externa para convertir
  directamente su salida en una probabilidad TP/SL.

## 3. Revision de las 7 entradas de datos

| Entrada | Decision para la biblioteca |
|---|---|
| DATA-PRICE-KLINES | Conservar como fuente primaria |
| DATA-DEPTH-TRADES | Conservar; distinguir trades de eventos completos del libro |
| DATA-DERIVATIVES | Conservar por variables separadas |
| DATA-BREADTH | Conservar como contexto candidato, no como regla implicita |
| DATA-GLOBAL | Conservar como contexto candidato |
| DATA-SENTIMENT | Conservar como dato externo, con frescura y metodologia |
| DATA-LIQUIDATIONS | Conservar como observacion; no confundir Hyperliquid con mapa agregado |

Estas entradas no son reglas predictivas. Deben registrar proveedor,
timestamp del proveedor, timestamp de recepcion, frescura, unidad, cobertura,
ausencia y huella del payload.

## 4. Revision de las 14 transformaciones

| Entrada | Decision |
|---|---|
| PLAN-TP-LOG-DISTANCE | Conservar; entrada esencial del modelo de barreras |
| PLAN-SL-LOG-DISTANCE | Conservar; entrada esencial del modelo de barreras |
| PLAN-LOG-HORIZON-SECONDS | Conservar; no es predictor independiente |
| PLAN-SIDE-SIGN | Conservar como codificacion |
| IND-EMA-CORE | Conservar como operador estandar |
| IND-EMA200-FALLBACK | Retirar el fallback 80->EMA200; no representa EMA200 |
| IND-RSI14-CURRENT | Corregir a Wilder o renombrar exactamente la variante |
| IND-ATR14-CURRENT | Corregir a Wilder o renombrar exactamente la variante |
| IND-EMA-STACK | Recuperar como familia candidata, sin votos fijos |
| IND-SUPPORT-RESISTANCE | Redisenar detector reproducible antes de usar |
| IND-FIBONACCI | Recuperar niveles como hipotesis contextual, no bonus automatico |
| IND-ORDERBOOK-PROXY | Conservar como proxy de snapshot, no llamarlo OFI |
| IND-CVD-PROXY | Recuperar solo con ventana temporal exacta |
| IND-PENDING-ZONE | Fuera del alcance actual MARKET; conservar para una fase futura |

Las transformaciones pueden alimentar una o varias reglas, pero no deben
contarse como evidencia adicional cuando reutilizan el mismo dato.

## 5. Revision individual de los 29 ajustes predictivos antiguos

| ID antiguo | Decision de recuperacion |
|---|---|
| SCORE-TREND_BIAS | Recuperar como hipotesis de tendencia EMA |
| SCORE-TECHNICAL_DIRECTION_BIAS | No recuperar como regla; era un contenedor de otras senales |
| SCORE-PRICE_VS_ENTRY_BIAS | Sustituir por geometria/frescura; en MARKET la entrada es el precio analizado |
| SCORE-VOLUME_BIAS | Recuperar con formula, ventana y normalizacion exactas |
| SCORE-ORDER_BOOK_BIAS | Recuperar como proxy microestructural separado |
| SCORE-MOMENTUM_BIAS | Recuperar RSI como hipotesis continua y contextual |
| SCORE-MARKET_REGIME_BIAS | Redisenar como interaccion explicita, no score agregado |
| SCORE-FIBONACCI_PROBABILITY_ADJUSTMENT | Recuperar como distancia/confluencia medible, sin puntos heredados |
| SCORE-ZONE_PROBABILITY_ADJUSTMENT | Fuera del alcance MARKET actual |
| SCORE-TAKER_FLOW_BIAS | Ya representado por aggressor imbalance |
| SCORE-CVD_BIAS | Recuperar si existe ventana completa |
| SCORE-OI_TREND_BIAS | Ya representado por OI y precio-OI; evitar duplicacion |
| SCORE-BREADTH_BIAS | Recuperar como contexto de mercado |
| SCORE-VOLATILITY_PENALTY | Integrar como interaccion distancia/sigma, no sumar otra penalizacion |
| SCORE-LIQUIDITY_PENALTY | Separar probabilidad fisica de coste/ejecucion |
| SCORE-OVEREXTENSION_PENALTY | Recuperar como hipotesis tendencia/reversion condicionada |
| SCORE-FUNDING_PENALTY | Ya representado por funding continuo |
| SCORE-FUNDING_RELATIVE_PENALTY | Recuperar como funding frente a su propia historia |
| SCORE-CROWDING_PENALTY | Recuperar ratios de posicionamiento como hipotesis |
| SCORE-LEVEL_PENALTY | Recuperar con detector reproducible de niveles |
| SCORE-SENTIMENT_PENALTY | Recuperar como hipotesis contextual, sin 75/25 heredado |
| SCORE-HIGHER_TIMEFRAME_PENALTY | Ya representado por MTF; no duplicar |
| SCORE-TECHNICAL_ENTRY_TIMING_PENALTY | No recuperar como regla; era un agregado |
| SCORE-TECHNICAL_BARRIER_PENALTY | Convertir en interaccion explicita nivel-plan |
| SCORE-OI_CONTEXT_PENALTY | Ya representado por precio-OI; no duplicar |
| SCORE-CONTRADICTION_PENALTY | No recuperar como regla; registrar cada interaccion concreta |
| SCORE-RISK_CALIBRATION_TP_ADJUSTMENT | Pertenece a calibracion, no a la biblioteca de evidencia |
| SCORE-ZONE_RANGE_PROBABILITY_ADJUSTMENT | Fuera del alcance MARKET actual |
| SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT | Pertenece a calibracion, no es evidencia |

Resultado:

- 14 familias o extensiones antiguas merecen recuperacion/redeseno;
- 8 eran duplicados, contenedores o agregados;
- 2 pertenecen a entradas pendientes;
- 3 pertenecen a calibracion o geometria, no a evidencia independiente;
- 2 deben permanecer en ejecucion/costes o frescura.

## 6. Revision de los 19 gates antiguos

Los gates 51-69 no deben regresar como 19 reglas binarias con puntos fijos.
Sus cortes (`55`, `50`, `40`, `3`, `0.25`, etc.) eran convenciones internas.

Se conservan sus ideas mediante tres destinos:

1. **Geometria del plan**: distancias TP/SL, R/R y horizonte ya entran en el
   modelo base; volver a puntuarlas produce doble conteo.
2. **Interacciones candidatas**: contradiccion MTF, nivel delante del TP,
   sobreextension, RSI-regimen, Fibonacci-sentimiento y flujo contrario deben
   tener IDs propios y variables continuas.
3. **Politicas**: calidad de entrada, riesgo economico o autorizacion para
   simular no deben modificar la probabilidad fisica de tocar barreras.

Los cuatro clusters retrospectivos de Fibonacci, sentimiento, CVD y RSI se
conservan como hipotesis de interaccion. Sus outcomes pasados no pueden entrar
como variables preoperacion.

## 7. Revision de las 17 salidas y politicas antiguas

No son reglas predictivas:

- OUT-TP-ADDITIVE, OUT-TP-CAPS, OUT-RANGE y OUT-SL-RESIDUAL eran el mecanismo
  de conversion del score antiguo y quedan sustituidos por riesgos competitivos.
- OUT-PROBABILITY-BANDS era presentacion heuristica.
- OUT-EV-COST, OUT-FEE, OUT-SLIPPAGE y OUT-FUNDING-COST pertenecen a la capa
  economica.
- OUT-RISK-SCORE, OUT-GRADE, OUT-CONFIDENCE y OUT-DECISION son politicas o
  presentacion.
- OUT-LAYERED-SCORES es un contenedor.
- OUT-HORIZON-FALLBACK y OUT-MISSING-DATA no deben ocultar ausencia real.
- OUT-RISK-CAL-METRIC era una metrica visual.

Se deben conservar las identidades economicas utiles, pero no contarlas como
reglas que predicen TP o SL.

## 8. Auditoria de las 11 reglas activas actuales

### 8.1 Estructura de trayectoria

- ID: `M4-RULE-PATH-STRUCTURE-001`.
- Formula: `SE_H=sum(r_i)/sum(abs(r_i))`.
- Uso: individual, ajustado al lado de la operacion.
- Efecto actual: log-peso TP `+0.12*side*SE_H`; SL con signo contrario.
- Fundamento: trayectoria/momentum como familia investigable.
- Problema: `0.12` no procede de publicacion ni estimacion; ademas H fue
  eliminado del candidato ajustado y despues reintroducido por overlay.
- Traza: senal, peso, delta TP/SL y hash disponibles.
- Dictamen: conservar como hipotesis; justificar o aprender el peso.

### 8.2 Extremo previo entre entrada y TP

- ID: `M4-RULE-PRIOR-EXTREMA-001`.
- Formula: indicador binario de maximo/minimo previo entre entrada y objetivo.
- Uso: individual dentro del modelo ajustado.
- Fundamento: niveles previos como posible interrupcion de trayectoria.
- Efecto actual: coeficientes TP/SL estimados en el candidato historico.
- Problema: un unico bit pierde distancia, numero y prominencia del nivel.
- Traza: valor bruto, estandarizado y coeficientes; falta delta probabilistico
  individual copiado al registro estructurado de aprendizaje.
- Dictamen: conservar y ampliar a una representacion continua.

### 8.3 Percentil de volatilidad

- ID: `M4-RULE-VOLATILITY-RANK-001`.
- Formula: midrank de RV_H frente a 60 ventanas anteriores.
- Uso: individual en el modelo y parte de la interaccion de regimen.
- Fundamento: persistencia/heterogeneidad de volatilidad.
- Problema: reutilizacion doble de la misma familia; el numero 60 es politica
  del proyecto.
- Traza: valor y coeficientes; falta atribucion probabilistica marginal estable.
- Dictamen: conservar; declarar usos principal e interactivo.

### 8.4 Jerarquia multi-timeframe

- ID: `M4-RULE-MTF-HIERARCHY-001`.
- Formula: `side*SE_2H` y `side*SE_4H`.
- Uso: regla de grupo con dos covariables ajustadas.
- Fundamento: momentum/estructura a diferentes escalas, evidencia transferible
  solo como hipotesis.
- Problema: la regla agrupa dos efectos y el aprendizaje debe conservar ambos.
- Traza: valores y coeficientes por feature; no delta final por feature.
- Dictamen: conservar como grupo y registrar sus componentes.

### 8.5 Regimen continuo

- ID: `M4-RULE-CONTINUOUS-REGIME-001`.
- Formula actual: `side*SE_H*(2*q_RV-1)`.
- Uso: interaccion trayectoria-volatilidad.
- Efecto actual: peso fijo `0.08`.
- Problema: la formula obliga a invertir el signo de la trayectoria por debajo
  de la mediana de volatilidad. Esa semantica exacta no esta respaldada por la
  documentacion publicada.
- Traza: completa para el overlay.
- Dictamen: mantener solo como hipotesis explicita y revisar su forma.

### 8.6 Desequilibrio agresor

- ID: `M4-RULE-AGGRESSOR-IMBALANCE-001`.
- Formula: `ATI_H=(B_H-S_H)/(B_H+S_H)`.
- Uso: individual, alineado con el lado.
- Fundamento: relacion entre flujo ejecutado y cambios de precio a corto plazo;
  no equivale a OFI completo.
- Efecto actual: peso fijo `0.12`.
- Problema: peso y transferencia entre horizontes no estan estimados.
- Traza: completa.
- Dictamen: conservar y evaluar por horizonte/regimen.

### 8.7 Actividad de open interest

- ID: `M4-RULE-OPEN-INTEREST-CHANGE-001`.
- Formula base: `dOI_H=ln(OI_t/OI_(t-H))`.
- Senal actual: `tanh(50*abs(dOI_H))`.
- Uso: movimiento; aumenta simultaneamente TP y SL y reduce vencimiento.
- Fundamento: OI como actividad, no como direccion.
- Problema: escala `50` y peso `0.06` son internos.
- Traza: completa.
- Dictamen: conservar como hipotesis de actividad.

### 8.8 Estado conjunto precio-OI

- ID: `M4-RULE-PRICE-OI-STATE-001`.
- Formula actual:
  `side*sign(D_H)*tanh(50*dOI_H)`.
- Uso: interaccion direccional precio-OI.
- Problema: impone una narrativa de cuadrantes que M4 habia evitado; comparte
  `dOI_H` con la regla anterior y puede duplicar evidencia.
- Traza: completa.
- Dictamen: revisar signo, semantica y control de doble conteo antes de ampliar.

### 8.9 Basis Spot-Futures

- ID: `M4-RULE-SPOT-FUTURES-BASIS-001`.
- Formula base: basis logaritmico sincronizado.
- Senal actual: `-side*tanh(100*b_mid)`.
- Uso: individual contrarian.
- Problema: el signo contrarian, escala `100` y peso `0.06` no se derivan de la
  fuente que define el basis.
- Traza: completa.
- Dictamen: conservar la variable; tratar continuacion y reversion como
  hipotesis alternativas condicionadas.

### 8.10 Prima mark-index

- ID: `M4-RULE-MARK-INDEX-PREMIUM-001`.
- Formula base: `ln(markPrice/indexPrice)`.
- Senal actual: `-side*tanh(200*premium)`.
- Uso: individual contrarian.
- Problema: puede duplicar basis y funding; escala `200` y peso `0.06` internos.
- Traza: completa.
- Dictamen: conservar, pero dentro de una familia comun de dislocacion.

### 8.11 Funding

- ID: `M4-RULE-FUNDING-STATE-001`.
- Dato: ultima tasa observada.
- Senal actual: `-side*tanh(last_rate/0.0005)`.
- Uso: individual contrarian.
- Problema: ultima tasa no equivale a funding futuro ni demuestra reversion;
  `0.0005` y peso `0.08` son internos.
- Traza: completa.
- Dictamen: conservar y ampliar con funding relativo a su historia.

## 9. Defectos transversales actuales

1. **Biblioteca demasiado estrecha**: 11 reglas dejan fuera tendencia EMA,
   RSI, ATR contextual, volumen, niveles, Fibonacci, CVD, order book, breadth,
   sentimiento, crowding y liquidaciones.
2. **Pesos provisionales sin ficha de origen**: ocho reglas usan pesos fijos
   introducidos en v0.4.
3. **Doble conteo potencial**:
   - trayectoria H y regimen usan `SE_H`;
   - OI y precio-OI usan `dOI_H`;
   - basis, premium y funding pertenecen a una familia correlacionada.
4. **Atribucion desigual**: las ocho reglas overlay guardan delta TP/SL; las
   tres familias ajustadas guardan features y coeficientes, pero no un delta
   probabilistico individual equivalente.
5. **Delta overlay dependiente del orden**: el resultado final es equivalente
   a sumar log-efectos, pero el delta secuencial atribuido a cada regla depende
   del orden de aplicacion. No debe interpretarse como efecto causal.
6. **Reglas base omitidas del aprendizaje**: geometria TP/SL, horizonte y
   volatilidad realizada determinan fuertemente la probabilidad base, pero no
   aparecen como reglas activas en el snapshot de aprendizaje.
7. **Interacciones sin registro de familia**: existen IDs para regimen y
   precio-OI, pero no un registro general que distinga efecto individual,
   interaccion y evidencia compartida.
8. **Terminologia excesiva**: la interfaz llama calibrada a una estimacion cuya
   prueba independiente final no esta cerrada para la version activa.

## 10. Contrato de trazabilidad necesario

Cada ejecucion de regla, incluida cada interaccion, debe guardar:

```text
rule_id
rule_version
family_id
role = standalone | interaction | baseline | economic | information
parent_rule_ids
source_ids
input_values
input_units
provider_timestamps
data_cutoff_at
activation_status
non_application_reason
formula_id
formula_branch
raw_output
normalized_signal
coefficient_or_weight
log_effect_tp
log_effect_sl
log_effect_expiry
probabilities_before_family
probabilities_after_family
trace_sha256
engine_version
```

Al cerrar el horizonte, el motor de aprendizaje debe enlazar esa traza con:

```text
outcome = TP_FIRST | SL_FIRST | EXPIRY | AMBIGUOUS | CENSORED
first_touch_at
MFE
MAE
evidence_quality
reconstruction_sha256
```

Para medir aportacion individual deben registrarse tambien:

- prediccion completa;
- prediccion por ablacion de cada regla;
- prediccion por ablacion de cada familia;
- prediccion con y sin cada interaccion.

Asi el aprendizaje no dependera del delta secuencial ni confundira variables
correlacionadas con aportaciones independientes.

## 11. Dictamen

El trabajo previo sirve como inventario, contratos de datos, formulas
deterministas y sistema de trazas. No debe descartarse.

Sin embargo, el estado actual no cumple aun el objetivo de biblioteca amplia:

- las 86 entradas antiguas fueron clasificadas, no sustituidas por una
  biblioteca equivalente;
- las 11 actuales son hipotesis ejecutables y trazables, pero ocho tienen
  signos/escalas/pesos provisionales y varias comparten evidencia;
- la trazabilidad permite reconstruir mucho del calculo, pero no comparar de
  forma uniforme la aportacion marginal de todas las reglas y familias;
- existen al menos 14 familias antiguas recuperables que deben redisenarse e
  incorporarse como hipotesis documentadas.

La siguiente fase correcta no es eliminar las 11 ni restaurar los puntos
antiguos. Es crear el contrato maestro de biblioteca, corregir las
inconsistencias de las 11 actuales y reincorporar por familias las hipotesis
antiguas utiles con formulas continuas, trazas uniformes e interacciones
explicitas.

## 12. Fuentes ya vinculadas

- Binance USD-M y Spot: definicion oficial de datos de mercado.
- Wilder (1978): RSI y ATR originales.
- NIST: suavizado exponencial.
- Moskowitz, Ooi y Pedersen (2012): momentum temporal en futuros.
- Hudson y Urquhart (2021): limites fuera de muestra de reglas tecnicas crypto.
- Osler (2000): niveles de soporte/resistencia en FX intradia.
- Cont, Kukanov y Stoikov (2014): order flow imbalance y precio.
- Corsi (2009): heterogeneidad/persistencia de volatilidad.
- Hong y Yogo (2012): actividad de mercados de futuros y retornos.
- Baur y Dimpfl (2019), Frino et al. (2025): relacion spot-futuros.
- He, Manela, Ross y von Wachter (2022): perpetuos y funding.
- Tsinaslanidis, Guijarro y Voukelatos (2022): prueba empirica de Fibonacci.
- Brier (1950) y Gneiting-Raftery (2007): evaluacion probabilistica.

La matriz detallada de limites de transferencia permanece en
`matriz_fuentes_y_teorias.md`. Ninguna fuente anterior acredita por si sola
los pesos numericos actuales.
