# Plan extraordinario - Auditoria integral del motor de analisis

Fecha de apertura: 2026-07-24
Estado: ACTIVO
Motor congelado: `rules-v0.12.1-liquidations-readable`
Scoring congelado: `scoring-v0.11-underweighted-risk-cluster`
Commit de partida: `ac16ccdd1d2a71bd5214ab3bcc8151e44adb8350`

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

El futuro motor debe estimar por separado:

`P(TP antes que SL dentro del horizonte | informacion pre-trade)`

`P(SL antes que TP dentro del horizonte | informacion pre-trade)`

`P(ninguno dentro del horizonte | informacion pre-trade)`

Las tres salidas deben sumar uno, identificar la version del modelo y declarar
su incertidumbre y calibracion.

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

Estado: COMPLETADA LOCALMENTE; PENDIENTE DE PUBLICACION

- Extraer funciones, constantes, formulas, umbrales y dependencias.
- Generar huellas SHA-256 de cada modulo.
- Reconciliar codigo, especificacion e historial.
- Identificar todas las rutas desde datos hasta recomendacion.

Criterio de salida:

- El inventario mecanico cubre todos los modulos declarados.
- Cada funcion del alcance tiene archivo, lineas y huella.
- Los conteos son reproducibles mediante un comando versionado.

### E1.2 - Procedencia y fundamento

Estado: PENDIENTE

- Vincular cada regla a teoria y fuentes primarias o manuales reconocidos.
- Distinguir definiciones estandar de interpretaciones discutibles.
- Marcar reglas internas sin fuente demostrable.

Criterio de salida:

- Ninguna regla queda sin una procedencia explicita o la marca `sin_respaldo`.

### E1.3 - Coherencia matematica y semantica

Estado: PENDIENTE

- Auditar monotonicidad, continuidad, unidades, doble conteo y caps.
- Separar score direccional, alcanzabilidad y calidad de ejecucion.
- Verificar invariantes TP, SL, horizonte, volatilidad y costes.

Criterio de salida:

- Cada incoherencia tiene reproduccion, severidad y correccion candidata.

### E1.4 - Impacto historico

Estado: PENDIENTE

- Reejecutar reglas sobre snapshots preservados.
- Medir contribucion a probabilidad, grado, EV y decision.
- Calcular cuantos casos cambian al retirar o reformular cada regla.

Criterio de salida:

- Impacto cuantificado sin sobrescribir recomendaciones historicas.

### E1.5 - Contrato del challenger

Estado: PENDIENTE

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
```

## 9. Estado de cierre

La auditoria extraordinaria no puede cerrarse hasta completar E1.1-E1.5.
La Fase 5 original permanece pausada.
