# M4.7 - Evaluacion de la revision externa B

Fecha: 2026-07-27

Estado: DICTAMEN DE CONTRASTE; NO MODIFICA LAS FICHAS M4

Regla de aislamiento:

- este documento evalua exclusivamente la revision B;
- no incorpora ni compara recomendaciones de la revision A;
- ninguna recomendacion B queda aprobada por estar incluida aqui;
- el catalogo M4.7, sus formulas y produccion permanecen sin cambios;
- M4 continua abierta y M5 no se inicia.

Documento evaluado:

- ruta:
  `C:\Users\MSI\.codex\attachments\19f1565d-efda-4fbf-ae2a-6e7b6120b5bc\pasted-text.txt`;
- tamano: `14724` bytes;
- SHA-256:
  `8B324029ED93ABF224ABE563DB76B2909005CA74C801BB8E80223D344B254945`.

Version contrastada:

- informe humano:
  `auditorias_motor/2026-07-27_M4_7_27_reglas_formulas_auditoria.md`;
- SHA-256 real del archivo Markdown:
  `88E1FADFA06C52FFFD09D670CE06AAC056DD4542186D5562FABA47249FBA2C1E`;
- catalogo JSON:
  `auditorias_motor/catalogo_27_reglas_formulas_m4_7_v0_1.json`;
- SHA-256 real del archivo JSON:
  `A32B114E06076C42E1387EB5DECA1EE10ABA944B74C6F1098085E38AF83520DA`;
- digest canonico declarado dentro del catalogo:
  `474758f48c96a9b923332d94e10e70b91b4568b9d5ee6b05cfd32465d3092e53`.

## 1. Dictamen general

La revision B es tecnicamente valiosa y descubre carencias reales que deben
resolverse antes de dar por cerrado M4. Sus aportaciones mas importantes son:

1. corregir la formula publicada del VWAP cuando existe fill parcial;
2. formalizar el recorrido completo desde trigger hasta fill y resultados;
3. convertir el contrato general de first passage de M2 en una ficha operable;
4. modelar la factibilidad de liquidacion antes del SL;
5. definir el payoff de expiry como esperanza o distribucion condicional;
6. separar calidad y procedencia de valores observados, deterministas,
   estimados y escenarios;
7. aclarar el alcance exacto del digest SHA-256.

La revision tambien contiene afirmaciones que necesitan matiz:

- la regla 8 no produce una division por cero en el operador de referencia; el
  defecto esta en la formula publicada;
- M2 ya fijo que el reloj no se reinicia al ejecutarse una entrada pendiente;
- M2 ya exige ambiguedad cuando no puede ordenarse TP y SL;
- M4.5 ya bloquea el riesgo de cuenta cuando faltan datos de liquidacion;
- la identidad matematica del EV es exacta condicionada a sus entradas, aunque
  el EV pre-trade resultante sea una estimacion;
- `INDEX_PRICE` no es un `workingType` de las ordenes condicionales USD-M;
- `triggerProtect` es metadato del simbolo, no una eleccion del usuario;
- un WebSocket Spot `bookTicker` no aporta por si solo tiempo de evento de
  mercado, por lo que no elimina automaticamente la incertidumbre temporal.

Por ello, B no debe aplicarse literalmente. Si debe utilizarse como base para
una enmienda M4 versionada y sometida a decision expresa del propietario.

## 2. Siete observaciones principales

