# M4.7 - Comparacion A/B y decision de cambios

Fecha: 2026-07-27

Estado: COMPARACION Y PROPUESTA DE ENMIENDAS; CAMBIOS AUN NO APLICADOS

## 1. Objetivo y limites

Este documento:

- compara las revisiones A y B por primera vez;
- conserva la procedencia exacta de cada observacion;
- elimina duplicados sin borrar la autoria A o B;
- determina que cambios corrigen un fallo o mejoran M4;
- separa cambios claros de decisiones que requieren definicion del propietario;
- no modifica aun las fichas, formulas, catalogos ni produccion;
- no cierra M4 ni inicia M5.

Documentos fuente:

- A:
  `auditorias_motor/2026-07-27_M4_7_evaluacion_revision_A.md`;
- B:
  `auditorias_motor/2026-07-27_M4_7_evaluacion_revision_B.md`.

Regla de decision:

```text
implementar solo si:
    corrige una formula, contrato, metadato o comportamiento incorrecto
    OR
    mejora trazabilidad, reproducibilidad o separacion semantica

no implementar si:
    duplica una proteccion ya completa
    OR
    contradice M2/M3
    OR
    mezcla probabilidad de mercado con ejecucion o riesgo de cuenta
    OR
    introduce una politica empirica sin validacion previa
```

## 2. Resultado ejecutivo

La comparacion produce:

- 15 paquetes unificados de cambio;
- 7 paquetes claros que pueden implementarse sin inventar semantica;
- 5 paquetes necesarios que requieren antes decisiones explicitas;
- 3 paquetes de cierre, prueba o migracion que dependen de los anteriores;
- 5 observaciones ya satisfechas que no requieren una nueva regla;
- 7 propuestas o interpretaciones que se rechazan;
- 6 trabajos que se difieren a mantenimiento, M5, M7 o M8.

No se mantiene el cierre propuesto sobre exactamente 27 fichas. Si se aprueban
las cuatro fichas nuevas de B, el conteo y el DAG deben regenerarse al final.
Tampoco se presupone que todas las fichas sean evidencia P0: el suavizador
exponencial ya esta excluido por su propio contrato.

## 3. Solapamientos A/B

| Grupo unificado | Procedencia A | Procedencia B | Resolucion sin duplicar |
|---|---|---|---|
| Trazas y calidad | A-R1 | B6, calidad de valores, ATI/OI | Un solo esquema de traza con campos producidos, campos prohibidos y procedencia/calidad por valor. |
| Politicas numericas | A-R2, A-R5 | B regla 1, B regla 16 | Un solo registro de decisiones para `24`, `60`, `H/2H/4H` y `2000 ms`, sin llamarlos optimos publicados. |
| Cross-venue | A-R5 | B regla 16 | Conservar el bloqueo actual, renombrar la captura y registrar incertidumbre; no crear dos reglas. |
| ATI | A-R6 | B regla 13 | La limitacion ATI/OFI ya existe; solo ampliar identidad, unidad, cobertura y metodo de la fuente. |
| Versionado e integridad | A-R7 | B7 y renombrados B | Una sola convencion de versionado, migracion de IDs y hashes con alcance declarado. |
| Invariantes | Puente A hacia M5 | Correcciones y nuevas fichas B | Una sola matriz `invariante -> prueba de referencia -> futura prueba productiva`. |
| Fees y separacion | A-R4 | B regla 22 | Mantener basis separado de fees y corregir la condicion de exactitud de comisiones. |

No existe solapamiento sustancial entre:

- el DAG de A y las nuevas semanticas de B;
- el inventario de hipotesis de A y el payoff de expiry de B;
- la clasificacion de fuentes de B y la politica de idioma de A.

Son piezas complementarias, no recomendaciones duplicadas.

## 4. Matriz maestra de cambios

### `AB-CHG-001` - Rama plana de estructura

