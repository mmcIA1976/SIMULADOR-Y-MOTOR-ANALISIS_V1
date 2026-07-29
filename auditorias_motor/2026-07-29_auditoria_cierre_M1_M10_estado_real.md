# Auditoria de cierre M1-M10: estado real del motor

Fecha: 2026-07-29

Commit auditado: `3e4f392736ed3307cfe262ccdb78086036db9d3e`

Motor servido: `TP-SL-PROBABILITY-ENGINE-v0.4`

## 1. Criterio de esta auditoria

Una fase no se considera resuelta solo porque exista un documento de cierre.
Se distinguen cuatro estados:

1. documentada;
2. implementada;
3. verificada sobre la misma version;
4. activa en produccion conforme a la puerta prevista.

El contrato rector sigue siendo `CONTRATO_FASE_1_MOTOR_ANALISIS.md`. En
particular, siguen vigentes estas prohibiciones:

- no inventar umbrales o pesos por parecer razonables;
- no llamar probabilidad a un score no calibrado;
- ninguna regla sin ficha completa puede afectar al resultado;
- una prueba de software no equivale a validacion financiera;
- una fuente oficial de datos no respalda por si sola un peso predictivo.

## 2. Veredicto general

El trabajo M1-M8 produjo una base util y material:

- inventario y retirada conceptual del scoring antiguo;
- semantica TP/SL/expiry;
- 27 reglas con formulas deterministas y traza;
- baseline de primera barrera;
- reparacion de masa de riesgos competitivos;
- un nucleo estadistico con tres familias ajustadas;
- snapshots preoperacion con horizonte y corte temporal exactos;
- atribucion individual por regla.

Sin embargo, el motor actualmente servido no ha completado la secuencia
M6-M9 exigida por la hoja de ruta:

- ocho contribuciones activas usan pesos provisionales no estimados;
- la version actual es posterior al cierre M7;
- M8 termino rechazando el candidato y no se repitio sobre la version actual;
- M9 fue ejecutada como activacion directa, pero no fue cerrada con sus
  controles de gradualidad, kill switch y rollback;
- M10 no se ha iniciado.

Por ello, la version actual es funcional y trazable, pero no puede
considerarse todavia un motor probabilistico completamente validado.

## 3. Estado exacto por fase

| Fase | Estado real | Conclusion |
|---|---|---|
| M0 | cerrada y valida | La hoja de ruta y el contrato existen. |
| M1 | cerrada y valida | El motor antiguo quedo inventariado y clasificado. |
| M1-A | cerrada y valida | Existe el catalogo exacto de 86 elementos antiguos. |
| M2 | cerrada como fundamento | La semantica TP/SL/expiry, geometria e invariantes siguen siendo validas. |
| M3 | cerrada documentalmente; cumplimiento productivo parcial | Los contratos P0 existen, pero la auditoria del pipeline esta desactualizada y faltan metadatos de calidad por llamada en parte del contexto vivo. |
| M4 | cerrada y valida como catalogo | Existen 27 reglas formales. M4 no autorizo los ocho pesos provisionales posteriores. |
| M5 | implementada; cierre de la version actual pendiente | El runtime ejecuta y traza 27 reglas, pero los hashes de cierre ya no se comparan con el codigo actual. |
| M6 | parcialmente resuelta; reabierta por v0.4 | El nucleo matematico esta reparado. La capa de ocho pesos provisionales no satisface el contrato de M6. |
| M7 | cerrada solo para una version anterior | No verifica la integracion viva ni la capa de once reglas activa. Debe repetirse sobre la version candidata definitiva. |
| M8 | proceso cerrado con rechazo | La decision formal fue `return_to_earlier_phase`; no aprobo produccion ni desbloqueo M9. No se ha repetido sobre v0.4. |
| M9 | activada de hecho, no cerrada conforme al plan | Produccion sirve el motor nuevo, pero no existe cierre M9, activacion gradual, kill switch del motor servido ni rollback probado. |
| M10 | no iniciada | Fibonacci, liquidaciones y las restantes expansiones P1/P2/P3 siguen fuera del nucleo activo. |

## 4. M5 y las 27 reglas en produccion

La ultima recomendacion auditada (`#913`) contiene las 27 reglas:

- 22 `evaluated`;
- 3 `blocked`;
- 1 `deferred`;
- 1 `not_applicable`;
- 0 errores.

Distribucion funcional:

- 5 reglas alimentan geometria y volatilidad del baseline;
- 1 regla limita la entrada a MARKET;
- 1 suavizador no se aplica por falta de alfa aprobada;
- 3 reglas tienen coeficientes ajustados;
- 8 reglas tienen pesos provisionales;
- 1 regla es un contenedor complementario sin doble conteo;
- 8 reglas pertenecen a ejecucion, costes y economia.

En la capa economica de esa recomendacion:

- comisiones: bloqueadas;
- cashflow de funding: diferido;
- payoffs netos: bloqueados;
- valor esperado: bloqueado.

