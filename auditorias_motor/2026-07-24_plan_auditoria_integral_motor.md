# Plan extraordinario - Auditoria integral del motor de analisis

Fecha de apertura: 2026-07-24
Estado: ACTIVO
Motor congelado: `rules-v0.12.1-liquidations-readable`
Scoring congelado: `scoring-v0.11-underweighted-risk-cluster`
Commit de partida: `ac16ccdd1d2a71bd5214ab3bcc8151e44adb8350`

## 0. Contrato rector

Desde el 2026-07-24, cualquier conclusion, correccion o challenger de esta
auditoria debe cumplir `CONTRATO_FASE_1_MOTOR_ANALISIS.md`.

`COBERTURA_ANALITICA_FASE_1.md` registra los 34 bloques de analisis objetivo,
su prioridad y el estado real de los datos. Enumerar un bloque no autoriza su
incorporacion: cada variable y regla debe superar individualmente el contrato.

## 1. Motivo

Los analisis 872 y 873 demostraron que una regla binaria de timing podia
alterar cinco puntos la salida llamada `tp_probability`, aunque el segundo TP
estuviera mas lejos. La salida actual es un score heuristico y no una
probabilidad calibrada de tocar TP antes que SL dentro del horizonte.

La Fase 5 del plan de aprendizaje queda pausada. Antes de continuar se debe
conocer, justificar y validar todo el motor de analisis.

## 2. Objetivo

Construir una especificacion exhaustiva y verificable de:

- Datos de entrada, fuente, antiguedad, unidad y disponibilidad.
- Indicadores y transformaciones.
- Reglas, formulas, pesos, umbrales, caps y dependencias.
- Resultados intermedios y salida final.
- Procedencia historica de cada regla.
- Teoria financiera o tecnica que pretende respaldarla.
- Evidencia empirica propia disponible.
- Riesgos, duplicidades, discontinuidades y supuestos no demostrados.

Ninguna regla se considerara respaldada solo porque exista en el codigo o sea
habitual en trading.

## 3. Pregunta probabilistica objetivo

El futuro motor debe mostrar como resultados principales:

`P(TP antes que SL dentro del horizonte | informacion pre-trade)`

`P(SL antes que TP dentro del horizonte | informacion pre-trade)`

La expiracion sin tocar ninguna barrera debe modelarse internamente para no
falsear esos dos porcentajes y debe quedar registrada en el outcome posterior.

La distribucion interna de resultados mutuamente excluyentes debe ser
matematicamente coherente. Los dos porcentajes principales deben identificar
la version del modelo y declarar su incertidumbre y calibracion.

## 4. Clasificacion obligatoria de reglas

Cada regla recibira:

- Identificador estable.
- Archivo y lineas ejecutables.
- Formula exacta.
- Variables y unidades.
- Fuente de datos.
- Horizonte y temporalidades.
- Efecto maximo sobre cada salida.
- Interacciones con otras reglas.
- Origen historico dentro del proyecto.
- Fundamento externo y referencia.
- Evidencia interna y numero de casos.
- Estado: `fundamentada`, `heuristica`, `empirica_provisional`,
  `duplicada`, `incoherente`, `sin_respaldo` o `retirada`.
- Decision propuesta: mantener, reformular, calibrar, aislar o eliminar.

## 5. Subfases

### E1.1 - Inventario ejecutable

Estado: COMPLETADA

- Extraer funciones, constantes, formulas, umbrales y dependencias.
- Generar huellas SHA-256 de cada modulo.
- Reconciliar codigo, especificacion e historial.
- Identificar todas las rutas desde datos hasta recomendacion.

Criterio de salida:

- El inventario mecanico cubre todos los modulos declarados.
- Cada funcion del alcance tiene archivo, lineas y huella.
- Los conteos son reproducibles mediante un comando versionado.

### E1.2 - Procedencia y fundamento

Estado: COMPLETADA

- Vincular cada regla a teoria y fuentes primarias o manuales reconocidos.
- Distinguir definiciones estandar de interpretaciones discutibles.
- Marcar reglas internas sin fuente demostrable.

Criterio de salida:

- Ninguna regla queda sin una procedencia explicita o la marca `sin_respaldo`.

Resultado:

- Catalogo humano de datos, indicadores, scoring, riesgo, decision y aprendizaje.
- Matriz reproducible de 185/185 funciones con procedencia, estado y fuentes.
- Se preservan 1.528 apariciones numericas y 3.317 fragmentos de formula.
- Ningun peso exacto del score direccional queda presentado como validado
  externamente.
