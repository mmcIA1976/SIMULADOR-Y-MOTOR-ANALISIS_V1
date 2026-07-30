# Noveno bloque: economia de ejecucion

Fecha: 2026-07-30
Estado: IMPLEMENTADO; ACTIVO; NO PREDICTIVO

## 1. Resultado de la comparacion

Las fichas candidatas:

```text
LIB-CAND-SPREAD-EXECUTION-001
LIB-CAND-DEPTH-COVERAGE-001
```

duplicaban dos reglas ya ejecutadas por el motor:

```text
M4-RULE-QUOTED-SPREAD-001
M4-RULE-DEPTH-SWEEP-001
```

Las candidatas se eliminan del registro de identidades. Las reglas M4 quedan
como unicas fichas canonicas y conservan en el catalogo los identificadores
que sustituyen.

## 2. Spread cotizado

Formulas:

```text
mid = (best_bid+best_ask)/2
spread_quote = best_ask-best_bid
spread_fraction_mid = spread_quote/mid
```

La captura tambien verifica:

```text
age_ms = capture_time-receive_time
valid = 0<=age_ms<=30000
```

El limite de 30000 ms procede del contrato interno para datos de mercado en
tiempo real. Un libro cruzado, futuro o caducado bloquea la medicion.

## 3. Barrido de profundidad

La regla utiliza el midpoint producido por la regla de spread y consume:

- asks ascendentes para una compra;
- bids descendentes para una venta.

Formulas:

```text
filled_qty = sum(min(remaining_qty,level_qty))
fill_ratio = filled_qty/requested_qty
VWAP_filled = sum(price_i*filled_qty_i)/filled_qty
D = +1 buy; -1 sell
IS_filled_quote =
    D*(sum(price_i*filled_qty_i)-arrival_mid*filled_qty)
IS_filled_fraction =
    IS_filled_quote/(arrival_mid*filled_qty)
complete_VWAP = VWAP_filled iff fill_ratio=1
```

Si `fill_ratio<1`, la observacion sigue siendo valida y conserva:

```text
availability_status = insufficient_visible_depth
complete_vwap = null
```

No se extrapola el coste de la cantidad no visible. La viabilidad de entrada
queda bloqueada, pero las probabilidades de mercado siguen disponibles.

## 4. Doble conteo

El implementation shortfall medido desde midpoint ya incorpora:

- medio spread;
- coste del barrido visible.

Por tanto, el spread no puede sumarse otra vez al shortfall.

## 5. Salida auditable

El snapshot del analisis incorpora:

```text
execution_economics.quoted_spread
execution_economics.entry_depth_sweep
execution_economics.probability_effect =
    none_separate_economic_layer
```

El aprendizaje puede conservar estas condiciones como contexto economico,
pero no tratarlas como reglas direccionales ni modificar produccion.

## 6. Invariante principal

Una prueba integrada ejecuta el mismo plan con profundidad completa y con
profundidad insuficiente. El segundo caso:

- conserva exactamente las mismas probabilidades TP, SL y expiracion;
- registra el fill parcial;
- no inventa un VWAP completo;
- bloquea solo `entry_execution`.
