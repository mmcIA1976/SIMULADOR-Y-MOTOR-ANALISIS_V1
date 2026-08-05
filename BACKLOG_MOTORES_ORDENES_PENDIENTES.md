# Backlog de motores para ordenes pendientes

## Alcance aplazado expresamente

| Direccion | Intencion | Tipo interno | Estado |
|---|---|---|---|
| LONG | Entrar cuando el precio suba | `stop_breakout` | No cubierto; motor futuro |
| SHORT | Entrar cuando el precio baje | `stop_breakdown` | No cubierto; motor futuro |

Estas dos posibilidades no pertenecen al contrato LIMIT de retroceso. Exigen un
contrato de continuacion o ruptura que mida, entre otras cosas, calidad de la
ruptura, expansion de volumen, aceptacion sobre/bajo el nivel, riesgo de falsa
ruptura y cambio de liquidez antes y despues del disparo.

No se implementaran degradandolas a `limit_pullback`, porque eso mezclaria dos
preguntas diferentes:

- LIMIT: probabilidad de retroceder hasta una zona y reaccionar desde ella;
- STOP: probabilidad de romper un nivel, sostener la ruptura y continuar.

La fase futura debera reutilizar el ciclo de snapshots compacto, pero tendra su
propio espacio probabilistico, reglas y validacion historica.
