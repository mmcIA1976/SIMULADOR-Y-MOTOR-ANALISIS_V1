# M7.1 - Contrato de verificacion independiente

Fecha: 2026-07-28
Estado: M7 INICIADA; M7.1 COMPLETADA

## Objetivo

Intentar refutar M6 antes de medir rendimiento empirico.

## Alcance obligatorio

1. Casos limite de entrada, TP, SL y horizonte (M7.2).
2. Simetria long/short (M7.2).
3. Monotonicidad y continuidad (M7.2).
4. Masa probabilistica (M7.2).
5. Datos ausentes, obsoletos, parciales o contradictorios (M7.3).
6. Cobertura de todos los pares soportados (M7.4).
7. Cobertura de los tres marcos (M7.4).
8. Doble conteo e interacciones (M7.4).
9. Reproducibilidad de traza y explicacion (M7.5).
10. Comparacion manual de una muestra de analisis (M7.5).
11. Rendimiento, latencia y tolerancia a fallos (M7.6).
12. Revision independiente del codigo y formulas (M7.7).

## Cobertura congelada

- Pares: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, INJUSDT.
- Marcos: intraday_short, intraday_wide, short_swing.
- Lados: long, short.
- Celdas par-marco-lado: 36.
- Celdas maximas par-marco-lado-regla: 972.

## Independencia

- Los oraculos no pueden llamar al solver M6.
- Los casos manuales se recalcularan fuera de M6.
- Las propiedades no copiaran salidas esperadas de M6.
- Cada formula se contrastara con su fuente primaria.
- Todo fallo se registrara antes de corregirse.

## Cierre

- Cero fallos criticos abiertos.
- Toda limitacion restante declarada.
- Produccion intacta.
- Aprobacion expresa del propietario.

## Limites

- M7 no calibra probabilidades ni estima coeficientes.
- M7 no demuestra rentabilidad.
- M8 permanece bloqueada.
- Produccion no queda autorizada.

Siguiente subfase: M7.2.

SHA-256 del payload canonico: `d480cc514d195763945ec669776f8c6262a873a8721aff61c4b876e65d480460`.
