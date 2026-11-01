# Estándar de entrada de bots · 28 de octubre de 2026

**Decisiones posteriores del usuario · 29/10:** inicio tras finalizar el concurso
de octubre, el 1/11/2026 00:00 UTC (01:00 Madrid). Capital inicial del nuevo concurso:
1000 USDT por bot. Máximo efectivo de 8 operaciones abiertas por bot; las pendientes
que reservan capital cuentan para no superar el máximo al activarse. Se permite
mantener operaciones después de 4 h/24 h/7 días: no se añade cierre por vencimiento del
análisis. Se conservan cadencias, límites diarios y controles de capital/riesgo.
El cierre mensual propio del concurso se mantiene como motivo separado de TP/SL.
Estas decisiones sustituyen los pendientes antiguos sobre número de posiciones
y cierre al vencer el horizonte. El motor completo disponible es v0.12-lab.4.
Su conexión con el escáner online sigue pendiente. El inicio se traslada desde
el 31 de octubre al concurso de noviembre; no hay una activación programada.

Estado del paquete al 1/11: **publicación online autorizada**, app `0.40.21`.
Lab.4 es la selección global por defecto; verificar versión y heartbeat tras
el despliegue. Este documento conserva las decisiones previas como antecedente.
Fuente de requisitos:
instrucción del usuario en este chat y confirmación «1» de que el 20% corresponde
a no alcanzar ni TP ni SL dentro del horizonte. No es una mejora predictiva validada.

**Decisión del usuario · 29/10/2026:** el motor que decidirá las entradas será
**el motor nuevo completo**, conservando el contrato temporal del motor anterior.
En aquella decisión, la candidata v0.12-lab.2 era una corrección binaria experimental del
cierre real, no un sustituto completo listo para conectar a los bots. Sus
resultados se conservan con ese alcance. Después se construyó lab.4, que conserva
su dirección y añade el vector temporal; falta integrar lab.4 con los bots.
La elección de utilizar el motor nuevo queda cerrada, no pendiente de otra confirmación.

**Corrección expresa del mismo 29/10:** se retira la propuesta anterior de usar
el par eventual de lab.2 para la decisión y una no resolución antigua aparte,
así como el mínimo derivado del 54%. El motor debe devolver, para el mismo plan
y horizonte, TP primero, SL primero y ninguno antes del vencimiento, sumando100%.
Los ocho puntos y el máximo20% se aplicarán a esas salidas compatibles.
También debe explicar qué barrera es menos alcanzable, con alcance/no alcance
por nivel dentro del plazo. Tocar un nivel en cualquier momento y tocarlo antes
del contrario son objetivos distintos: no se deriva el primero como complemento
de la probabilidad de primer toque. Si se presentan alcances marginales de TP y
SL pueden solaparse; no se fuerzan a sumar100%.

La simetría es sólo una restricción de propuestas de bots. El motor general
debe seguir analizando entradas, TP y SL desiguales definidos por los usuarios,
tanto LONG como SHORT, sin igualarlos ni suponer igual probabilidad por distancia.

| Regla | Intradía corto | Intradía medio | Swing corto |
|---|---:|---:|---:|
| Horizonte del pronóstico | 4 horas | 24 horas | 7 días |
| Probabilidad máxima de no resolución | 20% | 20% | 20% |
| Diferencia mínima TP−SL | 8 puntos | 8 puntos | 8 puntos |
| Beneficio bruto mínimo previsto al TP | 20 USDT | 25 USDT | 25 USDT |
| Espera obligatoria de tres controles/30 min | Retirada | No requerida | No requerida |
| Distancia a TP y SL desde entrada efectiva | Igual | Igual | Igual |
| Mínimo TP individual conservado | 50% | 30% configurado | 30% configurado |
| Cadencia conservada | 15 min | 60 min | 360 min |
| Aperturas máximas por día UTC conservadas | 3 | 2 | 1 |

Con tres probabilidades que suman uno, no resolución ≤20% y TP−SL ≥8 puntos
implican **TP ≥44%** en medio y swing. El corto conserva el mínimo adicional
del 50%; no se ha rebajado esa condición por interpretar «8 puntos».
El límite del 20% pertenece al pronóstico por plazo; no cambia una operación
realmente cerrada por TP o SL por una etiqueta de vencimiento.

## Entrada y comprobaciones conservadas

1. Analizar las propuestas con los datos previos y el motor de referencia.
2. Exigir no resolución ≤20%, ventaja ≥0,08, soporte de al menos 80 análogos,
   niveles válidos y simétricos, filtros individuales y protección de exposición.