- Procedencia: B1.
- Decision: IMPLEMENTAR.
- Motivo: corrige una formula formal incompleta.
- Cambio:
  - declarar `E_W=0`, `SE_W=0`, `flat_path=true` cuando `TV_W=0`;
  - mantener el operador actual, que ya produce ese resultado;
  - ampliar la prueba para exigir tambien `path_efficiency=0`.
- Riesgo de regresion: bajo.
- Requiere decision del propietario: no.

### `AB-CHG-002` - VWAP y coste de fill parcial

- Procedencia: B2.
- Decision: IMPLEMENTAR.
- Motivo: corrige el denominador de la formula publicada.
- Cambio:
  - definir `VWAP_filled=sum(p_i*q_i)/Q_fill`;
  - distinguir cantidad solicitada, ejecutada y no ejecutada;
  - exponer coste del tramo ejecutado cuando el fill es parcial;
  - reservar coste completo de la orden para `fill_ratio=1`;
  - no llamar al coste parcial implementation shortfall completo.
- Riesgo de regresion: medio, por cambio de trazas y nombres.
- Requiere decision del propietario: no.

### `AB-CHG-003` - Correcciones de metadatos y nombres

- Procedencia: B reglas 5, 7, 17 y 18.
- Decision: IMPLEMENTAR CON MIGRACION VERSIONADA.
- Motivo: elimina nombres o metadatos que exageran el significado real.
- Cambio:
  - renombrar reachability geometrica como normalized barrier geometry;
  - declarar el suavizador exponencial como operador auxiliar;
  - corregir el proveedor mark-index a Binance USD-M;
  - renombrar funding horario como normalizacion lineal;
  - conservar alias y mapa de IDs anteriores para trazabilidad.
- Riesgo de regresion: medio, por referencias cruzadas.
- Requiere decision del propietario: no para el contenido; si para aceptar los
  nuevos IDs definitivos.

### `AB-CHG-004` - Versionado, hashes y manifiesto

- Procedencia: A-R7 y B7.
- Decision: IMPLEMENTAR.
- Motivo: mejora reproducibilidad e impide confundir digest canonico con hash
  de archivo.
- Cambio:
  - distinguir cambio editorial, correccion y cambio semantico;
  - publicar `canonical_payload_sha256`;
  - declarar serializacion canonica;
  - publicar hashes de archivos en un manifiesto externo;
  - probar reproduccion de todos los digests;
  - versionar cualquier cambio de formula o significado.
- Riesgo de regresion: bajo.
- Requiere decision del propietario: no.

### `AB-CHG-005` - Esquema unico de trazas y calidad

- Procedencia: A-R1 y B6.
- Decision: IMPLEMENTAR.
- Motivo: evita que campos `null` parezcan salidas calculadas y evita llamar
  exactos a valores estimados.
- Cambio:
  - separar `produced_trace_fields`;
  - separar `forbidden_or_reserved_null_fields`;
  - asignar procedencia/calidad por valor:
    `observed_exact`, `deterministic_from_plan`, `estimated_model`,
    `scenario_point`, `scenario_lower_bound`, `scenario_upper_bound`,
    `unavailable`, `not_applicable`;
  - exigir que M6 use una traza de modelo distinta;
  - probar que los nueve campos predictivos prohibidos siguen nulos.
- Riesgo de regresion: medio, por cambio transversal de contrato.
- Requiere decision del propietario: no.

### `AB-CHG-006` - Clasificacion de fuentes y trazas ATI/OI

- Procedencia: B evaluacion de fuentes, B reglas 13, 14 y 17; A-R6 como
  comprobacion ya satisfecha.
- Decision: IMPLEMENTAR.
- Motivo: mejora la fuerza de las afirmaciones y hace verificable la ventana
  real usada.
- Cambio:
  - clasificar fuentes como semantica de proveedor, definicion matematica,
    evidencia empirica directa, evidencia adyacente o contrato interno;
  - anadir a ATI fuente, unidad, cobertura, metodo y retencion;
  - anadir a OI timestamps, separacion real y error de alineacion;
  - bloquear OI no alineado; no interpolar silenciosamente;
  - mantener que ATI no es OFI/CVD y que fuentes ATI no se suman ni promedian.
