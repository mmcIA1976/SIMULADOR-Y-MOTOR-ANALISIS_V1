# M4.7 - Evaluacion de la revision externa A

Fecha: 2026-07-27

Estado: DICTAMEN DE CONTRASTE; NO MODIFICA LAS FICHAS M4

Documento evaluado:

- ruta: `C:\Users\MSI\Downloads\M4_recomendaciones_cierre_pre_M5.md`;
- SHA-256: `9B88DFBED7860BF1F6C9E84A4B78ECC0A3AC80940DB4DCF9302539C118AF2995`;
- catalogo auditado por el revisor:
  `474758f48c96a9b923332d94e10e70b91b4568b9d5ee6b05cfd32465d3092e53`;
- el SHA del catalogo citado coincide con la version M4.7 contrastada.

## 1. Dictamen general

La revision A es seria, esta basada en la version correcta y merece ser
considerada. Detecta tres carencias claras antes del cierre: contrato de
trazas, justificacion de parametros de politica y grafo completo de
dependencias. Tambien acierta en versionado y en varios artefactos de puente.

No debe aplicarse literalmente en todos sus puntos:

- la propuesta de netear basis con fees mezcla contexto de mercado con
  economia de ejecucion;
- el limite temporal cross-venue ya existe y esta probado, aunque no aparece
  con suficiente claridad dentro de la ficha;
- la limitacion de ATI ya esta declarada expresamente;
- varios campos predictivos criticados son `null` obligatorios y tienen
  pruebas, por lo que no existe hoy un efecto probabilistico oculto. Si existe
  un problema de contrato y legibilidad que conviene corregir.

## 2. Evaluacion R1-R8

| ID | Dictamen | Prioridad corregida | Motivo |
|---|---|---|---|
| R1 | ACEPTAR CON ALCANCE AMPLIADO | Alta | Existe incoherencia entre formulas no predictivas y nombres de traza. Los operadores actuales devuelven esos campos como `null`, por lo que no son probabilidades numericas activas. La revision solo cita 4 fichas, pero el barrido completo detecta 9. |
| R2 | ACEPTAR | Alta | `24`, `60` y `H/2H/4H` estan identificados como politica, pero no existe registro del criterio de eleccion. No debe inventarse retrospectivamente: requiere decision explicita y sensibilidad posterior. |
| R3 | ACEPTAR | Alta | M4.6 tiene slots y relaciones anti-duplicidad, pero no un DAG 27/27 con dependencias directas, dependientes y prueba de aciclicidad. |
| R4 | RECHAZAR LA FUSION; ACEPTAR UNA ACLARACION | Media | Basis es contexto de mercado. Fees pertenecen al payoff de la operacion del usuario. Un `basis neto` solo seria pertinente para una estrategia de arbitraje spot-perpetuo distinta. Debe documentarse esta separacion, no crear ahora una senal neta. |
| R5 | PARCIALMENTE SATISFECHA | Media editorial | Ya existe `cross_venue_max_skew_ms=2000`, bloqueo `cross_venue_capture_skew` y prueba de `capture_skew<=2000ms`. Conviene repetir el valor y el bloqueo en tiempo/activacion de la ficha y justificar los 2000 ms como politica. |
| R6 | YA SATISFECHA | Sin cambio | La ficha ya dice que `ATI_H` no es OFI ni CVD, que faltan ordenes limite y cancelaciones, y que un OFI real exige captura de eventos de libro y una ficha nueva. |
| R7 | ACEPTAR | Media de gobierno | Existe version `0.1`, sufijo `-001`, hashes y enmienda versionada, pero falta una convencion que distinga cambio semantico de correccion editorial. |
| R8 | ACEPTAR COMO HOUSEKEEPING | Baja | No cambia formulas. Se recomienda narrativa en espanol, identificadores/formulas/API en ingles y titulos de fuentes en idioma original. |

## 3. Alcance real de R1

Los campos que deben reclasificarse como salidas prohibidas o reservas
obligatoriamente nulas aparecen en:

1. `M4-RULE-BARRIER-REACHABILITY-001`: `probability`.
2. `M4-RULE-PENDING-ACTIVATION-001`: `activation_probability`.
3. `M4-RULE-PATH-STRUCTURE-001`: `prediction`.
4. `M4-RULE-VOLATILITY-RANK-001`: `regime_label`.
5. `M4-RULE-MTF-HIERARCHY-001`: `aggregate_score`,
   `probability_effect`.
