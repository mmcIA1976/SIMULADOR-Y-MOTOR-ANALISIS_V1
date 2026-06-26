# Auditoria aprendizaje - operaciones verificadas 130

Fecha: 2026-06-26

Estado: hipotesis registradas, no aplicadas al motor.

Motor vigente auditado: `rules-v0.9-pending-zone-adjusted`

## Snapshot de datos

- Operaciones registradas: 140.
- Operaciones cerradas verificadas: 130.
- Evaluaciones de aprendizaje: 127.
- Analisis/recomendaciones guardados: 416.
- Ticks de precio registrados: 31.997.
- Operaciones cerradas pendientes de evaluacion: 3.
- Operaciones pendientes de evaluar detectadas: 135, 137 y 138.

## Regla de seguimiento

Esta auditoria queda como punto base.

No se aplican cambios al motor hasta comprobar las hipotesis con mas operaciones posteriores.

Revision recomendada:

- primera revision: 180 operaciones cerradas verificadas;
- revision mas fiable: 230 operaciones cerradas verificadas;
- validacion por hipotesis: minimo 30 casos nuevos comparables;
- validacion fuerte por hipotesis: 50-60 casos nuevos comparables.

## Hipotesis 01 - Endurecer filtro por probabilidad de STOP LOSS

Archivo sugerido si se separa en ficha individual:

`hipotesis_01_operaciones_verificadas_130_sl_probability.md`

Dato observado:

- `SL probability < 40%`: resultado positivo.
- `SL probability 40-50%`: resultado positivo.
- `SL probability 50-60%`: resultado muy negativo.
- `SL probability >= 60%`: resultado muy negativo.

Mejora candidata:

- Si `sl_probability >= 0.50`, degradar la decision final hacia `observar`.
- Si `sl_probability >= 0.60`, exigir confluencia excepcional para permitir `simular`.
- No aplicar como regla aislada sin cruzar con direccion, regimen y calidad tecnica.

Criterio de comprobacion futura:

- Revisar nuevas operaciones con `sl_probability >= 0.50`.
- Comparar PnL real contra el PnL que se habria evitado si se hubiera bloqueado o degradado la operacion.
- Separar por mercado, `limit_pullback`, `stop_breakout` y `stop_breakdown`.

Minimo para revisar:

- 30 casos nuevos con `sl_probability >= 0.50`.

Estado:

- Pendiente.

## Hipotesis 02 - Penalizar direction_score bajo

Archivo sugerido:

`hipotesis_02_operaciones_verificadas_130_direction_score.md`

Dato observado:

- `direction_score < 50`: 85 casos, resultado muy negativo.
- `direction_score 50-70`: resultado positivo.

Mejora candidata:

- Si `direction_score < 50`, bajar probabilidad de TP y subir riesgo salvo que exista una razon estructural muy clara.
- Evitar que un buen ratio riesgo/beneficio compense una direccion mala.
- Usar `direction_score` como filtro primario, no como metrica secundaria.

Criterio de comprobacion futura:

- Auditar nuevas operaciones con `direction_score < 50`.
- Medir si las ganadoras son excepciones explicables o ruido.
- Comprobar si el filtro mejora especialmente en longs debiles.

Minimo para revisar:

- 30 casos nuevos con `direction_score < 50`.

Estado:

- Pendiente.

## Hipotesis 03 - Long contra tendencia bajista debe ser mas exigente

Archivo sugerido:

`hipotesis_03_operaciones_verificadas_130_long_tendencia_bajista.md`

Dato observado:

- `short + tendencia_bajista`: resultado positivo.
- `long + tendencia_bajista`: resultado muy negativo.

Mejora candidata:

- Penalizar mas los longs en `tendencia_bajista`.
- Permitir long contra tendencia solo si hay evidencia fuerte de rebote, barrida confirmada, soporte claro, mejora de momentum y riesgo de SL bajo.
- Mantener short en tendencia bajista como contexto potencialmente favorable, pero no automatico.

Criterio de comprobacion futura:

- Separar longs en tendencia bajista por rebote real, persecucion de precio, ruptura fallida y operacion contra estructura.
- Medir si el filtro habria reducido perdidas sin bloquear buenos rebotes.

Minimo para revisar:

- 30 casos nuevos `long + tendencia_bajista`.

Estado:

- Pendiente.

## Hipotesis 04 - No premiar RR alto si la estructura no acompana

Archivo sugerido:

`hipotesis_04_operaciones_verificadas_130_rr_alto_estructura.md`

Dato observado:

- `risk_reward_ratio >= 2` tuvo mal resultado global.
- `long + RR >= 2` fue especialmente negativo.
- En shorts, el tramo mas sano estuvo mas cerca de `RR 1-2`.

Mejora candidata:

- Dejar de tratar `RR >= 2` como mejora automatica.
- Penalizar RR alto cuando venga de un TP demasiado lejano, direccion debil o SL con alta probabilidad.
- Valorar mas la alcanzabilidad del TP que la distancia teorica del TP.

Criterio de comprobacion futura:

- Comparar operaciones con RR alto por lado y regimen.
- Revisar si el TP estaba bloqueado por resistencias/soportes, liquidez o falta de momentum.
- Medir MFE frente a distancia al TP para saber si el objetivo era realista.

Minimo para revisar:

- 30 casos nuevos con `risk_reward_ratio >= 2`.

Estado:

- Pendiente.

## Hipotesis 05 - Revisar confianza alta en setup C

Archivo sugerido:

`hipotesis_05_operaciones_verificadas_130_confianza_alta_setup_c.md`

