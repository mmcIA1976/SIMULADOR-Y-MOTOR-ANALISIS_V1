# Preservacion heatmap y primera familia tecnica

Fecha: 2026-07-29
Estado: IMPLEMENTADO; SIN NUEVOS PESOS

## 1. Evidencia historica del heatmap

Se consulto la base online en modo lectura para todas las recomendaciones
`rules-v0.12%`.

Resultado:

```text
recomendaciones                         107
analisis sin operacion vinculada         83
operaciones vinculadas                   24
operaciones cerradas                     24
observaciones de liquidacion presentes  107
observaciones disponibles               104
casos vinculados, cerrados y resueltos   24
```

Las 30 operaciones eran el minimo planeado para revisar peso, no el numero
realmente completado. Los 24 casos existentes no se descartan.

Artefactos:

```text
audit_heatmap_historical_cases.py
auditorias_motor/heatmap_historical_cases_v0_1.json
```

El inventario conserva IDs de recomendacion y operacion, version, estado,
calidad del snapshot, lectura del mapa y estado del outcome. No modifica la
base de datos.

## 2. Primera familia tecnica

Reglas implementadas en observacion:

```text
LIB-CAND-EMA-TREND-001
LIB-CAND-RSI-WILDER-001
LIB-CAND-ATR-EXTENSION-001
```

Calculos:

- EMA20, EMA50 y EMA200 con semilla SMA y alpha estandar `2/(n+1)`;
- pendiente EMA50 de seis barras normalizada por ATR14;
- distancia logaritmica cierre-EMA50 y EMA50-EMA200;
- RSI14 con suavizado original de Wilder;
- ATR14 con true range y suavizado de Wilder;
- extension `(close-EMA20)/ATR14`;
- salidas alineadas con el lado long/short.

## 3. Condiciones

- solo velas cerradas anteriores o iguales a `analysis_at`;
- minimo 206 velas para EMA200 y pendiente;
- bloqueo explicito si ATR es cero o faltan datos;
- misma formula para todos los pares;
- intervalo derivado del horizonte vigente;
- snapshot y hash de la fuente conservados.

## 4. Integracion

Cada analisis nuevo conserva:

- inputs;
- outputs;
- formulas;
- familia y padres;
- lado;
- intervalo;
- corte temporal;
- hash de los datos;
- hash de la traza;
- estado `evaluated_shadow`;
- efecto probabilistico `none_shadow_observation`.

Al cerrar la operacion, estos valores se enlazan con TP, SL o expiracion. Esto
permite medir su relacion con el outcome antes de estimar coeficientes.

## 5. Limite deliberado

Estas tres reglas no modifican todavia TP/SL. Activarlas con puntos o pesos
manuales repetiria el defecto del motor antiguo. El siguiente paso es producir
un dataset historico compatible y estimar su aportacion individual y familiar.