- Riesgo de regresion: medio.
- Requiere decision del propietario: no, mientras se exija alineacion exacta;
  cualquier futura tolerancia si requerira decision previa.

### `AB-CHG-007` - Registro unico de politicas numericas

- Procedencia: A-R2, A-R5, B regla 1 y B regla 16.
- Decision: IMPLEMENTAR SIN CAMBIAR TODAVIA LOS VALORES.
- Motivo: mejora auditabilidad sin fingir optimalidad ni elegir parametros
  despues de ver resultados.
- Politicas:
  - minimo de 24 retornos;
  - referencia de 60 ventanas;
  - jerarquia H, 2H y 4H;
  - maximo de 2000 ms entre recepciones cross-venue.
- Cambio:
  - registrar razon practica, compromiso, limitaciones y futura sensibilidad;
  - declarar `2000 ms` como limite provisional de recepcion, no sincronizacion;
  - renombrar la observacion cross-venue;
  - registrar incertidumbre de captura;
  - prohibir reajustes despues de abrir el conjunto de prueba.
- Riesgo de regresion: bajo.
- Requiere decision del propietario: aprobar que los valores se conservan como
  politica provisional hasta M7/M8.

### `AB-CHG-008` - Contrato completo de orden y fill

- Procedencia: B3 y ficha nueva `ORDER-FILL-STATE`.
- Decision: IMPLEMENTAR, DESPUES DE DEFINIR SEMANTICA DE PRODUCTO.
- Motivo: la distancia al trigger no demuestra ejecucion.
- Cambio:
  - recibir tipo exacto de orden y `timeInForce`;
  - separar touch, trigger, activacion, fill parcial y fill completo;
  - usar estados terminales mutuamente excluyentes a `expiry_at`;
  - conservar tiempos y cantidades de cada fill;
  - mantener el vencimiento absoluto de M2;
  - integrar sobre tiempos/cantidades de fill en M6.
- Riesgo de regresion: alto, porque cambia el arbol de outcomes.
- Requiere decision del propietario: si; ver decisiones P1 y P2.

### `AB-CHG-009` - First passage y proceso de precios

- Procedencia: B4 y ficha nueva `FIRST-PASSAGE-LABEL`.
- Decision: IMPLEMENTAR, DESPUES DE DEFINIR REFERENCIAS DE PRECIO.
- Motivo: completa una obligacion M2 que aun no esta materializada en M4.
- Cambio:
  - declarar proceso de precio de entrada, TP y SL;
  - declarar tipos de orden y proteccion;
  - usar datos ordenados de resolucion suficiente;
  - marcar ambiguedad o censura sin forzar TP/SL;
  - medir frecuencia de ambiguedad;
  - separar `INDEX_PRICE` analitico de `workingType` USD-M.
- Riesgo de regresion: alto.
- Requiere decision del propietario: si; ver decisiones P1 y P2.

### `AB-CHG-010` - Factibilidad de liquidacion

- Procedencia: B5 y ficha nueva `LIQUIDATION-FEASIBILITY`.
- Decision: IMPLEMENTAR PARA PAYOFF Y AUTORIZACION APALANCADA.
- Motivo: un SL posterior a la liquidacion no representa una rama ejecutable.
- Cambio:
  - producir `before_stop`, `after_or_equal_stop`, `unknown` o
    `not_applicable`;
  - separar escenario aislado, posicion real aislada y margen cruzado;
  - bloquear payoff apalancado y autorizacion cuando sea desconocido;
  - conservar probabilidades fisicas de barrera separadas del riesgo de cuenta;
  - usar brackets y datos de cuenta solo cuando existan y sean aplicables.
- Riesgo de regresion: alto.
- Requiere decision del propietario: si; ver decision P3.

### `AB-CHG-011` - Payoff de expiry y significado del EV