Dato observado:

- `confidence = media` y `setup_grade = C`: resultado positivo.
- `confidence = alta` y `setup_grade = C`: muestra pequena, pero resultado muy negativo.

Mejora candidata:

- Auditar por que el motor asigna confianza alta a setups C.
- Evitar que una o dos metricas fuertes eleven demasiado la confianza si hay contradicciones internas.
- Convertir algunos casos `alta + C` en `media` o `media-baja` si direccion, SL o regimen no acompanan.

Criterio de comprobacion futura:

- Reunir mas casos `alta + C`.
- Comparar contra `media + C`.
- Revisar si el fallo viene de sobrepeso de indicadores puntuales.

Minimo para revisar:

- 30 casos nuevos con `confidence = alta` y `setup_grade = C`.

Estado:

- Pendiente.

## Hipotesis 06 - Mantener Fibonacci como confluencia secundaria

Archivo sugerido:

`hipotesis_06_operaciones_verificadas_130_fibonacci_secundario.md`

Dato observado:

- Los casos con Fibonacci favorable todavia no muestran mejora clara.
- La muestra es pequena.
- Algunas zonas favorables de Fibonacci terminaron en resultado negativo.

Mejora candidata:

- No subir peso de Fibonacci por ahora.
- Usarlo solo como confluencia, nunca como razon principal para apoyar una operacion.
- Penalizar menos o nada si Fibonacci es neutral, salvo que coincida con otras alertas.

Criterio de comprobacion futura:

- Esperar mas casos con Fibonacci completo.
- Comparar por `bias`, `entry_zone`, `target_zone`, `stop_zone` y `probability_adjustment`.
- Validar si funciona mejor en pullbacks que en rupturas.

Minimo para revisar:

- 50 casos nuevos con contexto Fibonacci completo.

Estado:

- Pendiente.

## Hipotesis 07 - Penalizar stop_breakdown pendiente hasta tener mejor evidencia

Archivo sugerido:

`hipotesis_07_operaciones_verificadas_130_stop_breakdown.md`

Dato observado:

- Las ordenes `stop_breakdown` cerradas muestran muestra pequena, pero resultado 0 ganadoras / 7 perdedoras.
- Muchas quedan relacionadas con riesgo de falsa ruptura o barrida.

Mejora candidata:

- Penalizar `entry_order_type = stop_breakdown` si hay riesgo de falsa ruptura, barrida alta o confluencia insuficiente.
- Exigir confirmacion adicional de volumen, momentum y ruptura limpia antes de apoyar la orden.
- No generalizar aun a todos los breakdowns: la muestra es pequena.

Criterio de comprobacion futura:

- Separar `stop_breakdown` por `reaction_bias`, `liquidity_sweep_risk`, `zone_confluence_score` y `activation_probability`.
- Medir no solo PnL, sino activacion, MAE, MFE y tiempo hasta invalidacion.

Minimo para revisar:

- 30 ordenes nuevas `stop_breakdown` cerradas.

Estado:

- Pendiente.

## Hipotesis 08 - Separar fallo tecnico de fallo por exposicion

Archivo sugerido:

`hipotesis_08_operaciones_verificadas_130_exposicion_vs_tecnica.md`

Dato observado:

- Todavia aparecen casos clasificados como `excessive_leverage`.
- El apalancamiento no cambia la direccion del mercado; cambia el impacto economico y la exposicion.

Mejora candidata:

- No usar apalancamiento para bajar la probabilidad tecnica direccional.
- Mantener apalancamiento en una capa separada de gestion de riesgo/exposicion.
- Si una operacion falla por movimiento contrario, clasificar el fallo tecnico real: direccion, estructura, SL probable, RR debil, zona pendiente, etc.

Criterio de comprobacion futura:

- Auditar nuevos fallos clasificados como exposicion.
- Confirmar que no estan ocultando un fallo tecnico real.
- Separar resultado tecnico del resultado monetario.

Minimo para revisar:

- 30 nuevos fallos donde el aprendizaje clasifique o mencione exposicion/apalancamiento.

Estado:

- Pendiente.

## Hipotesis 09 - Dar mas peso a la decision final del motor

Archivo sugerido:

`hipotesis_09_operaciones_verificadas_130_decision_observar.md`

Dato observado:

- Operaciones con decision `simular` o `simular con tamano prudente` tuvieron resultado positivo.
- Operaciones donde el motor dijo `observar` y aun asi se operaron tuvieron resultado negativo.

Mejora candidata:

- Hacer que `observar` sea mas vinculante en la interpretacion del analisis.
- Si el usuario opera una recomendacion `observar`, guardar el caso como operacion contra advertencia del motor.
- No reforzar como patron ganador una operacion que gana pero iba contra una advertencia fuerte.

Criterio de comprobacion futura:

- Medir resultado de operaciones tomadas contra `observar`.
- Separar ganadoras contra analisis de ganadoras respaldadas por analisis.
- Revisar si `observar` evita perdidas netas de forma consistente.

Minimo para revisar:

- 30 operaciones nuevas donde la decision original haya sido `observar` y el usuario opere igualmente.

Estado:

- Pendiente.

## Prioridad de revision

1. `sl_probability >= 0.50`.
2. `direction_score < 50`.
3. `long + tendencia_bajista`.
4. `risk_reward_ratio >= 2` sin estructura.
5. `confidence alta + setup C`.
6. `stop_breakdown`.
7. Fibonacci como confluencia secundaria.
8. Separacion exposicion vs tecnica.
9. Peso de la decision `observar`.

