# Septima familia: reglas compuestas en observacion

Fecha: 2026-07-30
Estado: IMPLEMENTADA EN SOMBRA; SIN EFECTO PROBABILISTICO

## 1. Alcance

Se implementan tres interacciones ya incluidas en el catalogo maestro:

1. compresion de volatilidad y volumen;
2. absorcion flujo-volumen-precio;
3. contexto de pullback.

No se crea una puntuacion compuesta, una clasificacion discreta ni un ajuste
manual. Cada regla conserva un vector reproducible para que el aprendizaje
pueda medir posteriormente sus componentes, sus combinaciones y su valor
incremental.

## 2. Condiciones comunes

Una regla compuesta solo se evalua cuando todas sus reglas padre:

- pertenecen al mismo analisis pre-trade;
- tienen estado `evaluated` o `evaluated_shadow`;
- exponen sus salidas estructuradas;
- conservan su `trace_sha256`.

La traza compuesta registra los hashes de todos sus padres. Si falta uno, la
regla queda `blocked` con `parent_rule_unavailable`; no se completa el dato
mediante inferencias.

## 3. Compresion

Identificador:

```text
LIB-CAND-COMPRESSION-001
```

Padres:

```text
M4-RULE-VOLATILITY-RANK-001
LIB-CAND-RELATIVE-VOLUME-001
```

Formulas:

```text
ATRNorm_t = ATR14_t/close_t
atr_rank_60 = midrank(ATRNorm_t, previous_60_horizon_endpoints)
bb_width_20_2sigma = 4*population_std(close_20)/SMA20
bb_width_midrank_60 = midrank(
    bb_width_current,
    previous_60_horizon_endpoints
)
compression_vector = (
    atr_rank_60,
    bb_width_midrank_60,
    relative_volume_H,
    volume_midrank_60
)
```

Los 61 puntos son finales exactos de horizontes no solapados. No se fija un
umbral para declarar que existe compresion: se conserva el vector continuo.

## 4. Absorcion

Identificador:

```text
LIB-CAND-ABSORPTION-001
```

Padres:

```text
M4-RULE-AGGRESSOR-IMBALANCE-001
LIB-CAND-RELATIVE-VOLUME-001
```

Formulas:

```text
upper_wick = max(H_H-max(O_H,C_H),0)/(H_H-L_H)
lower_wick = max(min(O_H,C_H)-L_H,0)/(H_H-L_H)
displacement_atr = log(C_H/O_H)/(ATR14/C_H)
flow_opposing_wick =
    upper_wick if ATI_H > 0
    lower_wick if ATI_H < 0
    null if ATI_H = 0
absorption_vector = (
    ATI_H,
    relative_volume_H,
    displacement_atr,
    flow_opposing_wick
)
```

El OHLC se agrega sobre la ventana exacta del horizonte. El vector describe
flujo, participacion, desplazamiento y rechazo contrario al flujo, pero no
afirma por si mismo que haya absorcion.

## 5. Contexto de pullback

Identificador:

```text
LIB-CAND-PULLBACK-CONTEXT-001
```

Padres:

```text
LIB-CAND-EMA-TREND-001
LIB-CAND-ATR-EXTENSION-001
LIB-CAND-RELATIVE-VOLUME-001
M4-RULE-AGGRESSOR-IMBALANCE-001
LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001
```

Vector:

```text
pullback_vector = (
    side_adjusted_ema50_vs_ema200_log,
    side_adjusted_ema50_slope_6bars_atr,
    side_adjusted_extension_atr,
    relative_volume_H,
    volume_midrank_60,
    side_adjusted_ATI_H,
    target_path_level_count,
    adverse_path_level_count
)
```

Los niveles estructurales cercanos se conservan adicionalmente en la salida.
No se aplica una definicion discreta de pullback ni se fuerza una conclusion
alcista o bajista.

## 6. Regla no implementada

`LIB-CAND-SHOCK-001` permanece bloqueada. Requiere:

- historia sincronizada del spread;
- historia fiable de liquidaciones realizadas.

Las posiciones publicas agregadas para el mapa de Hyperliquid son una
estimacion de exposicion potencial, no liquidaciones realizadas. Sustituir un
dato por el otro falsearia la formula de shock.

## 7. Efecto y aprendizaje

Las tres trazas declaran:

```text
status = evaluated_shadow
probability_effect = none_shadow_observation
```

El cierre de una operacion puede enlazar el vector y los hashes de sus padres
con TP, SL o expiracion. El aprendizaje no modifica produccion
automaticamente; cualquier efecto futuro exige evaluacion retrospectiva,
validacion temporal y aprobacion del propietario.
