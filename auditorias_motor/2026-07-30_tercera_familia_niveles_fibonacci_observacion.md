# Tercera familia implementada: niveles y Fibonacci

Fecha: 2026-07-30
Estado: IMPLEMENTADA EN OBSERVACION; SIN EFECTO PROBABILISTICO

## 1. Reglas

```text
LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001
LIB-CAND-FIBONACCI-DISTANCE-001
```

Ambas se calculan antes de la operacion, se trazan y se enlazan posteriormente
con TP primero, SL primero o expiracion/censura. No modifican todavia las
probabilidades.

## 2. Auditoria del motor antiguo

No se ha reutilizado el detector anterior:

- soporte y resistencia se obtenian promediando maximos o minimos cercanos;
- no se exigia que fueran pivotes confirmados;
- Fibonacci aplicaba puntos como `+10`, `-14`, `+14`, `-12`;
- tambien aplicaba ajustes manuales de probabilidad como `-0.01` o `-0.02`;
- esos valores no procedian de una estimacion probabilistica validada.

Se conservan los datos historicos, no esas decisiones.

## 3. Niveles estructurales

Contexto:

```text
cuatro horizontes H anteriores
pivot_half_window = 3 velas
solo velas cerradas antes de analysis_at
```

Pivotes:

```text
pivot_high_i = maximo unico de high[i-3:i+4]
pivot_low_i = minimo unico de low[i-3:i+4]
confirmed_at = i + 3
```

Prominencia continua:

```text
prominence_atr = min(excursion_izquierda, excursion_derecha) / ATR14
```

Distancia:

```text
distance_sigma = log(level_price / entry) / sigma_h
```

Se registran soporte y resistencia mas cercanos, niveles situados entre entrada
y TP, niveles entre entrada y SL, cantidades y prominencias. No existe umbral
que convierta un nivel en bueno o malo.

## 4. Fibonacci

El swing se define como los dos ultimos pivotes opuestos de la serie alternada
de pivotes confirmados. Los pivotes consecutivos del mismo tipo se colapsan
conservando el mas extremo.

Formulas:

```text
retracement_r = start + direction * (1-r) * abs(end-start)
extension_r = start + direction * r * abs(end-start)
```

Ratios registrados:

```text
retracements = 0.236, 0.382, 0.5, 0.618, 0.786
extensions = 1.0, 1.272, 1.618
```

Para entrada, TP y SL:

```text
distance_sigma = abs(log(fib_level / plan_price)) / sigma_h
```

Confluencia con pivotes:

```text
confluence_sigma = abs(log(pivot_price / fib_level)) / sigma_h
```

La confluencia es una distancia continua. No concede puntos ni presupone que
el precio reaccionara.

## 5. Evidencia historica preservada

Inventario reproducible:

```text
auditorias_motor/fibonacci_historical_cases_v0_1.json
```

Resultado:

| Concepto | Casos |
|---|---:|
| Recomendaciones antiguas | 669 |
| Observaciones Fibonacci disponibles | 666 |
| Operaciones enlazadas | 163 |
| Operaciones cerradas | 154 |

SHA-256 del inventario:

```text
05f5e7b73785520c0a31a4a083a4f3d6b09b19e11083bfb6ec23a7386730a2cb
```

Estos 154 cierres podran utilizarse cuando se reconstruyan las nuevas
observaciones desde velas pre-trade. No se compararan directamente contra los
scores Fibonacci antiguos.

## 6. Trazabilidad

Cada regla registra:

- proveedor, intervalo, corte temporal y cuatro horizontes de contexto;
- parametros del detector y ratios utilizados;
- pivotes, confirmacion temporal y prominencia;
- swing, niveles y distancias normalizadas;
- formulas, familia, padres y hashes;
- estado evaluado o bloqueado y motivo;
- `probability_effect = none_shadow_observation`.

## 7. Estado de la biblioteca

La biblioteca mantiene 38 fichas:

- 5 operadores base;
- 11 reglas predictivas provisionales actuales;
- 8 candidatas implementadas en observacion;
- 14 candidatas pendientes, limitadas o bloqueadas.

Catalogo canonico:

```text
auditorias_motor/catalogo_maestro_biblioteca_predictiva_v0_1.json
7c91a8e6f148f18c02f5c19109e4ad6fbf0f852fa8463eb5f543ee52ac1706d8
```

## 8. Limite

La literatura respalda el estudio de niveles y Fibonacci como familia de
investigacion, no demuestra que estos ratios, pivotes o distancias mejoren por
si solos P(TP primero). Esa aportacion se estimara con operaciones cerradas y
validacion temporal.

El siguiente bloque de la hoja de ruta es funding relativo y crowding.

## 9. Verificacion

```text
650 pruebas ejecutadas
650 correctas
0 fallos
```