- Procedencia: B6 y ficha nueva `EXPIRY-PAYOFF`.
- Decision: IMPLEMENTAR, DESPUES DE DEFINIR LA SALIDA EN EXPIRY.
- Motivo: el precio terminal no se conoce pre-trade.
- Cambio:
  - representar `E[Y_expiry | no barrier before expiry]` o su distribucion;
  - prohibir payoff puntual arbitrario;
  - conservar la identidad algebraica del EV;
  - etiquetar probabilidades y costes futuros como estimados o escenarios;
  - prohibir llamar exacto al EV pre-trade completo.
- Riesgo de regresion: alto.
- Requiere decision del propietario: si; ver decision P4.

### `AB-CHG-012` - Separacion basis, fees y comisiones

- Procedencia: A-R4 y B regla 22.
- Decision: IMPLEMENTAR LA ACLARACION Y LA CORRECCION DE FEE.
- Motivo: mejora la separacion entre mercado y economia de ejecucion.
- Cambio:
  - basis y mark-index siguen siendo contexto de mercado;
  - fees, slippage y funding siguen siendo costes por outcome;
  - no se crea basis neto de fees;
  - una fee pre-trade se etiqueta como escenario;
  - una fee realizada exige notional ejecutado, tasa/importe, rol y activo.
- Riesgo de regresion: bajo.
- Requiere decision del propietario: no.

### `AB-CHG-013` - DAG final de reglas y familias

- Procedencia: A-R3.
- Decision: IMPLEMENTAR AL FINAL DE LAS ENMIENDAS SEMANTICAS.
- Motivo: mejora trazabilidad y prueba que no hay ciclos ni doble conteo.
- Cambio:
  - incluir todas las fichas finales, no congelarse en 27;
  - marcar reglas atomicas, derivadas, contenedores y auxiliares;
  - probar aciclicidad;
  - probar una sola ruta canonica por familia de evidencia;
  - regenerar slots y relaciones M4.6.
- Riesgo de regresion: medio.
- Requiere decision del propietario: no, una vez cerrado el conjunto de fichas.

### `AB-CHG-014` - Inventarios, invariantes y puerta futura

- Procedencia: puente A hacia M5 y pruebas exigidas por B.
- Decision: IMPLEMENTAR COMO CIERRE M4.
- Motivo: mejora la capacidad de verificar posteriormente que produccion
  implementa exactamente las fichas.
- Cambio:
  - consolidar inventario de hipotesis y ficha origen;
  - construir matriz de invariantes y pruebas M4/M5;
  - registrar un ID estable para la futura puerta de promocion M8;
  - no fijar ahora umbrales empiricos;
  - regenerar el paquete de revision del propietario.
- Riesgo de regresion: bajo.
- Requiere decision del propietario: no para los artefactos; el cierre final
  sigue requiriendo aprobacion expresa.

### `AB-CHG-015` - Correccion productiva de doble toque ambiguo

- Procedencia: hallazgo B4 confirmado durante el contraste.
- Decision: IMPLEMENTAR DESPUES DE APROBAR `AB-CHG-009`.
- Motivo: corrige una contradiccion real entre M2 y produccion.
- Cambio:
  - eliminar el fallback que fuerza `stop_loss` si TP y SL aparecen en la misma
    vela y no pueden ordenarse;
  - resolver con trades o menor resolucion cuando exista cobertura;
  - en ausencia de orden temporal, registrar `ambiguous`;
  - no usar el caso ambiguo como TP o SL observado;
  - anadir pruebas de regresion del simulador y del aprendizaje.
- Riesgo de regresion: alto, porque cambia cierres/reconstrucciones.
- Requiere decision del propietario: aprobar primero la semantica exacta de
  first passage y su efecto sobre operaciones abiertas.

## 5. Cambios claros y cambios condicionados

### Implementables sin nueva decision semantica

1. `AB-CHG-001`: rama plana.
2. `AB-CHG-002`: VWAP parcial.
3. `AB-CHG-004`: versionado y hashes.
4. `AB-CHG-005`: trazas y calidad.
5. `AB-CHG-006`: fuentes y trazas ATI/OI.
6. `AB-CHG-012`: basis y fees.
7. parte no nominal de `AB-CHG-003`: proveedor, funding y clasificacion
   auxiliar.

