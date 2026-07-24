# E1.1 - Inventario ejecutable del motor

Fecha: 2026-07-24
Estado: COMPLETADA LOCALMENTE; PENDIENTE DE PUBLICACION
Commit de entrada: `ac16ccdd1d2a71bd5214ab3bcc8151e44adb8350`
Motor congelado: `rules-v0.12.1-liquidations-readable`
Scoring congelado: `scoring-v0.11-underweighted-risk-cluster`

## 1. Objetivo

Crear un inventario reproducible de las funciones, constantes, formulas,
umbrales, comparaciones y dependencias que participan en:

- Obtencion de datos.
- Construccion de indicadores.
- Analisis y scoring.
- Liquidaciones.
- Evidencia historica.
- Metricas economicas.
- Etiquetas y reglas del aprendizaje.
- Validacion del plan y creacion de recomendaciones.

No se ha modificado ninguna regla del motor.

## 2. Artefactos

- `audit_scoring_rules.py`: extractor AST versionado.
- `inventario_reglas_motor_v0_1.json`: inventario mecanico.
- `tests/test_audit_scoring_rules.py`: pruebas de cobertura y huellas.
- `2026-07-24_plan_auditoria_integral_motor.md`: plan extraordinario.

Comando:

```powershell
.\.venv\Scripts\python.exe audit_scoring_rules.py `
  --output auditorias_motor\inventario_reglas_motor_v0_1.json
```

## 3. Cobertura

| Modulo | Funciones | Constantes | Literales numericos | Fragmentos |
|---|---:|---:|---:|---:|
| `analysis_engine.py` | 64 | 2 | 1027 | 1580 |
| `data_engine.py` | 28 | 3 | 183 | 322 |
| `market_data.py` | 26 | 21 | 29 | 163 |
| `liquidation_data.py` | 8 | 5 | 43 | 159 |
| `learning_evidence.py` | 18 | 4 | 33 | 260 |
| `economic_metrics.py` | 12 | 1 | 34 | 123 |
| `versioning.py` | 4 | 10 | 0 | 10 |
| `app.py`, funciones de reglas seleccionadas | 25 | 17 | 179 | 700 |
| **Total** | **185** | **63** | **1528** | **3317** |

Un literal numerico no equivale necesariamente a una regla independiente.
El inventario conserva cada aparicion para impedir que un umbral quede oculto.
E1.2 consolidara estas apariciones en reglas semanticas con identificadores
estables.

## 4. Reproducibilidad

- Huella SHA-256 del inventario:
  `C4A37A95B709F15C1285E3C5E7187B483A8D471DC19D2FD6E2B80C60A0C5FA47`.
- Tamano: 1.536.448 bytes.
- Dos ejecuciones independientes produjeron la misma huella.
- Cada modulo incluye su propia huella SHA-256 y numero de lineas.
- El inventario guarda archivo, funcion, lineas, llamadas, expresiones y
  literales numericos.

## 5. Ruta ejecutable reconciliada

La ruta principal es:

1. `market_data.py` consulta proveedores.
2. `data_engine.py` transforma respuestas en indicadores y snapshot.
3. `analysis_engine.py` convierte indicadores en biases, penalizaciones,
   score, EV, grado, confianza y decision.
4. `app.py` valida el plan, persiste la recomendacion y enlaza la operacion.
5. `learning_evidence.py` reconstruye el recorrido posterior.
6. `economic_metrics.py` normaliza el resultado por riesgo.
7. Las funciones de aprendizaje de `app.py` crean etiquetas, conclusiones,
   patrones e informes.

## 6. Estado de la documentacion previa

`ESPECIFICACION_MOTOR_ANALISIS.md`:

- Describe la intencion funcional.
- No enumera todas las formulas y umbrales ejecutables.
- Llama probabilidad a una salida cuya calibracion no esta demostrada.

`FUENTES_DATOS_Y_ANALISIS.md`:

- Identifica proveedores y limitaciones generales.
- No demuestra que cada transformacion o peso sea financieramente valido.

`HISTORIAL_CAMBIOS_MOTOR_ANALISIS.md`:

- Conserva motivos y cambios historicos.
- No ofrece una referencia teorica individual para cada regla.

Conclusion: la documentacion existente aporta trazabilidad historica, pero no
constituye todavia el manual tecnico y financiero exhaustivo solicitado.

## 7. Hallazgos iniciales

- La salida `tp_probability` parte de 0,50 y suma/resta heuristicas.
- La regla `price_vs_entry_bias` introduce un salto discontinuo de cinco
  puntos alrededor de la entrada.
- La distancia exacta al TP se usa en R/R, EV y algunas barreras, pero no como
  componente monotono suficiente de alcanzabilidad.
- El mapa de liquidaciones actual es observacional y no afecta al scoring.
- Existen muchos umbrales y caps de origen interno cuya teoria y evidencia
  deben clasificarse individualmente en E1.2.
- La precision decimal visible supera la precision empirica demostrada.

Estos hallazgos no modifican el motor; abren pruebas obligatorias para E1.3.

## 8. Pruebas

- Compilacion del extractor: correcta.
- Suite completa: 61/61.
- Cobertura de los ocho modulos: comprobada.
- Presencia de funciones criticas: comprobada.
- Huellas contra fuentes actuales: comprobadas.
- Repeticion determinista: comprobada.

## 9. Criterios de salida

| Criterio | Resultado |
|---|---|
| Modulos declarados inventariados | Cumplido |
| Analisis, datos y aprendizaje cubiertos | Cumplido |
| Archivo, lineas y huella por modulo | Cumplido |
| Formulas y umbrales extraibles | Cumplido |
| Comando reproducible | Cumplido |
| Scoring sin cambios | Cumplido |
| Publicacion y despliegue | Pendiente |

## 10. Siguiente subfase

E1.2 - Procedencia y fundamento.

Cada regla semantica se vinculara a:

- Definicion exacta.
- Origen dentro del proyecto.
- Fuente de datos.
- Teoria o manual externo.
- Evidencia propia.
- Nivel de respaldo.
- Decision propuesta.