Esto no impide calcular la probabilidad fisica de TP/SL, pero impide afirmar
que el plan tiene rentabilidad neta completa.

## 5. Defecto principal pendiente en M6

Las tres familias ajustadas son:

- extremo previo entre entrada y TP;
- percentil de volatilidad;
- jerarquia multitemporal 2H/4H.

Las ocho contribuciones provisionales son:

| Regla | Peso actual |
|---|---:|
| estructura del recorrido H | 0.12 |
| regimen continuo | 0.08 |
| desequilibrio taker | 0.12 |
| actividad de open interest | 0.06 |
| relacion precio/OI | 0.10 |
| basis spot/futuros | 0.06 |
| prima mark/index | 0.06 |
| funding | 0.08 |

Estos pesos aparecen por primera vez en `m6_predictive_rules.py` y en el
documento de activacion v0.4. No tienen derivacion teorica, estimacion
estadistica ni validacion temporal independiente registrada.

Ademas, `directional_path_efficiency_h` fue retirada del candidato v0.2 porque
su ablation era desfavorable. La capa v0.4 la reintrodujo como `Path
structure` con peso 0.12. La auditoria historica v0.4 vuelve a situarla entre
las contribuciones negativas.

La capa provisional conserva masa uno y genera trazas correctas. Eso prueba
coherencia de software, no correccion de sus pesos.

## 6. Por que M7 no esta cerrada para el motor actual

El cierre M7 verifico:

- 12/12 frentes;
- 972 celdas de cobertura;
- 175 casos matematicos;
- 71 pruebas especificas;
- 552 pruebas totales.

Ese trabajo sigue siendo valido para las formulas y modulos congelados que
audito. No cubre el motor servido actual porque despues se incorporaron:

- `m6_remediated_competing_risks.py`;
- `m6_remediation_engine.py`;
- `m5_live_inputs.py`;
- `m5_input_assembly.py`;
- `m6_predictive_rules.py`;
- `m6_production_analysis.py`;
- la nueva ruta activa de `prospective_validation.py`.

Las pruebas de cierre M5-M7 fueron modificadas tras la activacion para dejar
de exigir que los hashes guardados coincidan con los archivos actuales. Los
builders devuelven el paquete historico cuando detectan el documento de
activacion. Esto conserva el cierre antiguo, pero impide usar un test verde
como prueba de que el motor actual coincide con aquel cierre.

La suite actual de 623 pruebas pasa. Aun asi, las pruebas M7 independientes
siguen dirigidas principalmente a los modulos anteriores y no constituyen un
nuevo cierre M7 de v0.4.

## 7. Resultado real de M8

M8 se completo administrativamente, pero su resultado fue un rechazo:

- decision: `return_to_earlier_phase`;
- motivo inicial: defecto de masa del hazard discreto;
- registros historicos sin horizonte exacto: 200;
- registros finales retrospectivos: 21;
- registros finales formalmente validos: 1;
- M9 no desbloqueada.

El defecto de masa fue reparado posteriormente. No se realizo una nueva M8
formal con una cohorte temporal posterior.

La auditoria historica local v0.4 reconstruyo 237 operaciones y obtuvo:

| Variante | Brier | Log-loss | Acierto principal |
|---|---:|---:|---:|
| motor antiguo | 0.660784 | 1.129288 | 43.88% |
| nucleo nuevo, 3 reglas | 0.482142 | 0.769423 | 63.71% |
| hasta 7 reglas exactas | 0.482423 | 0.769166 | 62.87% |
| hasta 10 reglas aproximadas | 0.488813 | 0.775675 | 62.87% |

Conclusion:

- el nucleo de tres reglas mejora claramente al motor antiguo en esa
  reconstruccion;
- las capas provisionales no mejoran el nucleo en conjunto;
- la repeticion exacta de las once reglas no es posible con el historico;
- 236 de 237 casos usan horizonte reconstruido;
- el informe y su script siguen locales, sin commit;
- esta evidencia es diagnostica y no sustituye una M8 temporal independiente.

Cobertura historica:

- desarrollo/calibracion: 180 casos, cinco pares, ningun horizonte exacto;
- prueba final abierta: 21 casos, solo BTC y ETH, un horizonte exacto;
- BNB no aparece en desarrollo/calibracion;
- no existe validacion empirica suficiente para afirmar igualdad de calidad en
  los seis pares.

## 8. Evidencia prospectiva existente

En base de datos hay 14 recomendaciones del motor v0.4 anterior al cambio de
nombre:

- 3 vinculadas a operaciones cerradas: 2 TP y 1 SL;
- 5 vinculadas a operaciones abiertas;
- 6 analisis sin operacion iniciada.

Los 14 snapshots guardan:

- `analysis_at`;
- `data_cutoff_at`;
- horizonte exacto;
- once reglas activas;
- probabilidades y contribuciones.

Esto es util para una futura evaluacion. Todavia no es una muestra suficiente.

