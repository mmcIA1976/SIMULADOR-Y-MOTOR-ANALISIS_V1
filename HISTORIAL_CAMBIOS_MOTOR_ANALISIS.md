# Historial de Cambios del Motor de Analisis

Este archivo registra cada cambio relevante del motor de analisis para poder auditar si mejora o empeora con operaciones reales posteriores.

## 2026-06-09 - rules-v0.7-fibonacci-confluence

Estado de auditoria: implementacion inicial pendiente de validacion con operaciones cerradas.

Base de partida:
- Version anterior: `rules-v0.6-audit-calibrated`.
- Baseline v0.6: 68 operaciones cerradas evaluables.
- Se conserva la regla central: el R/R no infla directamente la probabilidad direccional.

Cambios realizados:
- Se anade deteccion automatica de swings por temporalidad usando pivotes objetivos y filtro minimo por ATR/rango.
- Se calculan retrocesos Fibonacci `0.236`, `0.382`, `0.5`, `0.618`, `0.786`.
- Se calculan extensiones `1.272`, `1.618`, `2.0`, `2.618`.
- Se incorpora `fibonacci_context` al resultado y snapshot del analisis.
- Se crea una metrica explicada `fibonacci_confluence`.
- Fibonacci se usa como confluencia de zona, calidad de entrada, calidad de TP/SL y riesgo de ejecucion.
- El ajuste directo sobre probabilidad queda limitado a `-0.02` / `+0.02`.
- El aprendizaje descriptivo empieza a registrar sesgo, zona de entrada y puntuacion Fibonacci dentro del patron guardado.
- Se endurece la validacion backend para impedir analisis u operaciones con SL/TP en el lado incorrecto de la entrada.
- `refresh_learning_evaluations` deja de recalcular historico cerrado ya evaluado; solo crea evaluaciones faltantes y omite cierres manuales todavia en observacion.

Motivo:
- Incorporar Fibonacci como sistema de zonas medibles, no como predictor aislado.
- Mejorar la lectura de entrada, invalidacion y objetivos cuando coinciden con estructura tecnica existente.
- Crear trazabilidad para auditar si las zonas Fibonacci aportan valor real por activo, lado y temporalidad.

Riesgo esperado:
- Posible sobreajuste si se da demasiado peso a Fibonacci antes de tener muestra suficiente.
- Posible ruido en mercados laterales o con swings poco limpios.
- Los pivotes automaticos pueden elegir un impulso distinto al que usaria un analista visual.

Estado pendiente de validacion:
- Auditar tras al menos 30 operaciones cerradas con `rules-v0.7-fibonacci-confluence`.
- Comparar operaciones con `fibonacci_context.bias = favorable` frente a neutral/desfavorable.
- Medir por separado `golden_zone`, retroceso superficial, entrada extendida, LONG/SHORT y temporalidad.

## 2026-06-07 - rules-v0.6-audit-calibrated

Estado de auditoria: aplicada tras auditoria de operaciones cerradas.

Muestra auditada:
- Operaciones cerradas evaluables: 68.
- Acierto global del analisis previo frente al resultado del plan: 77,94%.
- Mejor rendimiento observado: `technical_score` 85,7%, `market_regime` 80,0%, `asset_24h_move` 78,8%, `direction_score` 76,7%.
- Peor rendimiento observado: `risk_reward_ratio` 32,7%, `operation_quality` 33,3%, `cvd_spot` 52,1%, `order_book_imbalance` 57,9%.

Cambios realizados:
- Se sube la version del motor a `rules-v0.6-audit-calibrated`.
- Se anade `ENGINE_AUDIT_REFERENCE` al resultado y al snapshot guardado de cada analisis.
- Se incorpora `market_regime_bias` como ajuste direccional prudente, porque el regimen de mercado fue una de las capas con mejor tasa de acierto.
- Se reduce el impacto directo del `order_book_imbalance` en la probabilidad direccional.
- Se reduce el impacto directo del `cvd_spot` en la probabilidad direccional.
- Se recalibra `operation_quality_score` para que dependa menos del R/R y mas de EV neta y riesgo sobre margen.
- Se mantiene `risk_reward_ratio` fuera de la probabilidad direccional; sigue afectando a EV, break-even y calidad de diseno.

Hipotesis de mejora:
- El motor deberia mejorar especialmente en `intraday_wide`, donde estructura tecnica y regimen ya mostraban mejor comportamiento.
- El motor deberia ser menos vulnerable a falsas lecturas de CVD/order book aislados.
- El motor deberia dejar de sobrevalorar operaciones con buen R/R pero mala direccion probable.

Riesgos vigilados:
- No aumentar demasiado la confianza en tendencias ya agotadas.
- No penalizar en exceso rebotes contra tendencia que puedan funcionar por timing.
- Revisar si los shorts siguen quedando penalizados por capas no tecnicas.

Criterio de revision futura:
- Repetir auditoria tras al menos 30 nuevas operaciones cerradas con `rules-v0.6-audit-calibrated`.
- Comparar por separado: global, LONG, SHORT, `intraday_short`, `intraday_wide`, `short_swing`, BTC y altcoins.
- Si `risk_reward_ratio` o `operation_quality_score` siguen por debajo del 50%, mantenerlos fuera de la probabilidad direccional y usarlos solo como EV/diseno.

## Baseline Anterior - rules-v0.5-technical-ratings

Estado de auditoria: baseline comparativo.

Resumen:
- Funcionaba bien en estructura tecnica y regimen.
- Mostraba debilidad al interpretar R/R como parte de la calidad general.
- CVD y order book eran utiles como contexto, pero insuficientes como senales aisladas.
- La decision final era mas fiable en LONG que en SHORT.
