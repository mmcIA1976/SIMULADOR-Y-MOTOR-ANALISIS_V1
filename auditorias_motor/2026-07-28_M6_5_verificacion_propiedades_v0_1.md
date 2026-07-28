# M6.5 - Verificacion de propiedades

Fecha: 2026-07-28
Estado: VERIFICACION INTERNA COMPLETADA; M7 SIGUE PENDIENTE

## Caso historico 872/873

| Analisis | Entrada | TP | SL | Distancia TP log | Legacy P(TP) |
|---|---:|---:|---:|---:|---:|
| 872 | 63942.4 | 63200.0 | 65000.0 | 0.01167838 | 0.5389 |
| 873 | 63920.2 | 63115.0 | 65000.0 | 0.01267697 | 0.5889 |

El 872 tenia el TP mas cercano, pero el score antiguo le asigno
cinco puntos menos por cruzar la condicion binaria precio/entrada.

El baseline M6 asigna `P_TP(872) > P_TP(873)` en todos los
escenarios sigma de la malla. La malla es una prueba de
sensibilidad geometrica, no una reconstruccion de volatilidad
M5 ni una afirmacion probabilistica retrospectiva.

## Propiedades

- Casos de masa y limites: 125.
- Error maximo de masa: 0.000e+00.
- TP mas lejano nunca aumenta P(TP): SI.
- Delta maximo con perturbacion continua: 3.220e-07.
- Simetria, escala y monotonia temporal: cubiertas por pruebas.

## Limites

- Calibracion empirica: NO.
- Rentabilidad demostrada: NO.
- M7 o M8 sustituidas: NO.
- Produccion autorizada: NO.

SHA-256 del payload canonico: `a8d266fe62c708b247d5b6ac363ffbca815f7a6b48ce70258cf09e35e934102c`.
