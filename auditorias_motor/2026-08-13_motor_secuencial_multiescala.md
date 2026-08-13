# Motor secuencial multiescala

- Motor: `TP-SL-SEQUENTIAL-MULTISCALE-v0.8`.
- Decisión: **`promote_single_sequential_multiscale_engine`**.
- Autorizado para producción: **True**.
- Arquitectura: un único motor con etapas condicionales anidadas.

## Etapas

| Tramo | Datos propios | Hereda | Reglas activas |
|---|---|---|---|
| 0-4 h | 5m sobre contexto 4 h | ninguno | True |
| 4-24 h | 1h sobre contexto 24 h | intraday_short | True |
| 24 h-7 d | 6h sobre contexto 168 h | intraday_short, intraday_wide | False |

`False` en el último tramo no significa que el marco largo quede sin analizar:
mantiene la física de primer toque, la volatilidad propia 6h/7d y toda la
probabilidad heredada de 0-24h. Significa únicamente que el ajuste direccional
de las reglas fue rechazado al empeorar fuera de muestra y, por tanto, no se
forzó un peso sin evidencia.

## Prueba final frente a v0.7

| Marco | Δ log-loss | Δ Brier |
|---|---:|---:|
| `intraday_short` | 0.125026 | 0.038734 |
| `intraday_wide` | 0.087717 | 0.046880 |
| `short_swing` | 0.023168 | -0.001668 |

- IC95% semanal log-loss: `[0.05787669250174337, 0.10088628143857697]`.
- IC95% semanal Brier: `[0.01918592472807358, 0.03698363514358733]`.
- Errores de invariantes: `{}`.

El resultado de un tramo sólo se añade a la masa que sobrevivió al anterior; un primer toque anterior nunca puede reclasificarse.