- La salida `tp_probability` queda dictaminada como score heuristico no
  calibrado; su incoherencia matematica se probara formalmente en E1.3.

Artefactos:

- `catalogo_reglas_motor.md`
- `matriz_fuentes_y_teorias.md`
- `matriz_procedencia_funciones_v0_1.json`
- `audit_rule_provenance.py`

### E1.3 - Coherencia matematica y semantica

Estado: COMPLETADA

- Auditar monotonicidad, continuidad, unidades, doble conteo y caps.
- Separar score direccional, alcanzabilidad y calidad de ejecucion.
- Verificar invariantes TP, SL, horizonte, volatilidad y costes.

Criterio de salida:

- Cada incoherencia tiene reproduccion, severidad y correccion candidata.

Resultado:

- 12 invariantes matematicos y semanticos versionados.
- 17 hallazgos: 16 fallos demostrados y 1 validez universal no demostrada.
- 7 hallazgos criticos, 9 altos y 1 medio.
- Casos end-to-end sinteticos prueban insensibilidad a distancia TP/SL y el
  salto exacto de cinco puntos al cruzar entrada/precio.
- Quedan reproducidos la masa total de 1.01, funding sin signo, costes sin
  duracion, intervalos no estadisticos, ausencia de bloqueo por falta de datos,
  dobles conteos y trazabilidad incompleta.
- El champion y las salidas de produccion permanecen sin cambios.

Artefactos:

- `invariantes_coherencia_motor_v0_1.json`
- `coherencia_motor_v0_1.json`
- `informe_coherencia_motor.md`
- `audit_engine_coherence.py`
- `tests/test_engine_coherence_audit.py`

### E1.4 - Impacto historico

Estado: COMPLETADA

- Reejecutar reglas sobre snapshots preservados.
- Medir contribucion a probabilidad, grado, EV y decision.
- Calcular cuantos casos cambian al retirar o reformular cada regla.

Criterio de salida:

- Impacto cuantificado sin sobrescribir recomendaciones historicas.

Resultado:

- 875 recomendaciones inventariadas y separadas por version.
- 86 snapshots del engine congelado reproducidos de forma exacta.
- Paridad 86/86 para TP, SL, rango, grado, riesgo y decision.
- 29 contribuciones directas y 3 grupos compuestos auditados por ablation.
- Impacto cuantificado sobre probabilidad, EV, grado y decision.
- 789 recomendaciones de motores anteriores excluidas del replay actual.
- Solo 20 outcomes completos y 7 casos ETH: no existe muestra suficiente para
  autorizar cambios de reglas ni afirmar validez entre pares.
- Ninguna recomendacion historica ni fila de produccion fue modificada.

Artefactos:

- `audit_historical_rule_impact.py`
- `e1_4_export_query.sql`
- `cobertura_historica_e1_4_v0_1.json`
- `impacto_historico_reglas_v0_1.json`
- `informe_impacto_historico_reglas.md`
- `tests/test_historical_rule_impact.py`

### E1.5 - Contrato del challenger

Estado: SIGUIENTE - NO INICIADA

- Definir arquitectura interpretable de alcanzabilidad.
- Crear challenger en sombra.
- Especificar calibracion, validacion temporal, kill switch y reversion.

Criterio de salida:

- El challenger no altera produccion y puede compararse caso a caso.

## 6. Reglas de seguridad

- El champion permanece congelado.
- No se cambian probabilidades, decisiones, TP, SL o grados durante E1.1-E1.4.
- Los analisis historicos no se sobrescriben.
- Toda reinterpretacion se guarda append-only y con version.
- No se presenta precision probabilistica sin calibracion demostrada.
- La activacion de un challenger requiere aprobacion humana explicita.

## 7. Artefactos previstos

- `inventario_reglas_motor_v0_1.json`
- `catalogo_reglas_motor.md`
- `matriz_fuentes_y_teorias.md`
- `informe_coherencia_motor.md`
- `impacto_historico_reglas.json`
- `contrato_challenger_alcanzabilidad.md`

## 8. Comando reproducible

```powershell
.\.venv\Scripts\python.exe audit_scoring_rules.py `
  --output auditorias_motor\inventario_reglas_motor_v0_1.json

.\.venv\Scripts\python.exe audit_engine_coherence.py
```

## 9. Estado de cierre

La auditoria extraordinaria no puede cerrarse hasta completar E1.1-E1.5.
La Fase 5 original permanece pausada.
