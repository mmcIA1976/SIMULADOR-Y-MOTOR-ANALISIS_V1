# Valor incremental del horizonte en un motor único

- Decisión: **`horizon_value_demonstrated_rule_layer_ready_for_prospective_shadow_only`**.
- Motores independientes por marco: **no**.
- Cambio en producción: **ninguno**.

## Comparación física: mismo plan, sólo cambia el tiempo

| Partición | Δ log-loss | IC95% semanal | Δ Brier | IC95% semanal |
|---|---:|---|---:|---|
| `calibration` | 0.350482 | `[0.30881799307735824, 0.3915963276949335]` | 0.195190 | `[0.18091687922476926, 0.20962482820375256]` |
| `rule_test` | 0.414832 | `[0.3774680510020176, 0.4504940812258755]` | 0.215288 | `[0.20050879942526192, 0.22900140974208258]` |

## Modelos con reglas

| Candidato temporal | Comparador sin horizonte | Calibración positiva | Selección positiva |
|---|---|---|---|
| `horizon_aware_core` | `horizon_blind_core` | True | True |
| `horizon_aware_rules` | `horizon_blind_rules` | True | True |
| `horizon_aware_interactions` | `horizon_blind_rules` | True | True |

## Puerta final sellada

- Candidato: `horizon_aware_interactions`.
- Comparador: `horizon_blind_rules`.
- Núcleo temporal frente al núcleo ciego: **True**.
- Candidato completo frente al comparador ciego: **True**.
- Reglas frente al núcleo temporal en todos los horizontes: **False**.
- Δ log-loss: 0.362650.
- Δ Brier: 0.198599.

## Diagnóstico incremental posterior a la selección

Este diagnóstico no reabre la selección: comprueba si las reglas aportan más que usar correctamente la duración.

| Comparador temporal | Δ log-loss | IC95% | Δ Brier | IC95% |
|---|---:|---|---:|---|
| `horizon_aware_core` | 0.029146 | `[0.0169931069765117, 0.04091537322308307]` | 0.007984 | `[0.0017195500412162193, 0.01399655748007802]` |
| `horizon_aware_rules` | 0.024059 | `[0.01535035369142232, 0.03338407654186385]` | 0.005428 | `[0.002480987263718698, 0.008542603365433629]` |
