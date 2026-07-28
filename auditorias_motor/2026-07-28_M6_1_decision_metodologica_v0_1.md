# M6.1 - Decision metodologica probabilistica

Fecha: 2026-07-28
Estado: RECOMENDACION TECNICA COMPLETA; APROBACION PENDIENTE

## Problema exacto

El analisis es pre-trade y debe publicar conjuntamente:

- probabilidad de TP antes que SL dentro de H;
- probabilidad de SL antes que TP dentro de H;
- probabilidad de que ninguna barrera sea primera antes de expirar H.

La suma debe ser uno. No se calculan TP y SL de forma independiente.

## Arquitectura recomendada

### Capa A - baseline de primera barrera

`X(t)=sigma_H W(t)` en log-precio, sin drift impuesto.
Las barreras son `+d_TP` y `-d_SL`; el horizonte es `H`.
El modelo calcula salida superior, salida inferior y supervivencia.

### Capa B - evidencia mediante riesgos competitivos

Las variables M5 no suman puntos. Solo podran modificar los hazards
de TP y SL mediante coeficientes estimados con datos pre-trade y
resultados de primer evento. Mientras esten bloqueados, el resultado
sera exactamente el baseline.

## Decisiones

- Primera barrera doble: BASELINE SELECCIONADO.
- Riesgos competitivos discretos: CAPA DE EVIDENCIA SELECCIONADA.
- Multinomial directo: RECHAZADO COMO MODELO PRINCIPAL.
- Barreras TP/SL independientes: RECHAZADAS.

## Estado de las reglas M5

- Entradas directas del baseline: 5.
- Covariables candidatas con coeficiente bloqueado: 12.
- Reglas de ejecucion/economia: fuera de la probabilidad fisica.
- Coeficientes definidos: 0.

## Limites

Browniano es un baseline auditable, no una afirmacion de que BTC o
todos los pares sigan exactamente ese proceso. La suficiencia del
modelo solo podra decidirse con validacion temporal independiente.

## Puerta

- M6 iniciada: SI.
- M6.1 completada: SI.
- M6.2 autorizada: NO.
- Produccion modificada: NO.

Se requiere aprobacion u objecion del propietario sobre la
arquitectura de dos capas antes de definir el solver de M6.2.

## Fuentes primarias

- [First passage in an interval for fractional Brownian motion](https://arxiv.org/abs/1807.08807) (`WIESE-2019-FIRST-PASSAGE-INTERVAL`).
- [Anomalous diffusion and the first passage time problem](https://arxiv.org/abs/cond-mat/0105267) (`RANGARAJAN-DING-2001-TWO-BARRIERS`).
- [Revisiting the cumulative incidence function with competing risks data](https://academic.oup.com/jrsssc/article/72/2/498/7076689) (`KIM-ET-AL-2023-CIF`).
- [Discrete-time competing-risks regression with or without penalization](https://academic.oup.com/biometrics/article/81/2/ujaf040/8120014) (`LEE-ET-AL-2025-DISCRETE-COMPETING-RISKS`).
- [Strictly Proper Scoring Rules, Prediction, and Estimation](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf) (`GNEITING-RAFTERY-2007-PROPER-SCORES`).
- [Verification of forecasts expressed in terms of probability](https://journals.ametsoc.org/view/journals/mwre/78/1/1520-0493_1950_078_0001_vofeit_2_0_co_2.xml) (`BRIER-1950-PROBABILITY-FORECASTS`).

SHA-256 del payload canonico: `60b4fa2230ab91bb3733eae0cc948f3af5b34d8ce0f18aea6c6ca919c44b3a03`.