| Punto B | Dictamen independiente | Alcance real |
|---|---|---|
| B1. Regla 8 y `TV_W=0` | ACEPTAR COMO CORRECCION OBLIGATORIA DE LA FICHA | La formula publicada deja `E_W=0/0`. El operador ya evita el error y devuelve `E_W=0`, `SE_W=0` y `flat_observed_path`. No es un fallo numerico activo del operador. |
| B2. Regla 21 y VWAP | ACEPTAR COMO CORRECCION OBLIGATORIA | La formula general de la ficha divide por cantidad solicitada y es incorrecta para fills parciales. El operador calcula `partial_vwap=quote_value/filled` correctamente. La ficha, trazas y pruebas deben distinguir coste del tramo ejecutado y coste completo de la orden. |
| B3. Trigger frente a fill | ACEPTAR EL HUECO; RECHAZAR QUE EL RELOJ SIGA INDEFINIDO | M2 ya prohibe conflar touch, trigger y fill, pero M4 no contiene aun el contrato de estados de ejecucion. M2 ya fijo `expiry_at=analysis_at+H`, sin reinicio. |
| B4. Proceso de precio y first passage | ACEPTAR CON CORRECCIONES | M2 ya exige `price_reference` y ambiguedad no forzada. Falta materializarlo en M3/M4 y existe una divergencia en produccion. `workingType` admite `MARK_PRICE` o `CONTRACT_PRICE`, no `INDEX_PRICE`. |
| B5. Liquidacion antes del SL | ACEPTAR COMO NUEVA PUERTA DE FACTIBILIDAD | M4.5 ya declara el dato ausente y `account_risk_available=false`, pero no existe formula de factibilidad ni outcome de liquidacion. No debe bloquear la probabilidad fisica TP/SL; si debe bloquear payoff apalancado o una decision operable cuando pueda alterar las ramas. |
| B6. Payoff de expiry y EV | ACEPTAR CON MATIZ | El payoff de expiry no es determinista pre-trade. La identidad `EV=sum(p_k*y_k)` sigue siendo exacta como identidad; sus probabilidades y payoffs futuros son estimados, distribuidos o escenarios. |
| B7. SHA-256 | ACEPTAR COMO DEFECTO DE METADATO, NO DE INTEGRIDAD | El valor declarado es un digest de un subconjunto JSON canonico, no el hash de los archivos. El rotulo `SHA-256` es ambiguo. Deben declararse algoritmo, alcance, serializacion y hashes de archivo en un manifiesto externo. |

### B1. Trayectoria plana

Formula formal requerida:

```text
D_W = sum(r_i)
TV_W = sum(abs(r_i))

if TV_W > 0:
    E_W = abs(D_W) / TV_W
    SE_W = D_W / TV_W
    flat_path = false
else:
    E_W = 0
    SE_W = 0
    flat_path = true
```

Evidencia local:

- `build_m4_structure_regime.py:path_structure` ya implementa la rama plana;
- `tests/test_m4_structure_regime.py` ya prueba la trayectoria constante;
- falta hacer explicita la rama para `E_W` en la ficha consolidada.

### B2. VWAP y fill parcial

Formula formal requerida:

```text
Q_req = requested_quantity
Q_fill = sum(q_i)
Q_unfilled = Q_req - Q_fill
fill_ratio = Q_fill / Q_req

VWAP_filled =
    sum(p_i*q_i) / Q_fill     if Q_fill > 0
    unavailable               if Q_fill = 0

D = +1 buy; -1 sell
IS_filled_quote = D * (sum(p_i*q_i) - arrival_mid*Q_fill)
IS_filled_fraction = IS_filled_quote / (arrival_mid*Q_fill)
```

Condiciones:

- `full_order_execution_cost` solo esta disponible si `fill_ratio=1`;
- con `0<fill_ratio<1` solo esta disponible el coste del tramo ejecutado;
- ese coste parcial no es el implementation shortfall completo de la orden,
  porque no incluye el coste de oportunidad de la cantidad no ejecutada;
- con `Q_fill=0`, VWAP e IS del tramo ejecutado no estan disponibles.

Evidencia local:

- `build_m4_execution_risk.py:depth_sweep` calcula correctamente
  `partial_vwap=quote_value/filled`;
- el mismo operador oculta el shortfall cuando el fill no es completo;
- la formula de la ficha usa incorrectamente `requested_qty` como denominador.

### B3. Estados de ejecucion y reloj

M2 ya contiene:

- `M2-INV-ACTIVATION-01`: entrada y no entrada son eventos separados;
- `M2-INV-CLOCK-01`: el reloj nunca se reinicia;
- `execution_boundary`: touch, trigger y fill no pueden conflarse;
- `remaining_horizon=expiry_at-entry_at`.

El hueco real esta entre ese contrato y las fichas M4:

- la regla 6 solo calcula distancia a un trigger;
- deriva `limit_pullback`, `stop_breakout` o `stop_breakdown` a partir de lado y
  condicion, sin recibir el tipo exacto de orden;
- no representa estados terminales de fill;
- no trata fills parciales en distintos instantes.

