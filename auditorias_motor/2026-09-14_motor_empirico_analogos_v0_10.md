# Motor empírico de análogos v0.10

- Motor: `TP-SL-EMPIRICAL-ANALOG-v0.10`.
- Arquitectura: un único motor; sin fórmula browniana ni coeficientes de geometría.
- Resultado: frecuencias ponderadas de primeros toques observados en futuros históricos de 5m.
- Registros históricos en artefacto: **5242**.
- Grupos activos seleccionados por horizonte: `{"intraday_short": ["price_path", "trend_momentum", "volatility_regime"], "intraday_wide": ["price_path", "volatility_regime"], "short_swing": ["price_path", "volatility_regime"]}`.
- Cambio frente a v0.9: se añade únicamente EMA50/EMA200 orientada al lado en la selección de análogos del tramo 0-4 h.
- Evidencia de selección: `79a8005d4cf1a4d1f78d7aa7917aeb9324637e8daf916865423456ab87c2c75d`.
- Rule-test log-loss/Brier macro: `0.670862` / `0.420811`.
- Final sellado log-loss/Brier macro: `0.713209` / `0.455734`.
- Autorización de producción: **True**.
- Mejora macro final frente a first-passage (sólo referencia de validación): log-loss `0.019454`, Brier `0.005003`.
- Cobertura final no ambigua: `100.000%`.

## Contrato

1. La geometría TP/SL se aplica directamente sobre cada trayectoria histórica.
2. Las reglas sólo seleccionan contextos anteriores comparables.
3. Intradía medio hereda el tramo corto; intradía largo hereda corto y medio.
4. Un primer toque anterior no puede reclasificarse.
5. Los casos ambiguos dentro de una vela de 5m se excluyen.
6. Si el contexto queda fuera del soporte histórico, el análisis se bloquea.
7. Una muestra condicional tardía escasa amplía el intervalo y queda trazada.

## Limitaciones observadas

- Frente a v0.9, la candidata mejora log-loss y Brier en las seis combinaciones de horizonte y lado, pero los intervalos individuales todavía cruzan cero.
- El desglose por activo no contiene perjuicios consistentes ni confirmados; 19 celdas son favorables consistentes y 17 quedan mixtas.
- Frente a first-passage, el Brier final de 0-4 h queda ligeramente peor; la autorización exige mejora macro y se apoya además en la comparación directa contra v0.9.
- La referencia first-passage sólo se usa para validar y no se ejecuta ni mezcla en producción.

## Reglas excluidas

- Fibonacci y niveles estructurales: no activos hasta validar su proyección dinámica para cualquier TP/SL.
- Liquidaciones: no activas porque no existe histórico fechado suficiente en el artefacto.
