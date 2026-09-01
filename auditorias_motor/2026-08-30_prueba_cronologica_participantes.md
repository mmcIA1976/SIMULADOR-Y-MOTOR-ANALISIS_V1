# Prueba cronológica mínima de participantes autónomos

- Motor: `TP-SL-EMPIRICAL-ANALOG-v0.9` / artefacto `TP-SL-EMPIRICAL-ANALOG-v0.9-frozen-001`.
- Ventana: 2026-08-01 a 2026-08-29 (UTC).
- Entrada simulada: apertura de la vela de 5 minutos inmediatamente posterior al corte de datos.
- Geometría: TP y SL simétricos a una sigma del horizonte; resultado bruto en R, sin costes.
- Producción y Supabase: cero escrituras.
- Contextos evaluados: 21077; bloqueados por soporte: 109 (0.51%); errores inesperados: 0.

## Equivalencia con producción

Validación `passed`. Diferencia máxima de features activas: `0`; diferencia máxima de probabilidad: `5.55e-17`.

## Resultados por umbral

| Horizonte | Umbral edge | Trades | Cuota | TP | SL | Sin resolver | Ambiguos | Win rate resuelto | R estricto | R/trade (IC 95%) | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| intraday_short | 0 pp | 87 | 100.0% | 27 | 28 | 32 | 0 | 49.1% | -3.155 | -0.036 (-0.195, 0.135) | 0.662 |
| intraday_short | 2 pp | 87 | 100.0% | 27 | 29 | 31 | 0 | 48.2% | -4.291 | -0.049 (-0.212, 0.122) | 0.666 |
| intraday_short | 4 pp | 87 | 100.0% | 25 | 32 | 30 | 0 | 43.9% | -7.730 | -0.089 (-0.236, 0.066) | 0.669 |
| intraday_short | 6 pp | 87 | 100.0% | 30 | 27 | 30 | 0 | 52.6% | 1.753 | 0.020 (-0.173, 0.229) | 0.681 |
| intraday_short | 8 pp | 87 | 100.0% | 31 | 26 | 30 | 0 | 54.4% | 1.896 | 0.022 (-0.173, 0.221) | 0.657 |
| intraday_short | 10 pp | 87 | 100.0% | 33 | 23 | 31 | 0 | 58.9% | 9.051 | 0.104 (-0.103, 0.304) | 0.678 |
| intraday_wide | 0 pp | 57 | 98.3% | 20 | 19 | 18 | 0 | 51.3% | -1.761 | -0.031 (-0.250, 0.191) | 0.662 |
| intraday_wide | 2 pp | 57 | 98.3% | 20 | 19 | 18 | 0 | 51.3% | -1.761 | -0.031 (-0.253, 0.201) | 0.662 |
| intraday_wide | 4 pp | 57 | 98.3% | 20 | 20 | 17 | 0 | 50.0% | -2.902 | -0.051 (-0.286, 0.185) | 0.669 |
| intraday_wide | 6 pp | 57 | 98.3% | 20 | 21 | 16 | 0 | 48.8% | -3.556 | -0.062 (-0.267, 0.143) | 0.657 |
| intraday_wide | 8 pp | 57 | 98.3% | 21 | 19 | 17 | 0 | 52.5% | -0.487 | -0.009 (-0.248, 0.229) | 0.679 |
| intraday_wide | 10 pp | 56 | 96.6% | 22 | 20 | 14 | 0 | 52.4% | 1.365 | 0.024 (-0.216, 0.263) | 0.665 |
| short_swing | 0 pp | 23 | 100.0% | 9 | 7 | 7 | 0 | 56.2% | 1.921 | 0.084 (-0.283, 0.442) | 0.705 |
| short_swing | 2 pp | 23 | 100.0% | 9 | 7 | 7 | 0 | 56.2% | 1.921 | 0.084 (-0.291, 0.441) | 0.705 |
| short_swing | 4 pp | 22 | 95.7% | 8 | 7 | 7 | 0 | 53.3% | 0.921 | 0.042 (-0.311, 0.410) | 0.711 |
| short_swing | 6 pp | 22 | 95.7% | 7 | 8 | 7 | 0 | 46.7% | -0.247 | -0.011 (-0.365, 0.334) | 0.747 |
| short_swing | 8 pp | 21 | 91.3% | 7 | 7 | 7 | 0 | 50.0% | 0.476 | 0.023 (-0.332, 0.380) | 0.765 |
| short_swing | 10 pp | 18 | 78.3% | 6 | 7 | 5 | 0 | 46.2% | -1.132 | -0.063 (-0.454, 0.351) | 0.726 |

## Lectura operativa

- `intraday_short`: mejor resultado descriptivo con 10 pp, 87 operaciones y 9.051 R; IC 95% del R medio (-0.103, 0.304).
- `intraday_wide`: mejor resultado descriptivo con 10 pp, 56 operaciones y 1.365 R; IC 95% del R medio (-0.216, 0.263).
- `short_swing`: mejor resultado descriptivo con 0 pp, 23 operaciones y 1.921 R; IC 95% del R medio (-0.283, 0.442).
- Ningún umbral queda validado como rentable si su intervalo incluye cero; el ganador de esta ventana es una hipótesis para seguimiento, no un peso aprendido.
- Los resultados por horizonte no autorizan un umbral universal: el filtro debe conservar identidad por participante/horizonte.

## Límites de interpretación

Esta es una prueba prospectiva histórica corta y exploratoria. Sirve para descartar umbrales inviables y detectar si las cuotas fuerzan entradas débiles; no basta por sí sola para declarar rentabilidad. Los casos en los que TP y SL aparecen dentro de la misma vela de 5 minutos se contabilizan como pérdida en el R estricto y como victoria únicamente en la cota optimista.