La tabla formal `m6_prospective_runs` contiene 0 registros. Tampoco existe un
evaluador operativo que, al vencer el horizonte, etiquete automaticamente
cada analisis no ejecutado como TP primero, SL primero o ninguna barrera.
Por tanto, se estan guardando snapshots aprovechables, pero no se esta
completando el protocolo prospectivo definido antes de M9.

## 9. Estado real de M9

Cumplido:

- el motor antiguo ya no calcula analisis nuevos;
- cada recomendacion guarda versiones y trazas;
- produccion sirve el commit esperado;
- endpoints principales y salida visible han sido comprobados;
- no existe fallback silencioso al motor antiguo.

No cumplido:

- M8 nunca desbloqueo M9;
- no hay paquete de inicio o cierre M9;
- la activacion no fue gradual;
- no existe un kill switch para el motor que sirve `/api/analyze`;
- el kill switch existente pertenece al antiguo carril prospectivo sin efecto;
- no existe rollback productivo probado;
- no hay criterio formal de incidencia y reversión;
- no hay aprobacion posterior basada en una M8 valida.

M9 esta, por tanto, activa de hecho pero no concluida metodologicamente.

## 10. Fibonacci

Lo que existe:

- calculo interno desde velas Binance USD-M;
- pivotes de 3 velas a cada lado;
- seleccion automatica de swing;
- retrocesos y extensiones;
- disponibilidad viva comprobada en 5m, 15m, 1h, 4h, 1d y 1w.

Lo que no esta resuelto:

- el selector de swing y sus umbrales son heuristicos;
- el score antiguo de Fibonacci usa puntos y umbrales manuales;
- la evidencia documentada es mixta y no respalda esos pesos;
- M4 lo excluyo de P0 y lo envio a M10;
- el motor activo fija `availability.fibonacci = false`;
- Fibonacci no modifica actualmente TP, SL ni expiry.

No debe reconectarse el score antiguo. En M10 debe definirse una variable
reproducible, una hipotesis concreta y una prueba incremental independiente.

## 11. Mapa de liquidaciones

Lo que existe:

- proveedor gratuito HyperPerps;
- origen subyacente limitado a posiciones publicas de Hyperliquid;
- clusters long y short, masa por distancia, apalancamiento y OI agregado;
- controles de antiguedad y diferencia entre precio de referencia y mercado;
- cobertura de BTC, ETH y SOL.

Comprobacion viva del 2026-07-29:

- endpoint del snapshot: 200;
- estado: disponible;
- antiguedad: 153.3 segundos;
- muestra declarada: 2383;
- 10 clusters por encima y 10 por debajo.

Lo que no esta resuelto:

- no cubre Binance ni otros exchanges;
- no cubre BNB, XRP ni INJ;
- no existe validacion sistematica contra mapas visuales independientes;
- no existe archivo historico inmutable para reconstruir cada mapa;
- representa liquidaciones estimadas desde posiciones Hyperliquid, no un mapa
  agregado del mercado;
- el motor activo fija `availability.liquidation_heatmap = false`;
- no modifica actualmente TP, SL ni expiry.

Liquidaciones pertenecen a M10/P1. Deben entrar exchange por exchange y
repetir M3-M9 antes de recibir peso.

## 12. Otros pendientes relevantes

- El README y la tabla de estado de la hoja de ruta estan desactualizados.
- La auditoria automatica M3 sigue inspeccionando en gran parte el pipeline
  antiguo y no audita correctamente todo `m5_live_inputs`.
- Faltan metadatos por llamada para distinguir error de proveedor, ausencia y
  fallback en todas las fuentes vivas.
- Comisiones, payoffs netos y EV siguen bloqueados.
- No hay cierre automatico por vencimiento del horizonte.
- No hay evaluacion automatica al vencer recomendaciones sin operacion.
- El motor de aprendizaje registra atribuciones, pero no debe cambiar pesos
  automaticamente antes de cerrar M6-M9 sobre la version definitiva.
- Los datos complementarios de sentimiento, breadth, long/short y otros
  bloques antiguos no participan en el motor activo.

## 13. Orden exacto para concluir el cambio

1. Actualizar la hoja de ruta y separar cierre historico de estado actual.
2. Reabrir M6 solo para resolver los ocho pesos provisionales.
3. Decidir con evidencia si se desactivan, se estiman o se retiran; no
   mantenerlos como pesos manuales permanentes.
4. Congelar una unica version candidata con formulas, datos y artefactos.
5. Repetir M7 completo contra esa misma version, incluyendo pipeline vivo,
   overlay, todos los pares y los tres horizontes.
6. Reparar la recogida prospectiva y el etiquetado automatico al vencer cada
   analisis, sin crear operaciones ficticias.
7. Repetir M8 con una cohorte temporal posterior e independiente.
8. Formalizar M9 con kill switch, rollback, comprobacion online y cierre.
9. Iniciar M10 incorporando Fibonacci y liquidaciones como dos lineas
   separadas; cada una debe repetir M3-M9.

Hasta completar los puntos 2-8, la prioridad no debe desviarse hacia mas
indicadores ni hacia aprendizaje automatico de pesos.
