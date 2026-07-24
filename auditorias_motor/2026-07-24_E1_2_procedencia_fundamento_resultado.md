# Resultado E1.2 - Procedencia y fundamento

Fecha de cierre: 2026-07-24
Estado: COMPLETADA
Champion modificado: NO
Scoring modificado: NO

## 1. Objetivo cumplido

Se ha vinculado el alcance ejecutable E1.1 con:

- procedencia del dato;
- definicion del indicador;
- teoria o evidencia externa aplicable;
- origen interno del proyecto;
- limite de transferencia de cada fuente;
- estado de respaldo;
- decision propuesta.

Toda funcion tiene una procedencia explicita. Cuando un concepto posee
literatura pero el umbral o peso concreto no, la funcion se clasifica como
`heuristica` o `empirica_provisional`, no como validada.

## 2. Cobertura

```text
modulos auditados                     8
funciones clasificadas          185/185
funciones con regla/convencion       105
fundamentadas                         72
empiricas provisionales               14
heuristicas                           99
literales numericos preservados     1528
fragmentos de formula preservados   3317
```

SHA-256 de la matriz:

`8a99436bc183a30bc5470a4fb423382dee4b1484ec951e175e5d001093490142`

## 3. Dictamen principal

El motor usa datos reales y familias reconocibles de analisis tecnico,
microestructura, derivados y riesgo. Sin embargo:

1. Las fuentes oficiales acreditan los datos, no los pesos.
2. RSI y ATR son variantes de media simple, no replicas completas de Wilder.
3. Fibonacci tiene evidencia externa no concluyente y no justifica scoring.
4. Order book y CVD actuales son proxies, no equivalen al OFI academico.
5. Zonas, activacion, barrida, grado y confianza son formulas internas.
6. Los frenos v0.10/v0.11 son la unica modificacion derivada del aprendizaje y
   siguen siendo evidencia interna provisional.
7. `tp_probability` es una suma heuristica acotada, no una probabilidad
   calibrada de TP antes que SL.

## 4. Caso 872/873

Queda documentado como incoherencia prioritaria:

```text
SHORT, precio >= entrada -> +3 puntos
SHORT, precio < entrada  -> -2 puntos
```

El salto de cinco puntos puede invertir la ordenacion de dos planes aunque uno
tenga TP mas lejano. E1.3 debe reproducirlo como prueba de discontinuidad y
definir la correccion candidata sin alterar todavia produccion.

## 5. Fuentes externas revisadas

- Documentacion oficial Binance USD-M Futures.
- Documentacion oficial CoinGecko.
- Metodologia y API Alternative.me.
- Wilder (1978) para RSI y ATR.
- CFA Institute para medias y osciladores.
- Brock, Lakonishok y LeBaron para reglas tecnicas simples.
- Lo, Mamaysky y Wang para formalizacion estadistica de patrones.
- Osler para soporte/resistencia intradia.
- Cont, Kukanov y Stoikov para order-flow imbalance.
- Tsinaslanidis, Guijarro y Voukelatos para Fibonacci.
- Brier; Gneiting y Raftery; Dimitriadis, Gneiting y Jordan para probabilidad y
  calibracion.

Cada referencia y su limite esta registrada en
`matriz_fuentes_y_teorias.md` y en la matriz JSON.

## 6. Artefactos

- `audit_rule_provenance.py`
- `tests/test_audit_rule_provenance.py`
- `auditorias_motor/catalogo_reglas_motor.md`
- `auditorias_motor/matriz_fuentes_y_teorias.md`
- `auditorias_motor/matriz_procedencia_funciones_v0_1.json`
- `auditorias_motor/2026-07-24_E1_2_procedencia_fundamento_resultado.md`

## 7. Verificacion

```text
python -m unittest discover -s tests -p "test_*.py"
Ran 65 tests
OK
```

Se regenero la matriz dos veces y mantuvo el mismo SHA-256. `git diff --check`
no detecto errores de whitespace.

## 8. Limites

- E1.2 clasifica procedencia; no prueba aun monotonicidad ni impacto.
- Una regla `empirica_provisional` no esta autorizada para produccion nueva.
- Una transformacion `fundamentada` no implica poder predictivo.
- No se ha cambiado el champion, scoring, API ni interfaz.

## 9. Siguiente fase

E1.3 - Coherencia matematica y semantica:

1. Invariantes TP/SL y horizonte.
2. Monotonicidad de alcanzabilidad.
3. Discontinuidades de umbrales.
4. Doble conteo.
5. Unidades y escalas.
6. Caps, saturacion y zonas muertas.
7. Separacion entre direccion, alcanzabilidad, ejecucion, riesgo y EV.
