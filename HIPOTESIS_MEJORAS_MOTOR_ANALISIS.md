# Hipotesis de mejoras del motor de analisis

Este archivo registra mejoras candidatas detectadas por auditoria de datos reales.

Importante: estas reglas no estan aplicadas al motor. Quedan congeladas como hipotesis para contrastarlas cuando existan mas operaciones cerradas y evaluadas. El objetivo es comprobar si habrian mejorado el resultado antes de convertirlas en cambios reales de pesos, probabilidades o decisiones.

Fuente estructurada:

- `auditorias_aprendizaje/2026-06-26_operaciones_verificadas_130_hipotesis_motor_v0_9.md`

Las siguientes secciones resumen la primera auditoria. Las comprobaciones futuras deben guardarse dentro de `auditorias_aprendizaje/` usando la convencion de nombres documentada en `auditorias_aprendizaje/README.md`.

## 2026-06-26 - Auditoria Supabase: operaciones, recomendaciones y aprendizaje

Base revisada:

- 140 operaciones registradas.
- 130 operaciones cerradas.
- 127 evaluaciones de aprendizaje.
- 416 analisis/recomendaciones guardados.
- 31.997 ticks de precio.
- 3 operaciones cerradas pendientes de evaluacion de aprendizaje: 135, 137 y 138.

### Hipotesis 1 - Endurecer filtro por probabilidad de STOP LOSS

Dato observado:

- `SL probability < 40%`: resultado positivo.
- `SL probability 40-50%`: resultado positivo.
- `SL probability 50-60%`: resultado muy negativo.
- `SL probability >= 60%`: resultado muy negativo.

Mejora candidata:

- Si `sl_probability >= 0.50`, degradar la decision final hacia `observar`.
- Si `sl_probability >= 0.60`, exigir confluencia excepcional para permitir `simular`.
- No aplicar como regla aislada sin cruzar con direccion, regimen y calidad tecnica.

Criterio futuro de validacion:

- Comparar nuevas operaciones con `sl_probability >= 0.50`.
- Medir si habrian evitado perdidas netas sin eliminar demasiadas ganadoras.
- Revisar por separado mercado, limit pullback, stop breakout y stop breakdown.

Estado:

- Pendiente de validacion con mas operaciones.

### Hipotesis 2 - Penalizar direction_score bajo

Dato observado:

- `direction_score < 50`: 85 casos, resultado muy negativo.
- `direction_score 50-70`: resultado positivo.

Mejora candidata:

- Si `direction_score < 50`, bajar probabilidad de TP y subir riesgo salvo que exista una razon estructural muy clara.
- Evitar que un buen ratio riesgo/beneficio compense una direccion mala.
- Usar `direction_score` como filtro primario, no como metrica secundaria.

Criterio futuro de validacion:

- Auditar nuevas operaciones con `direction_score < 50`.
- Medir si las ganadoras son excepciones explicables o ruido.
- Comprobar si el filtro mejora especialmente en longs debiles.

Estado:

- Pendiente de validacion con mas operaciones.

### Hipotesis 3 - Long contra tendencia bajista debe ser mucho mas exigente

Dato observado:

- `short + tendencia_bajista`: resultado positivo.
- `long + tendencia_bajista`: resultado muy negativo.

Mejora candidata:

- Penalizar mas los longs en `tendencia_bajista`.
- Permitir long contra tendencia solo si hay evidencia fuerte de rebote, barrida confirmada, soporte claro, mejora de momentum y riesgo de SL bajo.
- Mantener short en tendencia bajista como contexto potencialmente favorable, pero no automatico.

Criterio futuro de validacion:

- Separar longs en tendencia bajista entre:
  - rebote real desde soporte;
  - persecucion de precio;
  - ruptura fallida;
  - operacion contra estructura.
- Medir si el filtro habria reducido perdidas sin bloquear buenos rebotes.

Estado:

- Pendiente de validacion con mas operaciones.

### Hipotesis 4 - No premiar RR alto si la estructura no acompana

Dato observado:

- `risk_reward_ratio >= 2` tuvo mal resultado global.
- `long + RR >= 2` fue especialmente negativo.
- En shorts, el tramo mas sano estuvo mas cerca de `RR 1-2`.

Mejora candidata:

- Dejar de tratar `RR >= 2` como mejora automatica.
- Penalizar RR alto cuando venga de un TP demasiado lejano, direccion debil o SL con alta probabilidad.
- Valorar mas la alcanzabilidad del TP que la distancia teorica del TP.

Criterio futuro de validacion:

- Comparar operaciones con RR alto por lado y regimen.
- Revisar si el TP estaba bloqueado por resistencias/soportes, liquidez o falta de momentum.
- Medir MFE frente a distancia al TP para saber si el objetivo era realista.

Estado:

- Pendiente de validacion con mas operaciones.

### Hipotesis 5 - Revisar confianza alta en setup C

Dato observado:

- `confidence = media` y `setup_grade = C`: resultado positivo.
- `confidence = alta` y `setup_grade = C`: muestra pequena, pero resultado muy negativo.

Mejora candidata:

- Auditar por que el motor asigna confianza alta a setups C.
- Evitar que una o dos metricas fuertes eleven demasiado la confianza si hay contradicciones internas.
- Convertir algunos casos `alta + C` en `media` o `media-baja` si direccion, SL o regimen no acompanan.

Criterio futuro de validacion:

- Reunir mas casos `alta + C`.
- Comparar contra `media + C`.
- Revisar si el fallo viene de sobrepeso de indicadores puntuales.

Estado:

- Pendiente de validacion con mas operaciones.

### Hipotesis 6 - Mantener Fibonacci como confluencia secundaria

Dato observado:

- Los casos con Fibonacci favorable todavia no muestran mejora clara.
- La muestra es pequena.
- Algunas zonas favorables de Fibonacci terminaron en resultado negativo.

Mejora candidata:

- No subir peso de Fibonacci por ahora.
- Usarlo solo como confluencia, nunca como razon principal para apoyar una operacion.
- Penalizar menos o nada si Fibonacci es neutral, salvo que coincida con otras alertas.

Criterio futuro de validacion:

- Esperar mas casos con Fibonacci completo.
- Comparar por `bias`, `entry_zone`, `target_zone`, `stop_zone` y `probability_adjustment`.
- Validar si funciona mejor en pullbacks que en rupturas.

Estado:

- Pendiente de validacion con mas operaciones.

### Hipotesis 7 - Penalizar stop_breakdown pendiente hasta tener mejor evidencia

Dato observado:

- Las ordenes `stop_breakdown` cerradas muestran muestra pequena, pero resultado 0 ganadoras / 7 perdedoras.
- Muchas quedan relacionadas con riesgo de falsa ruptura o barrida.

Mejora candidata:

- Penalizar `entry_order_type = stop_breakdown` si hay riesgo de falsa ruptura, barrida alta o confluencia insuficiente.
- Exigir confirmacion adicional de volumen, momentum y ruptura limpia antes de apoyar la orden.
- No generalizar aun a todos los breakdowns: la muestra es pequena.

Criterio futuro de validacion:

- Esperar mas operaciones pendientes cerradas.
- Separar `stop_breakdown` por `reaction_bias`, `liquidity_sweep_risk`, `zone_confluence_score` y `activation_probability`.
- Medir no solo PnL, sino activacion, MAE, MFE y tiempo hasta invalidacion.

Estado:

- Pendiente de validacion con mas operaciones.

### Hipotesis 8 - Separar fallo tecnico de fallo por exposicion

Dato observado:

- Todavia aparecen casos clasificados como `excessive_leverage`.
- El apalancamiento no cambia la direccion del mercado; cambia el impacto economico y la exposicion.

Mejora candidata:

- No usar apalancamiento para bajar la probabilidad tecnica direccional.
- Mantener apalancamiento en una capa separada de gestion de riesgo/exposicion.
- Si una operacion falla por movimiento contrario, clasificar el fallo tecnico real: direccion, estructura, SL probable, RR debil, zona pendiente, etc.

Criterio futuro de validacion:

- Auditar nuevos fallos clasificados como exposicion.
- Confirmar que no estan ocultando un fallo tecnico real.
- Separar resultado tecnico del resultado monetario.

Estado:

- Pendiente de validacion con mas operaciones.

### Hipotesis 9 - Dar mas peso a la decision final del motor

Dato observado:

- Operaciones con decision `simular` o `simular con tamano prudente` tuvieron resultado positivo.
- Operaciones donde el motor dijo `observar` y aun asi se operaron tuvieron resultado negativo.

Mejora candidata:

- Hacer que `observar` sea mas vinculante en la interpretacion del analisis.
- Si el usuario opera una recomendacion `observar`, guardar el caso como operacion contra advertencia del motor.
- No reforzar como patron ganador una operacion que gana pero iba contra una advertencia fuerte.

Criterio futuro de validacion:

- Medir resultado de operaciones tomadas contra `observar`.
- Separar ganadoras contra analisis de ganadoras respaldadas por analisis.
- Revisar si `observar` evita perdidas netas de forma consistente.

Estado:

- Pendiente de validacion con mas operaciones.

## Orden de prioridad para futura implementacion

1. Penalizacion por `sl_probability >= 0.50`.
2. Penalizacion por `direction_score < 50`.
3. Penalizacion de long en `tendencia_bajista`.
4. Recalibracion de RR alto sin estructura.
5. Auditoria de confianza alta en setup C.
6. Stop breakdown pendiente con riesgo de falsa ruptura.
7. Fibonacci como confluencia secundaria hasta tener mas muestra.
8. Separacion tecnica entre fallo de analisis y fallo por exposicion.
9. Mayor peso a `observar` como advertencia real.

## Regla de decision antes de aplicar cambios

Ninguna de estas hipotesis debe aplicarse al motor hasta que se cumpla al menos una de estas condiciones:

- exista una muestra mayor de operaciones comparables;
- una nueva auditoria confirme el mismo patron;
- el impacto estimado muestre que habria reducido perdida neta sin eliminar demasiadas ganadoras;
- se pueda explicar la mejora con reglas simples, auditables y reversibles.