3. Elegir entre candidatas aptas. El corto prioriza TP; medio y swing priorizan
   diferencia TP−SL. Se mantienen los desempates existentes.
4. Reanalizar inmediatamente la seleccionada con precio reciente. Si falla,
   pierde elegibilidad o deja de ser la mejor candidata, no abrir una alternativa
   sin revalidarla. No se esperan otros dos escaneos para autorizar al corto.
5. Revalidar precio ejecutable, exposición, cuota y caja disponible. Dimensionar
   sobre el plan simétrico en la entrada efectiva.
6. Rechazar si el objetivo económico no cabe dentro del capital y presupuesto
   de pérdida. No ampliar el SL o saltarse el presupuesto para cumplir el mínimo.
7. Guardar versión de política, análisis, dimensionamiento y mínimo utilizado.

El campo de ventaja almacenado no puede sustituir a la diferencia real entre
probabilidades: también se exige `P(TP) − P(SL) ≥ 0,08`, con tolerancia numérica
de 1e−12. Las entradas directas verifican los filtros y que cuenta, horizonte y
política coinciden; no pueden tomar el mínimo 20 del corto para un bot de 25.

## Capital y riesgo: alcance exacto

Se conserva la fórmula existente de presupuesto inicial de pérdida:

`caja libre × min(0,05; max(0,02; 0,02 + 0,10 × ventaja normalizada))`.

La asignación local ya preparada tenía comprobación estricta de ese presupuesto;
se conserva y se adapta a mínimos 20/25/25. Margen y apalancamiento finales deben
respetarlo después de redondear. El máximo de apalancamiento sigue siendo ×10.
La caja sigue siendo capital inicial más PnL cerrado menos márgenes reservados;
no es patrimonio marcado a mercado ni un límite de riesgo agregado.

La instrucción de **1000 USDT iniciales por bot** se conserva como capital de la
nueva prueba. Esta preparación no resetea cuentas ni añade capital al concurso.
Los objetivos 20/25 son PnL bruto teórico al TP; no incluyen financiación,
comisiones ni deslizamiento y no garantizan que se alcance el nivel.

Con distancias iguales, el beneficio previsto al TP y la pérdida prevista al SL
tienen la misma magnitud antes de costes. Cuando el presupuesto disponible no
admite esos importes, el resultado correcto es no abrir; no es una cuota incumplida.

## Pendientes de definición

- La regla para repetir activo y lado conserva los controles de exposición.
  El límite de posiciones ya está decidido y aplicado localmente: 8 por bot.
- Riesgo total conjunto y tratamiento del patrimonio con pérdidas flotantes.
- No habrá cierre por vencer el horizonte; el cierre mensual del concurso se conserva.
- Integrar el motor lab.4 con el escáner, comprobar paridad con el modelo
  congelado y guardar su comparación con v0.11 en cada análisis nuevo.
  Las etiquetas del cierre real usadas en los estudios anteriores se conservan;
  el horizonte se evalúa aparte, sin cambiar retrospectivamente esos resultados.

## Versiones, pruebas y recuperación

- Política preparada: `autonomous-contest-policy-v0.10-standard-20pct-8pp-immediate`.
- Dimensionamiento: `autonomous-capital-allocation-v3-hard-risk-min20-25`.
- Entrada: `immediate-final-revalidation-v1`.
- Se conservan los ayudantes y pruebas del mecanismo histórico de confirmación,
  activado expresamente sólo en sus pruebas sintéticas. El escáner actual no lo exige.
- **149 pruebas del simulador superadas**, incluyendo límites, LONG/SHORT,
  inserciones sintéticas, reanálisis fallido, cambio de ranking, simetría,
  objetivos por bot y presupuesto de pérdida.
- **90 pruebas del área de bots del laboratorio superadas**. Se conserva la
  especificación histórica de asignación v2 de mínimo 20 y la de v1 de mínimo 2;
  no se reescriben sus informes ni se repiten ensayos de mercado.
- Se ha conservado una copia de los ficheros previos del simulador en
  `outputs/bot_standard_20261028/before_patch`. Incluye los cambios locales
  anteriores a esta preparación: no utilizar un reset de Git para recuperarla.
  Recuperar sólo los ficheros afectados desde esa copia, revisando primero
  cambios posteriores. El nuevo test `test_autonomous_entry_standard.py` pertenece
  a esta preparación. La adaptación del extractor de pruebas del laboratorio
  sólo añade la constante por horizonte y aclara el alcance de la paridad del corto.

No hubo nuevas predicciones, backtests, descargas, consultas o escrituras remotas,
push, despliegue, reinicio del worker ni aperturas o cierres del concurso en este bloque.