6. `M4-RULE-CONTINUOUS-REGIME-001`: `regime_label`,
   `directional_score`, `probability_effect`.
7. `M4-RULE-AGGRESSOR-IMBALANCE-001`: `prediction`.
8. `M4-RULE-PRICE-OI-STATE-001`: `positioning_label`,
   `probability_effect`.
9. `M4-RULE-DERIVATIVES-CONTEXT-001`: `crowding_label`,
   `aggregate_score`, `probability_effect`.

Resolucion recomendada:

- separar `trace_output` en `produced_trace_fields` y
  `forbidden_or_reserved_null_fields`;
- mantener una prueba que exija `null` para toda salida prohibida;
- M6 debera emitir su probabilidad en una traza de modelo distinta, no
  rellenar silenciosamente la traza del operador M4.

## 4. Parametros de politica

Antes del cierre deben existir registros separados para:

- minimo de 24 retornos por H;
- referencia de 60 ventanas anteriores;
- jerarquia H, 2H y 4H;
- desfase cross-venue maximo de 2000 ms.

Cada registro debe distinguir:

- razon practica propuesta;
- coste o compromiso aceptado;
- ausencia de optimalidad publicada;
- analisis de sensibilidad que M7/M8 debera realizar;
- prohibicion de reajustarlo despues de observar el conjunto de prueba.

No se considera valido crear ahora una historia retrospectiva sobre por que se
eligio cada numero. La justificacion debe aprobarse como politica provisional.

## 5. Basis y fees

Contrato correcto:

- `basis` y `mark-index premium`: variables de contexto de mercado;
- `fees`, slippage y funding cash flow: costes por outcome;
- `net_payoff_k`: punto de encuentro economico;
- ninguna fee modifica la probabilidad de mercado;
- no se crea `basis neto de fees` para el motor direccional P0.

Una futura estrategia de arbitraje spot-perpetuo requeriria plan, dos patas,
roles de liquidez, fills y payoffs propios, por lo que no puede introducirse
como una nota ambigua en estas fichas.

## 6. Puente hacia M5

### Inventario de hipotesis

Dictamen: ACEPTAR.

M4.7 contiene las 15 hipotesis y su enlace desde cada regla, pero falta una
tabla unica orientada al propietario con:

- ID;
- estado;
- ficha origen;
- variables;
- combinacion;
- restriccion matematica o hipotesis empirica;
- fase de prueba.

### Invariantes automatizados

Dictamen: PARCIALMENTE SATISFECHO Y AMPLIAR.

La revision no reconoce que ya existen 146 pruebas M4 para simetria,
monotonicidad, escalado, signos, masa, datos ausentes y doble conteo. Aun falta
una matriz `invariante -> prueba actual -> futura prueba M5`. Los tests de M4
validan operadores de referencia; M5 debera repetirlos contra la
implementacion real.

### Puerta de promocion

Dictamen: ACEPTAR CON LIMITE DE FASE.

M4 no debe inventar ahora umbrales empiricos. Si debe registrar un
identificador estable, por ejemplo `M8-HYPOTHESIS-PROMOTION-GATE-001`, y
establecer que:

- M5 no promociona hipotesis;
- M6 integra candidatos sin declarar validacion;
- M7 verifica matematicas y software;
- M8 fija previamente metricas, cortes y umbrales, y decide promocion,
  rechazo o retorno de fase.

## 7. Enmiendas candidatas acumuladas de A

No aplicar hasta contrastar la revision B:

1. sanear las trazas de 9 reglas, conservando campos prohibidos como `null`;
2. crear cuatro registros de decision para parametros de politica;
3. construir y probar el DAG de 27 reglas;
4. declarar expresamente la separacion basis-fees;
5. hacer visible el limite cross-venue de 2000 ms en la ficha;
6. documentar versionado semantico y editorial;
7. fijar la politica de idioma;
8. consolidar el inventario de 15 hipotesis;
9. crear la matriz de invariantes y pruebas M4/M5;
10. registrar el identificador de la futura puerta M8.

## 8. Estado

- Revision A evaluada: SI.
- Recomendaciones aplicadas: NO.
- M4 cerrada: NO.
- M5 iniciada: NO.
- Siguiente accion: recibir y contrastar la revision B antes de decidir las
  enmiendas.
