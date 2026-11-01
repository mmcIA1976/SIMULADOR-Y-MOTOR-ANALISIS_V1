# Arranque de los bots en noviembre de 2026

Decisión del usuario del 29/10/2026: empezar después de finalizar el concurso
de octubre. Sustituye la previsión anterior del 31 de octubre.

- Inicio previsto: **1/11/2026 a las 00:00 UTC, 01:00 en Madrid**, una vez
  confirmado que el sistema ha finalizado el concurso de octubre.
- Octubre conserva su motor y sus reglas online hasta terminar el concurso.
- Nueva temporada: 1000 USDT iniciales por bot mediante el mecanismo del concurso.
- Motor objetivo de los bots: `TP-SL-EXPERIMENTAL-v0.12-lab.4`.
- Modelo congelado: `1061816d0899ab541e61bf6e3b789dcb08d7328091f1a4ce2285bf1e59576a32`.
- Publicación autorizada el 1/11: app `0.40.21`, lab.4 seleccionado por defecto
  tanto en web como en worker. El estado efectivo se verifica tras el push.

## Reglas acordadas

| Condición | Intradía corto | Intradía medio | Swing corto |
|---|---:|---:|---:|
| Horizonte | 4 h | 24 h | 7 días |
| Máximo de posiciones activas por bot | 8 | 8 | 8 |
| Máximo de probabilidad de ninguno dentro del horizonte | 20% | 20% | 20% |
| Diferencia mínima P(TP) − P(SL) | 8 puntos | 8 puntos | 8 puntos |
| Beneficio bruto objetivo mínimo al TP | 20 USDT | 25 USDT | 25 USDT |
| Distancias desde la entrada efectiva | TP = SL | TP = SL | TP = SL |
| Cadencia conservada | 15 min | 60 min | 360 min |
| Aperturas máximas diarias UTC conservadas | 3 | 2 | 1 |

Las entradas pendientes que reservan margen cuentan para las ocho posiciones.
Se abre mientras haya caja y se cumplan los controles de riesgo, exposición y
elegibilidad. Se mantienen los mínimos individuales de TP ya documentados y
el reanálisis inmediato; se elimina la espera de tres controles del bot corto.

Vencer el horizonte del análisis **no cierra la posición**. Se guarda por
separado el resultado dentro del plazo y el cierre real posterior. El cierre
mensual propio del concurso sigue teniendo su motivo específico y no se
etiqueta como TP o SL si no lo fue.

## Estado de preparación y comprobaciones pendientes

Las reglas anteriores se incluyen en el paquete autorizado para producción. El 31/10 se incorporó la
integración global en código local mediante `served_analysis` y
`ANALYSIS_ENGINE_RELEASE`, compartida por usuarios, LIMIT, observaciones y bots.
Corrección del1/11: produce un único análisis del motor activo; v0.11 conserva
su histórico y la posibilidad de recuperación. Véase
`ENGINE_REPLACEMENT_2026_11.md` y los resultados de pruebas allí referenciados.
El despliegue y activación online siguen pendientes; deben completarse estas
comprobaciones antes de certificar el arranque:

1. **Comprobado en local:** inferencia congelada sin reajustar pesos, paridad
   con el laboratorio para seis pares, LONG/SHORT y los tres horizontes.
2. **Corregido el1/11:** un único pronóstico de lab.4, con datos
   anteriores al análisis; guardar versión, hash del modelo, probabilidades,
   operandos y contribuciones observacionales. Un fallo del motor elegido
   debe impedir la entrada, sin sustituirlo silenciosamente por v0.11.
3. **Comprobado en local:** reglas de entrada, registros, contratos de usuarios,
   LIMIT y controles, con pruebas sintéticas y selección global lab.4.
4. **Pendiente online:** copia recuperable de la base, finalización de octubre,
   nueva temporada y despliegue/activación global. Conservar el despliegue anterior.

La preparación local no modificó cuentas, saldos, operaciones ni variables online.
La publicación conserva saldos y posiciones existentes; el mecanismo mensual
ya cerró octubre y creó noviembre con 1000 USDT iniciales, comprobado en Supabase
el 1/11 antes del despliegue. Las nuevas reglas rigen las nuevas aperturas.
Las copias previas a esta preparación se conservan en
`outputs/bot_lab4_release_20261029/before_patch`.

El resultado histórico de lab.4 conserva la preferencia TP/SL de lab.2 en los
359 casos comprobados. No añade una validación futura ni demuestra una mejora
del error del vector temporal completo respecto a v0.11. La nueva temporada
aportará datos prospectivos para comprobarlo, sin reajustar el modelo en marcha.
