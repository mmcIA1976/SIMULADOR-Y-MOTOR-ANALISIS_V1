# Preparación del relevo global · 31 de octubre de 2026

Alcance pedido: análisis de todos los usuarios y bots del concurso. Esta preparación
no despliega ni activa la versión, no cambia cuentas o posiciones y no reescribe
predicciones, resultados, pesos ni avances históricos.

Corrección del 1/11/2026: un único análisis del motor activo. Se ha retirado la
generación, el guardado y la presentación de la comparación automática con v0.11.

Versión de publicación autorizada el 1/11: `0.40.21`. Contrato aditivo de datos:
`data-contract-v0.34-single-engine-inference`. Los registros anteriores mantienen su
contrato y su scoring originales. La estructura SQL existente se conserva.

## Modelo y selección

Modelo objetivo: `TP-SL-EXPERIMENTAL-v0.12-lab.4`, SHA-256
`1061816d0899ab541e61bf6e3b789dcb08d7328091f1a4ce2285bf1e59576a32`.

`engine_lab4/` contiene el modelo idéntico y las funciones de inferencia copiadas
del laboratorio, con procedencia y hashes en `manifest.json`. No contiene ajuste
de parámetros ni importa la app del lab. El histórico usado para aprender esos
pesos queda documentado en el modelo; no se reaprende durante una consulta.

La única selección global es `ANALYSIS_ENGINE_RELEASE`:

| Valor | Resultado |
|---|---|
| Ausente o `v0.12-lab.4` | Nuevo motor para usuarios, LIMIT, activaciones, controles y bots |
| `v0.11` | Recuperación explícita del comportamiento anterior, conservado |
| Cualquier otro | Arranque rechazado |

La web y el worker deben usar el mismo valor y el mismo paquete. El bot no recibe
un selector diferente. Un error de lab.4 bloquea el análisis/entrada; no se cambia
silenciosamente a v0.11. El horizonte, TP y SL de usuarios pueden ser asimétricos;
la simetría y los filtros 8 puntos/20% son reglas exclusivas de los bots.

Este relevo ejecuta el modelo ya definido: usa las mismas velas cerradas y seis
variables del lab, sin nuevas reglas ni umbrales. Conserva el orden C6 → contexto
→ LONG/EMA50 → respuesta SHORT → ratio LONG4h, sus gates congelados y la resolución
temporal. Cada paso guarda antes, después y alpha. No se cuentan como señales
independientes los pasos del mismo análisis. Los cierres posteriores permitirán
evaluar el nuevo motor; recuperar v0.11 conserva la evidencia
adversa. La evidencia histórica y sus límites son los del release congelado, no
resultados nuevos obtenidos por estas pruebas de compatibilidad.

## Histórico y registros nuevos

- Archivo previo de 308 ficheros: código, pruebas, artefacto v0.11 y release lab.4,
  en `outputs/engine_replacement_20261031/v011_before_integration_9dea33b4d401ee08.zip`.
  Su manifiesto permite comprobar y recuperar cada archivo por contenido.
- El artefacto y el cálculo v0.11 se conservan. Sus registros existentes no se
  convierten a v0.12. Las consultas históricas recuperan su propia versión de
  scoring, aunque el motor activo sea otro. No se ejecutan migraciones masivas.
- La caducidad de análisis no seleccionados excluye expresamente v0.11 y lab.4:
  sus snapshots y JSON completos no se vacían por esa tarea.
- Cada análisis nuevo conserva versión, scoring, hash del modelo, entrada,
  ventanas/contextos, seis operandos observacionales, procedencia, probabilidades,
  cadena de cinco correcciones y curva temporal. Sólo se calcula y guarda el
  pronóstico del motor seleccionado. No se ejecuta el analizador v0.11 en paralelo.
- Los controles compactados conservan los mismos operandos y trazas, sin duplicar
  todos los contextos. Se mantiene el límite existente de 48.000 bytes.
- Los escaneos guardan versión/modelo, hash de la entrada y las tres probabilidades
  del motor seleccionado también para candidatos no elegidos. Las operaciones seleccionadas
  conservan el análisis completo. Los antiguos formatos de escaneo siguen leyéndose.
- Una serie de avisos de cierre reinicia sus confirmaciones al cambiar de motor;
  cambiar probabilidades por actualizar versión no se interpreta como mercado
  deteriorándose. Los controles anteriores continúan almacenados y visibles.

TP/SL real y resolución dentro del horizonte siguen siendo datos separados.
El histórico de v0.11 permanece disponible para consulta y recuperación; no genera
un segundo análisis de las consultas nuevas.

## Comprobaciones y paso a producción

Verificación corregida: `outputs/single_engine_20261101/RESULTADO.md`.
El informe del 31/10 se conserva como antecedente de la preparación ya corregida.
`tools/check_engine_release.py` comprueba el archivo anterior, el artefacto
v0.11, el paquete congelado y el código de integración sin consultar una base.

Las pruebas se ejecutan sin red, con candidatas y contextos sintéticos. Incluyen
paridad con el servicio nativo del lab en LONG/SHORT y los tres horizontes, planes
asimétricos, recibos compactos, persistencia API, LIMIT, selección común, fallos sin
sustitución, lectura histórica y recuperación de v0.11.

El inicio acordado de bots sigue siendo después de finalizar octubre: 1 de
noviembre de 2026, 00:00 UTC / 01:00 de Madrid. No hay disparador programado.
Antes de activar:

1. Conservar una copia recuperable de la base de producción y comprobar su alcance
   por tablas; el ZIP local es un archivo de código/modelos, no un backup remoto.
2. Revisar los resultados locales y el paquete. Comprobar el cierre de octubre y
   la nueva temporada. Los saldos se crean con el mecanismo existente del concurso.
3. Desplegar el mismo paquete en web y worker y seleccionar explícitamente lab.4.
   No usar un arranque parcial con versiones discrepantes.
4. Verificar `/api/version`, heartbeat del worker y un análisis controlado: versión,
   hash, suma de probabilidades, registro único del motor activo, contrato LIMIT y gates de bots.
5. Si hay un fallo, seleccionar `v0.11` en ambos servicios o recuperar el despliegue
   previo. Conservar los registros lab.4 ya creados. No borrar ni revertir datos.

La preparación original no ejecutó esos pasos online ni afirmó que la base remota estuviese
respaldada. La gestión experimental de cierre 60%/protección sigue en el lab;
no se convierte en cierre automático de operaciones por este relevo del motor.

## Publicación autorizada el 1 de noviembre

El usuario ha autorizado implementar y hacer push para activar el relevo global
y las reglas acordadas de bots. Este paquete selecciona lab.4 por defecto en ambos
procesos; cualquier variable explícita de Railway tiene precedencia. La recuperación
requiere `ANALYSIS_ENGINE_RELEASE=v0.11` en web y worker, o volver al despliegue previo.
El estado efectivo sólo se certifica con `/api/version`, heartbeat y registros de
escaneo posteriores al despliegue. No hay cambio de esquema ni reescritura histórica.
`tools/backup_engine_release.py` crea la copia privada del esquema público en
`data/backups` (ignorado por Git), comprueba todas las tablas críticas y recorre
el archivo completo con `pg_restore`. No restaura ni modifica la base remota.
