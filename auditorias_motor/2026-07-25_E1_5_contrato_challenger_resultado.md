# Resultado E1.5 - Contrato del challenger

Fecha de cierre: 2026-07-25
Decision: COMPLETADA
Champion: `rules-v0.12.1-liquidations-readable`
Scoring: `scoring-v0.11-underweighted-risk-cluster`
Challenger: `challenger-v0.1-contract-only`
Commit de implementacion y cierre: `8066f24`

## 1. Objetivo alcanzado

E1.5 convierte la auditoria anterior en un limite ejecutable para el futuro
motor. Define que puede calcularse, que puede investigarse y que pruebas debe
superar una regla antes de influir en TP o SL.

El champion permanece congelado. No se han cambiado sus probabilidades,
decisiones, TP, SL, grados ni textos.

## 2. Matriz de admisibilidad

Resultado reproducible:

- 86 reglas exactas.
- 69 reglas predictivas o decisionales actuales.
- 29 aportaciones directas E1.4 cubiertas.
- 19 gates de calibracion cubiertos.
- 36 funciones predictivas/decisionales E1.2 cubiertas.
- 7 definiciones de datos permitidas como datos.
- 6 transformaciones calculables sin inferencia predictiva.
- 4 hipotesis reservadas para investigacion.
- 68 formulas, gates o implementaciones actuales bloqueadas.
- 0 reglas predictivas con validacion temporal independiente.
- 0 reglas predictivas autorizadas para produccion.

SHA-256 de la matriz:

`a59cb1e2b941e2ae989a402e6a1ed8b6aaad75f3a50ea730f50241675837e2b2`

La matriz prueba expresamente que una API oficial o una formula tecnica
reconocida no respaldan por si mismas un threshold, un peso o una probabilidad.

## 3. Contrato probabilistico

El challenger modela:

- `tp_first`;
- `sl_first`;
- `expiry_unresolved`.

Las tres probabilidades forman una distribucion coherente. Los dos porcentajes
principales son TP y SL antes de la otra barrera y dentro de una duracion
concreta. La expiracion no se oculta ni se reparte artificialmente.

Se fijan:

- tiempo cero pre-trade;
- geometria long/short;
- distancias logaritmicas simetricas;
- horizonte concreto dentro de los tres marcos actuales;
- tratamiento de orden no activada;
- ambiguedad y censura;
- bloqueo por dato ausente, degradado u obsoleto;
- trazabilidad completa de cada contribucion.

## 4. Arquitectura

El primer baseline investigable es multinomial, lineal e interpretable. Cada
probabilidad puede reconstruirse desde:

- variable cruda;
- centrado y escala;
- coeficiente;
- contribucion al logit;
- intercepto;
- calibracion;
- softmax final.

No hereda ningun bias, penalty, gate, cap o threshold del champion.

## 5. Estado ejecutable

`challenger_engine.py` implementa:

- validacion del plan y sus barreras;
- transformaciones deterministas del plan;
- contrato del artefacto;
- comprobacion de SHA de admisibilidad;
- control de par y horizonte validados;
- variables obligatorias de distancia TP, distancia SL y duracion;
- invariantes monotonicos que impiden repetir el fallo 872/873;
- bloqueo de interacciones ocultas con el plan;
- bloqueo por leakage temporal;
- control de fuente, calidad y frescura;
- masa probabilistica igual a uno;
- traza por outcome;
- comparacion separada con el champion;
- kill switch;
- seleccion reversible de version.

No esta importado por `app.py`, no escribe en base de datos y no afecta a la
aplicacion local ni online.

## 6. Por que no hay porcentajes challenger todavia

No existe un artefacto entrenado, calibrado y aprobado. E1.4 solo encontro 20
outcomes completos y 7 casos ETH. No permiten entrenar, calibrar, reservar un
test independiente y demostrar validez entre pares y horizontes.

Por contrato, la respuesta actual es:

```text
status = blocked
block_code = model_artifact_absent
probabilities = null
```

Esto evita repetir el error del champion: convertir puntos internos en
porcentajes aparentes.

## 7. Protocolo de validacion

Queda preregistrado:

- train, calibracion y test en orden cronologico;
- rolling origin dentro de train;
- log-loss y Brier multiclase como metricas primarias;
- reliability/CORP e intervalos por bloques temporales;
- ablation atomica y de interacciones;
- resultados separados por BTCUSDT, ETHUSDT, SOLUSDT y horizonte;
- minimos de gobernanza de 50 casos comparables y 10 TP/10 SL;
- promocion humana, kill switch y rollback;
- conservacion de resultados negativos.

Superar los minimos permite evaluar; no demuestra validez.

## 8. Verificacion

Comandos:

```powershell
.\.venv\Scripts\python.exe audit_rule_admissibility.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Resultado:

- matriz generada de forma determinista;
- cobertura completa sin reglas omitidas;
- 113/113 pruebas superadas;
- champion sin cambios;
- sin escritura ni despliegue funcional del challenger.

## 9. Artefactos

- `audit_rule_admissibility.py`
- `matriz_admisibilidad_reglas_v0_1.json`
- `informe_admisibilidad_reglas.md`
- `contrato_challenger_alcanzabilidad.md`
- `protocolo_validacion_challenger.md`
- `challenger_engine.py`
- `tests/test_rule_admissibility.py`
- `tests/test_challenger_engine.py`

## 10. Siguiente fase

La auditoria extraordinaria E1 queda cerrada. La siguiente fase del plan
auditable es:

`Fase 5 - Reevaluacion legacy append-only`

Objetivo: aplicar la taxonomia moderna a las evaluaciones antiguas sin
sobrescribir su interpretacion original ni inventar features ausentes.

Estado: desbloqueada, no iniciada. Requiere aprobacion expresa del usuario.
