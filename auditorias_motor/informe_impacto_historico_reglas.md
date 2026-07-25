# Informe de impacto historico de reglas - E1.4

Version de auditoria: `E1.4-v0.1`

Estado: COMPLETADA

## Dictamen

El champion congelado puede reproducirse de forma determinista sobre sus 86
snapshots historicos comparables. La auditoria cuantifica cuanto cambia la
salida cuando se elimina una contribucion registrada, pero no demuestra que una
regla prediga correctamente el futuro.

No se modificaron recomendaciones, operaciones, evaluaciones, probabilidades ni
filas de Supabase.

## Cobertura

- Recomendaciones totales inventariadas: 875.
- Analisis con salida estructurada completa: 844.
- Cohorte exacta del engine `rules-v0.12.1-liquidations-readable`: 86.
- Casos con `scoring_version` explicita: 18.
- Casos del mismo engine sin esa columna historica: 68.
- Motores anteriores excluidos del replay actual: 789.
- Operaciones vinculadas: 21.
- Outcomes completos reconstruidos: 20.
- Pares: 79 BTCUSDT y 7 ETHUSDT.
- Horizontes: 19 intradia corto, 40 intradia amplio y 27 swing corto.

Los 68 casos sin `scoring_version` se clasifican como
`formula_compatible_legacy_contract`, no como contrato exacto. Su inclusion se
justifica porque reproducen todas las salidas del engine congelado.

## Paridad

El replayer reproduce:

- TP, SL y rango: 86/86.
- Grado: 86/86.
- Nivel de riesgo: 86/86.
- Decision: 86/86.
- Error maximo TP/SL: 0.00005, atribuible al redondeo persistido.
- Error maximo rango: 0.

Una ablation solo se calcula despues de superar esta comprobacion.

## Tipos de ablation

`local_ablation` elimina una contribucion numerica del camino donde fue
registrada y recalcula caps, TP, SL, rango, EV, grado y decision. No afirma
haber retirado todas las rutas correlacionadas de la regla.

`aggregate_replayable` permite retirar un agregado historico completo. Es el
caso de `risk_calibration_bundle`, porque se guardaron sus ajustes de
probabilidad, riesgo, EV, confianza, cap y bloqueo.

`partial` identifica grupos cuyo efecto completo no puede separarse. No se
presentan como ablations causales.

## Mayor impacto mecanico

| Unidad | Estado | Activa | Media TP activa | Max TP | Cambia grado | Cambia decision | Cambia signo EV |
|---|---:|---:|---:|---:|---:|---:|---:|
| EMA overlap directo | parcial | 81 | 8.127 pp | 15.9 pp | 8 | 8 | 17 |
| Calibracion agregada | reproducible | 58 | 5.217 pp | 13.5 pp | 7 | 5 | 1 |
| Tendencia | local | 75 | 5.312 pp | 10.0 pp | 6 | 5 | 11 |
| Precio frente a entrada | local | 86 | 1.848 pp | 3.0 pp | 5 | 5 | 3 |
| Barrera tecnica | local | 76 | 1.738 pp | 2.5 pp | 6 | 5 | 2 |
| Penalizacion de nivel | local | 55 | 2.182 pp | 2.5 pp | 5 | 4 | 1 |
| Volatilidad | local | 42 | 4.332 pp | 7.0 pp | 3 | 2 | 3 |

Los datos completos de las 32 unidades estan en
`impacto_historico_reglas_v0_1.json`.

## Conclusiones tecnicas

### 1. EMA domina por rutas solapadas

El grupo directo EMA cambia 70 probabilidades, 8 grados, 8 decisiones y el
signo del EV en 17 casos. Es el mayor impacto mecanico observado, pero es
parcial: gates EMA incluidos dentro de calibracion no pueden separarse. Esto
confirma el doble conteo detectado en E1.3 y obliga a un modelo estructural
unico en el challenger.

### 2. La calibracion tiene poder de veto

El agregado de calibracion esta activo en 58/86 casos, mueve TP una media de
5.217 puntos cuando actua y hasta 13.5 puntos. Cambia siete grados y cinco
decisiones.

No pueden atribuirse esos efectos a cada uno de sus 17 flags. La traza guarda
flags y un ajuste agregado despues de aplicar caps internos; por tanto, repartir
el resultado entre flags seria inventar informacion.

Los flags mas frecuentes son:

- `ticker_24h_contra_side`: 33.
- `direction_score_lt_40`: 31.
- `price_vs_ema_1h_contra_side`: 29.
- `sl_probability_gte_55`: 27.
- `technical_score_lt_40`: 26.
- `ema_stack_15m_contra_side`: 26.

### 3. La regla precio-entrada alcanza todas las observaciones

`price_vs_entry_bias` esta activa en 86/86 casos. Su retirada cambia 62
probabilidades, cinco grados y cinco decisiones. E1.3 ya demostro que contiene
un salto discontinuo de cinco puntos; E1.4 demuestra que no es marginal.

### 4. Los caps anulan contribuciones

Una regla puede estar activa y no cambiar TP porque la salida ya esta saturada.
Ejemplos:

- tendencia: activa en 75, cambia TP en 57;
- precio-entrada: activa en 86, cambia TP en 62;
- barrera tecnica: activa en 76, cambia TP en 57.

El aprendizaje necesita registrar contribucion pre-cap y post-cap. De lo
contrario puede atribuir efecto a una regla que en ese analisis no altero la
salida final.

### 5. Hay reglas sin activacion en esta cohorte

No se activaron:

- `funding_penalty`;
- `liquidity_penalty`;
- `zone_range_probability_adjustment`;
- `risk_calibration_range_adjustment`.

Esto no demuestra que sean inutiles. Demuestra que los 86 casos no contienen
evidencia para evaluarlas.

## Lo que no puede concluirse

Esta fase no autoriza a aumentar, reducir o retirar pesos. Solo 20 casos tienen
outcome reconstruido completo, 79 de 86 analisis son BTC y solo aparecen dos
pares. No existe muestra suficiente para:

- medir utilidad predictiva fiable por regla;
- validar universalidad entre pares;
- separar individualmente los 17 flags de calibracion;
- concluir que cambiar una decision historica habria generado beneficio;
- confundir impacto mecanico con mejora de precision.

## Ganancia para el aprendizaje

Antes de E1.4 sabiamos que el score era incoherente. Ahora sabemos exactamente
que componentes dominan, en cuantos casos sobreviven a los caps y cuantas
salidas downstream alteran.

Estos resultados fijan las prioridades del challenger:

1. eliminar el solapamiento EMA;
2. sustituir el salto precio-entrada por una variable continua;
3. descomponer calibracion en reglas trazables;
4. registrar efecto pre-cap y post-cap;
5. validar por par y horizonte antes de activar cambios.

## Siguiente fase

E1.5 definira el contrato del challenger probabilistico en sombra. Debe superar
los invariantes E1.3 y compararse contra el champion con los grupos y limites
de trazabilidad descubiertos en E1.4.