El arbol propuesto por B es una buena base, pero debe precisarse. Los estados
terminales deben ser mutuamente excluyentes a `expiry_at`, por ejemplo:

```text
no_trigger
triggered_unfilled_at_expiry
partial_fill_at_expiry
full_fill
cancelled_or_rejected
```

Una orden que primero se llena parcialmente y despues completamente no puede
contarse en ambas ramas. Para fills multiples, la exposicion y el horizonte
restante dependen de cada tiempo y cantidad ejecutados.

La integracion sobre el tiempo de entrada/fill es conceptualmente correcta y
corresponde a M6. La alternativa de reiniciar H contradice el contrato M2 y no
se considera abierta.

### B4. Precio de activacion y first passage

La observacion es importante, pero parte del problema ya estaba resuelto:

- M2 exige `price_reference` en la traza;
- `M2-INV-AMBIGUITY-01` prohibe forzar un resultado ambiguo;
- las pruebas de evidencia historica conservan `ambiguous_same_candle`;
- `aggTrades` puede ordenar eventos recientes cuando esta disponible.

Carencias vigentes:

- M3-DATA-001 no recibe tipo exacto de orden ni referencia de trigger;
- ninguna de las 27 fichas formaliza el etiquetado first-passage;
- las velas de contrato no bastan para reconstruir triggers basados en mark;
- produccion usa precio/velas/`aggTrades` de contrato como referencia implicita.

Divergencia detectada en produccion:

- `app.py:triggered_exit_from_market_path` intenta resolver con `aggTrades`;
- si no hay trades y una vela de 1 minuto contiene TP y SL, cae en
  `triggered_exit_reason_from_range`;
- esa funcion fuerza `stop_loss` cuando ambas barreras aparecen en la vela;
- este fallback contradice el contrato M2 de ambiguedad no forzada.

La futura ficha debe distinguir:

```text
entry_order_type
entry_trigger_price_type
tp_order_type
tp_trigger_price_type
sl_order_type
sl_trigger_price_type
price_protect
symbol_trigger_protect
label_price_process
```

Correcciones a la propuesta B:

- Binance USD-M documenta `MARK_PRICE` y `CONTRACT_PRICE` como `workingType`;
- `INDEX_PRICE` puede ser una referencia analitica separada, pero no debe
  presentarse como `workingType` de una orden condicional USD-M;
- `priceProtect` pertenece a la orden;
- `triggerProtect` pertenece a `exchangeInfo` del simbolo.

Politica first-passage minima:

1. usar el proceso de precio declarado;
2. usar datos ordenados de resolucion suficiente;
3. si no puede determinarse el orden, etiquetar `ambiguous`;
4. conservar el caso y medir su frecuencia;
5. excluirlo de una etiqueta supervisada que exija TP o SL inequivoco;
6. nunca asignar TP o SL por una prioridad arbitraria.

### B5. Liquidacion

M4.5 no oculta la ausencia:

- `liquidation_price_available=false`;
- `account_risk_available=false`;
- `account_liquidation_inputs=account_risk_blocked`;
- la ficha 24 declara que no incluye equity, margin mode ni maintenance
  brackets.

El defecto real es que el bloqueo no se ha convertido en una regla de
factibilidad ni se ha conectado al arbol de outcomes.

Contrato minimo candidato:

```text
liquidation_feasibility =
    before_stop
    after_or_equal_stop
    not_applicable
    unknown
```

Consecuencias:

- `before_stop`: el plan apalancado no admite el payoff SL declarado;
- `unknown`: el motor puede conservar probabilidades fisicas de barrera, pero
  no puede declarar completo el payoff apalancado ni autorizar la operacion;
- `after_or_equal_stop`: no prueba que el SL vaya a ejecutarse, solo que la
  liquidacion modelada no invalida primero esa barrera;
- `not_applicable`: solo para una rama sin posicion apalancada.

Debe distinguirse:

- escenario aislado hipotetico, calculable con datos del plan y brackets;
- posicion real aislada, contrastable con datos autenticados;
- margen cruzado o multi-activo, dependiente del estado completo de cuenta;
- simulador sin cuenta conectada, que debe declarar escenario o desconocido.