Tambien puede prepararse `AB-CHG-007`, conservando los valores actuales como
politicas provisionales y sin afirmar que sean optimos.

### Necesarios pero condicionados

1. `AB-CHG-008`: orden y fill.
2. `AB-CHG-009`: first passage y referencias de precio.
3. `AB-CHG-010`: liquidacion.
4. `AB-CHG-011`: payoff de expiry.
5. `AB-CHG-015`: correccion productiva de ambiguedad.

### Dependientes del conjunto final

1. `AB-CHG-003`: IDs finales y conteo.
2. `AB-CHG-013`: DAG final.
3. `AB-CHG-014`: paquete final de revision y pruebas de puente.

## 6. Decisiones del propietario antes de cambios condicionados

### P1. Tipos de entrada admitidos

Problema:

- `market|pending` no distingue LIMIT, STOP_MARKET o STOP_LIMIT;
- no puede modelarse fill real sin esa distincion.

Recomendacion:

- mantener `MARKET`;
- distinguir al menos `LIMIT` y `STOP_MARKET`;
- admitir `STOP_LIMIT` solo si se modelan trigger y orden limite posterior;
- registrar `timeInForce`;
- no inferir el tipo a partir del lado y del precio.

Estado: PENDIENTE DE DECISION.

### P2. Referencia de precio de entrada, TP y SL

Problema:

- el motor actual usa implicitamente precio de contrato;
- Binance permite `MARK_PRICE` o `CONTRACT_PRICE` para triggers condicionales;
- datos historicos antiguos no guardan esa eleccion.

Recomendacion:

- exigir referencia explicita en analisis nuevos;
- mantener los historicos como `legacy_price_reference_unknown` salvo evidencia;
- no reconstruir mark triggers con velas de contrato;
- tratar `INDEX_PRICE` solo como referencia analitica separada.

Estado: PENDIENTE DE DECISION.

### P3. Semantica de liquidacion sin cuenta conectada

Problema:

- la app es simulador y no dispone siempre del estado completo de cuenta;
- margen cruzado depende de posiciones y balances simultaneos.

Recomendacion:

- calcular solo un escenario aislado cuando el plan declare margen aislado y
  existan brackets suficientes;
- etiquetar margen cruzado o modo desconocido como `unknown`;
- no bloquear las probabilidades fisicas TP/SL;
- bloquear decision y payoff apalancado completo cuando liquidacion sea
  desconocida.

Estado: PENDIENTE DE DECISION.

### P4. Cierre de la rama expiry

Problema:

- expiry no contiene hoy una orden ni un precio de ejecucion definidos.

Recomendacion:

- definir primero el payoff como variable condicional;
- para una futura simulacion, declarar proceso de precio y tipo de cierre;
- incluir costes de salida como estimacion, no valor observado;
- no fijar `entry`, `close` o midpoint como precio terminal por comodidad.

Estado: PENDIENTE DE DECISION.

## 7. Observaciones ya satisfechas

No se crean cambios duplicados para:

1. A-R6: ATI ya esta declarado distinto de OFI y CVD.
2. B3: M2 ya fija vencimiento absoluto y prohibe reiniciar H.
3. B4: M2 ya define ambiguedad y censura; falta implementacion completa, no
   una segunda politica contradictoria.
4. B regla 11: M4.6 ya conserva el vector MTF continuo y no usa el descriptor
   de signos como score.
5. B regla 1: el operador actual solo admite intervalos de segundos fijos entre
   `1m` y `1d`; no existe un intervalo mensual variable `1M` que retirar.

En estos puntos solo se reforzaran trazas o pruebas dentro de los paquetes
unificados correspondientes.

## 8. Propuestas rechazadas

1. Crear un `basis neto de fees`.
   Motivo: mezcla contexto de mercado con economia de una estrategia distinta.
2. Reiniciar H cuando se ejecuta una entrada pendiente.
   Motivo: contradice `M2-INV-CLOCK-01`.
3. Tratar `INDEX_PRICE` como `workingType` de Binance USD-M.
   Motivo: el proveedor documenta `MARK_PRICE` y `CONTRACT_PRICE`.
