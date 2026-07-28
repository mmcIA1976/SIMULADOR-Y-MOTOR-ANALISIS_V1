# M6.6 - Cierre de integracion probabilistica

Fecha: 2026-07-28
Estado: M6 COMPLETADA POR ORDEN DEL PROPIETARIO

## Resultado

- Baseline de primera barrera doble implementado.
- Tres outcomes coherentes: TP, SL y expiry.
- Riesgos competitivos discretos implementados.
- Formulas registradas: 8.
- Reglas M5 clasificadas: 27/27.
- Casos de malla verificados: 125.
- Caso 872/873: ordenacion geometrica corregida.
- Pruebas especificas M6 superadas: 62.
- Suite completa superada: 478.

## Evidencia tecnica

La infraestructura admite coeficientes estimados, pero el artefacto
actual esta bloqueado. Por tanto, las doce covariables candidatas no
alteran aun las probabilidades y la salida coincide con el baseline.

## Trazabilidad

Cada salida interna expone geometria, sigma, horizonte, formulas,
hashes M5, hazards, incidencia acumulada, masa, supuestos, limites
y estado de incertidumbre.

## Limites

- Puntos, bonus, penalizaciones o pesos manuales: NINGUNO.
- Coeficientes activos: 0.
- Calibracion empirica: NO.
- Validez predictiva o rentabilidad: NO DEMOSTRADAS.
- Produccion modificada: NO.
- M7 y M8 siguen siendo obligatorias.

## Estado de fases

- M6 cerrada: SI.
- M7 iniciada: NO.
- M7 requiere una orden expresa separada.

SHA-256 del payload canonico: `f2c042bf0be339f7c9358f65918efc7b7f293c5c0218c0e1e1cb3076f1370875`.