La liquidacion debe ser primero una puerta de factibilidad. Solo entra como
outcome competidor cuando el contrato de la operacion permite que ocurra antes
de la salida protectora.

### B6. Expiry, calidad y EV

TP y SL tienen niveles de plan. Expiry no tiene un precio terminal conocido en
`analysis_at`. Por tanto, se necesita:

```text
E[Y_expiry | entry/fill history, no terminal barrier before expiry]
```

o una distribucion condicional equivalente. No debe introducirse un precio de
expiry fijo sin una regla y un modelo identificados.

La ficha de EV debe separar:

- identidad matematica exacta;
- probabilidades estimadas por el modelo;
- payoff determinista derivado del plan;
- coste observado;
- coste futuro estimado o acotado;
- payoff de expiry estimado;
- resultado realizado posterior.

Estados candidatos de procedencia/calidad:

```text
observed_exact
deterministic_from_plan
estimated_model
scenario_point
scenario_lower_bound
scenario_upper_bound
unavailable
not_applicable
```

No se acepta llamar `exacto` al EV pre-trade completo. Si puede llamarse
exacta a la operacion algebraica aplicada a un conjunto concreto de entradas,
dejando visible la calidad de cada entrada.

### B7. Convencion SHA-256

El codigo calcula `catalog_sha256` sobre JSON canonico de:

```text
reading_contract
formula_index
rules
source_registries
```

con:

```text
UTF-8
ensure_ascii=true
keys ordenadas
separadores compactos
```

Ese digest es reproducible, pero el informe humano lo rotula solo como
`SHA-256`. No es el hash del Markdown ni del JSON completo.

Enmienda candidata:

- renombrar el campo a `canonical_payload_sha256`;
- publicar `canonicalization_contract`;
- publicar aparte `markdown_file_sha256` y `json_file_sha256`;
- colocar los hashes de archivo en un manifiesto externo para evitar
  autorreferencia;
- probar la reproduccion de cada digest.

## 3. Observaciones adicionales

| Regla/tema | Dictamen independiente | Accion candidata |
|---|---|---|
| Regla 1, intervalo | ACEPTAR COMO POLITICA PROVISIONAL NO JUSTIFICADA EMPIRICAMENTE | No sustituirla ahora por una tabla par/horizonte elegida sin evidencia. Registrar la decision y comparar resoluciones con protocolo previo en M7/M8. |
| Regla 5, nombre | ACEPTAR | `NORMALIZED-BARRIER-GEOMETRY` describe mejor la salida. Cambiar ID solo mediante versionado y mapa de migracion. |
| Regla 7, P0 | ACEPTAR | El suavizador esta excluido por su propia ficha. Presentar `26 fichas P0 + 1 operador auxiliar`, o sacarlo del conteo nuclear. |
| Regla 11, signo MTF | YA RESUELTO EN LA INTEGRACION | M4.6 conserva el vector continuo y no autoriza el descriptor como score. Conviene marcar el descriptor de signos como diagnostico inestable y no predictivo. |
| Regla 13, identidad ATI | ACEPTAR PARCIALMENTE | Las fuentes ya permanecen separadas y no se combinan. Falta una traza comun con fuente, unidad, cobertura y metodo. La retencion limitada y la necesidad de archivo ya estaban documentadas en M3. |
| Regla 14, OI exacto | ACEPTAR | La ficha exige separacion exacta H, pero el operador numerico no recibe timestamps y las pruebas no demuestran alineacion. Anadir separacion real y error; no interpolar silenciosamente. |
| Regla 16, sincronizacion | ACEPTAR EL PROBLEMA; NO ACEPTAR UNA SOLUCION SIN MEDIR | `<=2000 ms` es captura acotada por tiempos de recepcion, no sincronizacion real. WebSocket reduce latencia, pero Spot `bookTicker` no incluye tiempo de evento. El umbral y el filtro de incertidumbre requieren formula y justificacion previa. |
| Regla 17, proveedor | ACEPTAR COMO CORRECCION DE METADATO | Mark e index proceden de Binance USD-M. El proveedor generico compartido por las siete fichas M4.4 es incorrecto para esta regla. |
| Regla 18, nombre | ACEPTAR | `linearized_last_funding_rate_per_hour` evita presentarlo como tasa compuesta o forecast. |
| Regla 22, fee exacta | ACEPTAR CON SEPARACION PRE/POST-TRADE | Antes de ejecutar es escenario aun con rol conocido. Despues requiere notional ejecutado, tasa autenticada, rol y activo/importe de comision. |
| Clasificacion de fuentes | ACEPTAR | Separar semantica de proveedor, definicion matematica, evidencia empirica directa, evidencia adyacente e contrato interno. |

