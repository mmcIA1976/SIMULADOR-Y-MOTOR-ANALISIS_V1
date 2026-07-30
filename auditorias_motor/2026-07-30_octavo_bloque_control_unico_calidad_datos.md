# Octavo bloque: control unico de calidad de datos

Fecha: 2026-07-30
Estado: IMPLEMENTADO; BLOQUEANTE; NO PREDICTIVO

## 1. Objetivo

Consolidar los controles ya existentes sobre la historia de velas compartida
por el motor. Cada analisis ejecuta una unica validacion antes de calcular
reglas y conserva dos trazas del mismo informe:

1. frescura de la ultima vela cerrada;
2. integridad de toda la rejilla temporal seleccionada.

No se descargan datos de nuevo y ninguna regla posterior repite estos
controles en el flujo normal.

## 2. Punto unico

La validacion se ejecuta durante el ensamblado pre-trade:

```text
API -> normalizacion -> control unico -> conjunto validado -> reglas
```

El informe declara:

```text
validation_pass_count = 1
status = valid | blocked
source_data_sha256 = hash del conjunto exacto validado
report_sha256 = hash del informe y sus dos trazas
```

La regla de retornos recibe `report_sha256` y reutiliza la autorizacion. Solo
mantiene su antigua comprobacion defensiva cuando se invoca aisladamente sin
un informe prevalidado.

## 3. Frescura

Identificador:

```text
LIB-CAND-DATA-FRESHNESS-001
```

Formulas:

```text
age_ms = analysis_at-latest_closed_candle_timestamp
freshness_limit_ms = selected_interval_ms+60000
fresh = 0 <= age_ms <= freshness_limit_ms
```

Los 60000 ms son la gracia de publicacion definida en el contrato interno de
datos. No son una senal de mercado. Si la ultima vela cerrada supera el
limite, el analisis queda bloqueado como `pretrade_candles_stale`.

## 4. Integridad

Identificador:

```text
LIB-CAND-CANDLE-INTEGRITY-001
```

Se comprueba en la misma pasada:

- numero exacto de velas requerido;
- ausencia de timestamps duplicados;
- orden temporal estricto;
- separacion exacta segun el intervalo elegido;
- duracion exacta de cada vela;
- precios finitos y positivos;
- volumen finito y no negativo;
- `high >= max(open,close)`;
- `low <= min(open,close)`.

Salidas principales:

```text
missing_count
duplicate_count
duplicate_open_count
out_of_order_count
gap_count
invalid_value_count
invalid_ohlc_count
invalid_duration_count
integrity_valid
```

Historia insuficiente conserva el codigo existente
`insufficient_pretrade_history`. El resto de fallos de integridad utiliza
`pretrade_candle_integrity_failed`.

## 5. Efecto

Las dos fichas son gates deterministas activos:

```text
lifecycle_status = active_blocking
probability_effect = none_data_quality_gate
```

Un resultado valido no suma puntos ni modifica TP, SL o expiracion. Un
resultado invalido impide que el motor calcule probabilidades con datos
defectuosos.

## 6. Alcance de otras fuentes

Este control comun corresponde a las velas, porque son reutilizadas por
muchas reglas. Las fuentes con contratos diferentes, como funding,
posicionamiento, sentimiento o liquidaciones, conservan su validacion en el
primer y unico runtime que interpreta su semantica. No se les aplica de nuevo
el gate de velas.
