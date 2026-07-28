# M4.7 - Resultado de enmiendas, olas 1 y 2

Fecha: 2026-07-27

Estado: OLAS 1 Y 2 COMPLETADAS; M4 SIGUE ABIERTA; M5 NO INICIADA

## 1. Alcance

Este resultado aplica solo los cambios no controvertidos aprobados para
`M4.7 Enmiendas`. Conserva todos los artefactos v0.1 como historia auditable y
publica una cadena v0.2 independiente. No modifica el motor productivo ni el
motor de aprendizaje.

## 2. Cambios aplicados

| Paquete | Resultado |
|---|---|
| `AB-CHG-001` | Rama plana definida como `E_W=0`, `SE_W=0` y `flat_path=true`. |
| `AB-CHG-002` | VWAP del fill usa `Q_fill`; cantidad no llenada y coste parcial quedan separados del coste completo. |
| `AB-CHG-003` | Geometria renombrada con migracion de ID; suavizador marcado auxiliar; proveedor mark-index y nombre del funding corregidos. |
| `AB-CHG-004` | Versiones v0.2, digest canonico con alcance declarado y manifiesto externo de archivos completos. |
| `AB-CHG-005` | Traza producida separada de campos reservados a null; taxonomia y contrato por valor registrados. |
| `AB-CHG-006` | Fuentes y afirmaciones clasificadas; ATI conserva fuente, unidad, cobertura, metodo y retencion; OI exige separacion temporal exacta. |
| `AB-CHG-007` | `24`, `60`, `H/2H/4H` y `2000 ms` registrados como politicas internas provisionales, no como optimos publicados. |
| `AB-CHG-012` | Basis y fees permanecen separados; una fee pre-trade es escenario y solo una ejecucion observada puede ser exacta. |

## 3. Correcciones adicionales detectadas

- Las ocho fichas M4.5 ahora usan version de regla `0.2`.
- Cada afirmacion de fuente M4.5 incluye su nivel de respaldo.
- Las 27 fichas se presentan como 26 reglas nucleares P0 y 1 operador
  auxiliar.
- Los nueve campos predictivos no autorizados quedan identificados como
  reservados a null.
- M6 debera registrar estimaciones de modelo en una traza distinta con modelo,
  version, snapshot de variables y calibracion.

## 4. Artefactos principales

- `catalogo_alcanzabilidad_m4_2_v0_2.json`
- `catalogo_regimen_estructura_mtf_m4_3_v0_2.json`
- `catalogo_contexto_derivados_m4_4_v0_2.json`
- `catalogo_ejecucion_riesgo_m4_5_v0_2.json`
- `catalogo_combinaciones_reconciliacion_m4_6_v0_2.json`
- `catalogo_27_reglas_formulas_m4_7_v0_2.json`
- `2026-07-27_M4_7_27_reglas_formulas_enmienda_v0_2.md`
- `manifiesto_integridad_m4_7_v0_2.json`

El manifiesto usa SHA-256 sobre los bytes UTF-8 completos del catalogo y del
informe. El catalogo conserva, aparte, `canonical_payload_sha256` para su
contrato semantico canonico.

## 5. Verificacion

- Suites M4.2, M4.3, M4.4, M4.5, M4.6 y M4.7: `125/125` pruebas superadas.
- Suite completa del proyecto tras la integracion final: `344/344` pruebas
  superadas.
- Generadores v0.2 reproducibles mediante `--check`.
- Reglas con probabilidad directa autorizada: `0`.
- Reglas con peso numerico autorizado: `0`.
- Reglas productivas autorizadas: `0`.
- Motor productivo modificado: no.

## 6. Frontera pendiente

No se aplican todavia `AB-CHG-008`, `AB-CHG-009`, `AB-CHG-010`,
`AB-CHG-011` ni `AB-CHG-015`. Las decisiones semanticas quedan asi:

- `P1`: RESUELTA; solo entradas `MARKET` en el alcance inmediato;
- `P2`: referencias de precio para entrada, TP y SL;
- `P3`: semantica de liquidacion sin cuenta completa;
- `P4`: cierre y payoff de la rama expiry.

El ID `M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002` queda propuesto en la cadena
v0.2 y sujeto a aceptacion final del propietario junto con el conjunto
definitivo de fichas.

## 7. Estado de fase

- `M4.7 Enmiendas`: EN CURSO.
- Olas 1 y 2: COMPLETADAS TECNICAMENTE.
- Ola 3: BLOQUEADA POR DECISIONES P2-P4.
- Ola 4: PENDIENTE DE LA OLA 3.
- M4 cerrada: NO.
- M5 iniciada: NO.