### Regla 1

La revision acierta en que `24` y `max(I)` no son optimos publicados. La ficha
ya lo reconoce como politica del proyecto. No se considera correcto reemplazar
ahora una politica comun por `preregistered_interval(pair,horizon)` sin definir
el criterio y sin proteger el conjunto de prueba.

La lista actual solo usa intervalos de segundos fijos entre `1m` y `1d`; no
incluye `1M`. La advertencia sobre meses variables es correcta en general, pero
no detecta un intervalo variable presente en la implementacion actual.

### Regla 11

La funcion produce un descriptor exacto de signos, que puede cambiar cerca de
cero. Sin embargo:

- no asigna puntos, pesos ni probabilidades;
- M4.6 conserva `SE_H`, `SE_2H` y `SE_4H` como entradas canonicas;
- el descriptor no es una entrada canonica independiente.

No existe aqui un efecto predictivo oculto. Si existe una necesidad de
legibilidad: declararlo diagnostico no robusto y prohibir su promocion.

### Regla 13

Ya estan separados:

- ATI por operaciones ejecutadas;
- ATI periodico por volumen taker;
- sus valores originales;
- su diferencia y consistencia;
- `combined_value=null`.

Se acepta anadir:

```text
ati_source
activity_unit
coverage_start
coverage_end
aggregation_method
source_retention_status
```

Binance documenta una retencion de 30 dias para taker buy/sell y un mes para
OI historico. M3 ya registra ambos limites y la ausencia de archivo local.

### Regla 14

La ficha declara:

- `exact endpoint separation H`;
- timestamps anterior y actual en la traza.

El operador `open_interest_change(previous,current)` no puede verificarlo. La
enmienda debe hacer cumplir:

```text
actual_separation_seconds =
    timestamp_current - timestamp_previous

alignment_error_seconds =
    actual_separation_seconds - H
```

La disponibilidad debe exigir separacion exacta o una tolerancia previamente
decidida conforme a la malla del proveedor. No debe inventarse una tolerancia
despues de observar resultados ni interpolarse OI silenciosamente.

### Regla 16

El estado correcto hoy es:

```text
receive_time_bounded_cross_venue_capture
```

No:

```text
synchronized_market_timestamp_capture
```

El limite de 2000 ms esta implementado y probado, pero no esta justificado como
umbral adecuado para price discovery. Debe registrarse la incertidumbre de
captura y evaluarse un procedimiento mas estricto. La recomendacion WebSocket
es candidata de arquitectura, no una correccion suficiente por si sola.

### Regla 22

Hay que distinguir:

```text
pretrade_fee_scenario =
    assumed_notional * authenticated_rate(assumed_role)

realized_fee =
    observed_commission_amount in observed_commission_asset
```

El rol conocido no convierte por si solo una fee futura en observada ni exacta.
La API de operaciones realizadas expone precio, cantidad, `quoteQty`,
`commission`, `commissionAsset` y rol maker, que son los campos adecuados para
la evaluacion posterior.

## 4. Cuatro fichas nuevas propuestas por B

### `M4-RULE-FIRST-PASSAGE-LABEL-001`

Dictamen: NECESARIA.

Materializa una obligacion ya aprobada en M2. Debe definir proceso de precio,
resolucion, orden temporal, ambiguedad, censura y trazas. Tambien debe provocar
la eliminacion del fallback productivo que fuerza SL en una vela ambigua.

### `M4-RULE-ORDER-FILL-STATE-001`

Dictamen: NECESARIA.

Completa el hueco entre la distancia de activacion y una entrada ejecutada.
Requiere antes una decision de producto sobre tipos de orden admitidos y los
campos exactos del plan.

### `M4-RULE-LIQUIDATION-FEASIBILITY-001`

Dictamen: NECESARIA PARA PAYOFF Y DECISION APALANCADA.

