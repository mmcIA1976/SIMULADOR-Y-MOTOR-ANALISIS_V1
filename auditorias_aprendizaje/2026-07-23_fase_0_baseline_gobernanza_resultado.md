# Fase 0 - Baseline y gobernanza

Fecha: 2026-07-23  
Estado: COMPLETADA  
Commit de entrada: `513524566103ec96d57fc48f4cd6d24feb395aa2`  
Commit de salida: commit documental de esta fase

## 1. Objetivo autorizado

- Congelar el scoring champion.
- Adoptar el plan auditable como contrato de ejecucion.
- Crear una plantilla comun de resultados.
- Reconciliar Git, pruebas, Supabase y servicio online.

## 2. Alcance ejecutado

Solo se modifico documentacion de auditoria. No se modificaron codigo de
aplicacion, esquema, datos, endpoints ni scoring.

## 3. Cambios realizados

### Archivos

- Plan maestro auditable.
- Plantilla reutilizable de cierre de fase.
- Este informe de baseline.

### Base de datos

Ningun cambio. Solo consultas de lectura.

### Endpoints e interfaz

Ningun cambio.

### Scoring

Ningun cambio. Champion congelado:
`rules-v0.12.1-liquidations-readable`.

## 4. Evidencias

### Git

- `HEAD` inicial:
  `513524566103ec96d57fc48f4cd6d24feb395aa2`.
- `origin/main` inicial:
  `513524566103ec96d57fc48f4cd6d24feb395aa2`.
- El arbol solo contenia el plan aun no versionado al iniciar el cierre.

### Pruebas

- Comando: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
- Resultado: 30 pruebas ejecutadas, 30 correctas.

### Base de datos

| Indicador | Valor |
|---|---:|
| Recomendaciones | 857 |
| Operaciones | 243 |
| Cerradas | 232 |
| Canceladas | 7 |
| Abiertas | 3 |
| Pendientes de entrada | 1 |
| Evaluaciones | 232 |
| Evaluaciones legacy | 190 |
| Evaluaciones modernas | 42 |
| Cerradas sin evaluacion | 0 |
| Evaluaciones duplicadas | 0 |
| Evaluaciones con menos de 5 ticks | 5 |
| Analisis v0.12 | 69 |
| Mapas de liquidaciones validos | 67 |
| Mapas rechazados por antiguedad | 2 |

### Produccion

- Portada Railway: HTTP 200.
- Precio BTC: HTTP 200.
- Fuente de precio: `binance_usdm_futures_ticker`.
- Precio no obsoleto en la comprobacion.

Limitacion: la aplicacion no expone actualmente el SHA del despliegue. Se
verifico que `origin/main` coincide con el commit inicial y que Railway esta
operativo, pero la igualdad exacta del binario desplegado no puede demostrarse
mediante un endpoint de version. Cualquier endpoint de version se valorara en
una fase tecnica posterior sin ampliar esta fase.

## 5. Metricas antes y despues

No aplica. La fase no cambia datos ni comportamiento.

## 6. Casos excluidos

Ninguno.

## 7. Riesgos y limitaciones

- No existe identificador de commit visible desde Railway.
- Cinco evaluaciones tienen menos de cinco ticks.
- Solo 42 evaluaciones utilizan la taxonomia moderna.
- El scoring permanece sin validacion temporal independiente.

Estos riesgos estan asignados a fases posteriores y no bloquean el cierre de
la fase 0.

## 8. Reversion

Eliminar los tres documentos de gobernanza. No existe reversion de codigo o
datos porque no fueron modificados.

## 9. Criterios de aceptacion

| Criterio | Resultado | Evidencia |
|---|---|---|
| Baseline reconciliado | Cumplido | Conteos incluidos en este informe |
| Plan aprobado | Cumplido | Aprobacion del usuario el 2026-07-23 |
| Plantilla creada | Cumplido | `PLANTILLA_RESULTADO_FASE.md` |
| Champion congelado | Cumplido | Version registrada sin cambios |
| Sin cambios funcionales | Cumplido | Diff limitado a documentacion |
| Pruebas verdes | Cumplido | 30/30 |
| Servicio online operativo | Cumplido | Portada y precio HTTP 200 |

## 10. Decision de cierre

Decision: COMPLETADA  
Siguiente fase desbloqueada: Fase 1 - Madurez de senales  
Aprobacion del usuario: pendiente de aceptar el cierre y autorizar fase 1

