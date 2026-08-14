# Motor empírico de análogos v0.9

- Motor: `TP-SL-EMPIRICAL-ANALOG-v0.9`.
- Arquitectura: un único motor; sin fórmula browniana ni coeficientes de geometría.
- Resultado: frecuencias ponderadas de primeros toques observados en futuros históricos de 5m.
- Registros históricos en artefacto: **5242**.
- Grupos activos seleccionados por horizonte: `{"intraday_short": ["price_path", "volatility_regime"], "intraday_wide": ["price_path", "volatility_regime"], "short_swing": ["price_path", "volatility_regime"]}`.
- Rule-test log-loss/Brier macro: `0.674586` / `0.423684`.
- Final sellado log-loss/Brier macro: `0.716052` / `0.458266`.
- Autorización de producción: **True**.
- Mejora macro final frente a first-passage (sólo referencia de validación): log-loss `0.016611`, Brier `0.002471`.
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

- Intradía corto mejora log-loss final, pero su Brier queda ligeramente peor que la referencia.
- Intradía medio mejora ambas métricas en rule-test y periodo final.
- Intradía largo queda prácticamente empatado y ligeramente peor en el periodo final; no debe interpretarse sin su intervalo.
- La referencia first-passage sólo se usa para validar y no se ejecuta ni mezcla en producción.

## Reglas excluidas

- Fibonacci y niveles estructurales: no activos hasta validar su proyección dinámica para cualquier TP/SL.
- Liquidaciones: no activas porque no existe histórico fechado suficiente en el artefacto.