4. Sustituir ahora la politica de intervalo por una tabla par/horizonte.
   Motivo: introduciria elecciones no validadas y riesgo de sobreajuste.
5. Considerar WebSocket una solucion suficiente de sincronizacion.
   Motivo: Spot `bookTicker` no aporta por si solo timestamp de evento.
6. Forzar TP o SL cuando el orden temporal sea desconocido.
   Motivo: crea etiquetas retrospectivas falsas.
7. Bloquear las probabilidades fisicas de mercado porque falte riesgo de cuenta.
   Motivo: liquidacion bloquea payoff/decision apalancada, no la geometria
   fisica de las barreras.

## 9. Trabajos diferidos

1. Elegir frecuencia de muestreo optima o por par: M7/M8, con protocolo previo.
2. Sustituir REST por arquitectura WebSocket: M5, despues del contrato de datos.
3. Elegir un skew cross-venue mas estricto: M7/M8, con medicion de latencia e
   incertidumbre.
4. Fijar umbrales de promocion de hipotesis: M8, no M4.
5. Asignar pesos, puntos o probabilidades: M6/M8; el motor de aprendizaje sigue
   fuera de este trabajo.
6. Normalizar el idioma de todos los documentos: mantenimiento posterior a los
   cambios semanticos; no justifica reescritura masiva durante M4.7.

## 10. Orden de implementacion propuesto

### Ola 1 - Correcciones deterministas

1. `AB-CHG-001`.
2. `AB-CHG-002`.
3. `AB-CHG-004`.
4. correcciones no controvertidas de `AB-CHG-003`.

Criterio de salida:

- formulas corregidas;
- hashes reproducibles;
- alias/versiones conservados;
- pruebas M4 completas.

### Ola 2 - Trazabilidad y fuentes

1. `AB-CHG-005`.
2. `AB-CHG-006`.
3. `AB-CHG-007`.
4. `AB-CHG-012`.

Criterio de salida:

- cada valor tiene procedencia y calidad;
- politicas visibles como provisionales;
- ATI/OI reproducibles;
- mercado, ejecucion y cuenta siguen separados.

### Ola 3 - Semantica operable

Solo despues de resolver P1-P4:

1. `AB-CHG-008`.
2. `AB-CHG-009`.
3. `AB-CHG-010`.
4. `AB-CHG-011`.

Criterio de salida:

- arbol de outcomes exhaustivo y sin solapamientos;
- referencias de precio explicitas;
- liquidacion y expiry no se fingen;
- ninguna rama desconocida se transforma en dato neutral.

### Ola 4 - Integracion y correccion productiva

1. `AB-CHG-013`.
2. `AB-CHG-014`.
3. `AB-CHG-015`.

Criterio de salida:

- DAG aciclico del conjunto final;
- pruebas de invariantes completas;
- fallback ambiguo corregido;
- paquete del propietario regenerado;
- M4 permanece abierta hasta aprobacion expresa.

## 11. Decision final de esta comparacion

Se recomienda implementar los 15 paquetes porque cada uno corrige un defecto
confirmado o mejora de forma concreta la trazabilidad, reproducibilidad o
semantica del motor.

La recomendacion no equivale a aplicar todos inmediatamente:

- los cambios claros pueden comenzar por la Ola 1;
- P1-P4 deben resolverse antes de la Ola 3;
- la correccion productiva depende de la ficha first-passage aprobada;
- no se adoptan propuestas rechazadas o diferidas;
- no se modifica el motor de aprendizaje;
- no se asignan probabilidades, pesos o scores.

## 12. Estado

- Revisiones A y B preservadas de forma independiente: SI.
- Comparacion A/B realizada: SI.
- Duplicados consolidados con procedencia: SI.
- Cambios decididos conceptualmente: SI.
- Cambios aplicados al catalogo: NO.
- Produccion modificada: NO.
- Conteo final de fichas decidido: NO.
- M4 cerrada: NO.
- M5 iniciada: NO.