Debe separar escenario aislado, posicion real aislada y riesgo de cuenta
cruzada. No debe convertir apalancamiento o liquidacion en probabilidad
direccional de mercado.

### `M4-RULE-EXPIRY-PAYOFF-001`

Dictamen: NECESARIA.

Debe definir el objeto que M6 estimara para la rama expiry y prohibir un payoff
puntual arbitrario. No debe fingir que el precio terminal futuro es conocido.

Estas cuatro fichas son candidatas de enmienda. No se anaden mediante este
dictamen y todavia no se decide si amplian el catalogo a 31 fichas o si alguna
reemplaza una ficha actual.

## 5. Evaluacion de fuentes

La critica de B es valida. El catalogo ya registra `supported_claim` y
`does_not_support`, pero el encabezado comun puede hacer que una fuente
adyacente parezca validacion directa.

Clasificacion candidata:

```text
provider_semantics
mathematical_definition
direct_empirical_evidence
family_or_adjacent_evidence
internal_project_contract
```

Consecuencias:

- una documentacion de Binance define campos y comportamiento del proveedor;
- una identidad matematica define un operador, no su poder predictivo;
- una evidencia empirica en otro activo u horizonte justifica investigar, no
  transferir automaticamente;
- una fuente adyacente no autoriza signo, umbral, peso o probabilidad;
- solo M7/M8 podran probar estabilidad para los seis pares y tres perfiles.

## 6. Evidencia oficial de proveedor contrastada

Documentacion oficial consultada:

- ordenes USD-M, `workingType`, `priceProtect`, fills y datos de orden:
  https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order
- estados de orden y `workingType`:
  https://developers.binance.com/zh-CN/docs/products/derivatives-trading-usds-futures/common-definition
- posicion USD-M V3, `liquidationPrice`, margen y maintenance margin:
  https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3
- cuenta USD-M V3, balance y maintenance margin agregado:
  https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3
- OI historico, retencion de un mes:
  https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics
- taker buy/sell, retencion de 30 dias:
  https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume
- Spot WebSocket `bookTicker`, sin tiempo de evento en su payload:
  https://developers.binance.com/zh-CN/docs/products/spot/testnet/web-socket-streams

## 7. Enmiendas candidatas acumuladas de B

No aplicar hasta una decision posterior del propietario:

1. completar la rama plana de la formula de estructura;
2. corregir VWAP y coste del fill parcial;
3. crear el contrato terminal de trigger/fill;
4. mantener el vencimiento absoluto ya aprobado en M2;
5. crear la ficha first-passage y ampliar los campos del plan;
6. corregir el fallback productivo de doble toque solo en su fase autorizada;
7. crear la puerta de factibilidad de liquidacion;
8. crear la ficha de payoff condicional de expiry;
9. ampliar la taxonomia de procedencia y calidad;
10. documentar los hashes canonicos y de archivo;
11. registrar la politica de muestreo y su futura sensibilidad;
12. renombrar la geometria de barreras;
13. separar el suavizador exponencial del conteo P0;
14. ampliar trazas ATI y OI;
15. reclasificar la captura cross-venue y medir su incertidumbre;
16. corregir proveedor de mark-index;
17. renombrar la normalizacion lineal de funding;
18. separar fee pre-trade de comision realizada;
19. clasificar las fuentes por fuerza y relacion con la regla.

## 8. Conclusion independiente

La revision B merece ser considerada. Detecta dos errores formales locales
claros, varias carencias de contrato global y una divergencia productiva
importante. No demuestra que los 27 operadores sean inutiles ni que todo M4
deba rehacerse. Demuestra que el catalogo todavia no cubre de extremo a extremo
la semantica de una operacion ejecutable.

No se recomienda cerrar M4 en su estado actual. El siguiente paso, despues de
mantener A y B separadas, sera decidir expresamente que observaciones se
convierten en enmiendas M4 y en que orden se ejecutan.

## 9. Estado

- Revision B evaluada: SI.
- Revision A mezclada o comparada: NO.
- Recomendaciones B aplicadas: NO.
- Catalogo de 27 reglas modificado: NO.
- Produccion modificada: NO.
- Motor de aprendizaje utilizado: NO.
- M4 cerrada: NO.
- M5 iniciada: NO.
