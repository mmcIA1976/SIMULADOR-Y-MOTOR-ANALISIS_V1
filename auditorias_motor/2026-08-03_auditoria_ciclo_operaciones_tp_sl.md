# Auditoria del ciclo de operaciones, TP/SL y persistencia

Fecha: 2026-08-03
Estado: COMPLETADA EN LOCAL
Commit de entrada: `b24b516`
Produccion modificada: no
Supabase modificado: no; todas las consultas de auditoria fueron de solo lectura.
El lote del monitor incluye la definicion local de `operation_worker_state`, pero no se aplico en produccion.

## 1. Objetivo

Comprobar que las operaciones pendientes y abiertas reflejan correctamente el recorrido real del mercado, que los cierres automaticos por `take_profit` y `stop_loss` son idempotentes y que la aplicacion no genera historico innecesario en Supabase al consultar operaciones ya cerradas.

## 2. Cobertura

- Operaciones totales inventariadas: 276.
- Operaciones abiertas reconstruidas contra velas publicas de Binance Futures: 5.
- Ordenes pendientes reconstruidas contra velas publicas de Binance Futures: 1.
- Cierres naturales por TP o SL auditados en Supabase: 210.
- Periodo observado para la prueba de idempotencia historica: desde 2026-05-22 hasta 2026-08-03.
- Endpoints revisados: `/api/price`, `/api/operations` y `/api/operations/{id}/ticks`.

## 3. Resultado principal

Las seis operaciones activas estaban en el estado correcto en el momento de la auditoria. Ninguna habia atravesado su condicion de entrada, TP o SL sin que la aplicacion lo hubiera reflejado.

| Operacion | Estado | Par | Direccion | Resultado de la reconstruccion |
|---:|---|---|---|---|
| 115 | `PENDING_ENTRY` | BTCUSDT | short | El precio no alcanzo la entrada solicitada de 69.800. |
| 203 | `OPEN` | SOLUSDT | short | No alcanzo SL 80 ni TP 70 desde la apertura. |
| 271 | `OPEN` | XRPUSDT | long | No alcanzo SL 0,99 ni TP 1,25 desde la apertura. |
| 272 | `OPEN` | BTCUSDT | short | No alcanzo SL 64.500 ni TP 61.950 desde la apertura. |
| 274 | `OPEN` | BTCUSDT | short | No alcanzo SL 66.000 ni TP 59.500 desde la apertura. |
| 275 | `OPEN` | BTCUSDT | short | No alcanzo SL 65.000 ni TP 60.200 desde la apertura. |

No se corrigio manualmente ningun estado porque no habia ningun cierre ni activacion atrasados.

## 4. Hallazgos

### 4.1 Los cierres duplicados son historicos y la proteccion actual funciona

El cierre automatico actual actualiza una operacion solo si sigue en estado `OPEN`. Los ticks, el saldo y el evento de cartera se generan unicamente si esa actualizacion afecto realmente a una fila.

La frontera historica confirma el efecto de esa proteccion:

| Periodo | Cierres TP/SL | Operaciones con eventos de cierre repetidos | Operaciones con ticks terminales repetidos |
|---|---:|---:|---:|
| Antes del guard, hasta 2026-07-01 13:38:09 UTC | 121 | 14 | 14 |
| Despues del guard | 89 | 0 | 0 |

Los duplicados antiguos no multiplicaron el saldo actual. La cartera se recalcula desde `operations.final_pnl`, donde existe una sola fila por operacion, y no sumando `wallet_events`. Su impacto es historico repetido, auditoria confusa y almacenamiento innecesario.

### 4.2 Dos endpoints GET escribian historico retrospectivamente

`GET /api/operations` y `GET /api/operations/{id}/ticks` llamaban a una reparacion implicita para operaciones cerradas. Una simple consulta podia:

- consultar otra vez Binance;
- actualizar `exit_evidence_json`;
- insertar una ventana densa de velas;
- insertar un nuevo tick `auto_exit`.

Esto mezclaba lectura con reconstruccion historica y podia crear datos diferentes mucho despues del cierre real.

La operacion 81 demuestra el defecto:

- cierre correcto: TP 1.750 el 2026-06-15 10:54 UTC;
- evidencia de vela correcta: maximo 1.750 y motivo `take_profit`;
- tick retrospectivo incorrecto: `auto_exit` a 1.600, que era el SL;
- fecha del tick incorrecto: 2026-06-29, catorce dias despues del cierre.

La reparacion automatica desde endpoints GET queda eliminada en local. Los endpoints ahora devuelven solo lo ya persistido y no fabrican evidencia ni ticks.

### 4.3 Calidad del historico cerrado

De los 210 cierres TP/SL:

- 209 tienen evidencia de salida almacenada;
- 210 tienen al menos un tick;
- 209 tienen tick terminal de tipo `auto_exit`;
- ninguno carece de `closed_at`, `close_price` o `final_pnl`;
- 19 operaciones tienen alguna incidencia historica de trazabilidad;
- 14 de esas 19 corresponden al defecto antiguo de doble procesamiento;
- las operaciones 1 y 3 usan un precio efectivo de cierre diferente al nivel teorico del SL, pero su PnL es coherente con ese precio efectivo;
- la operacion 81 conserva el tick retrospectivo incorrecto descrito arriba.

No se reescribieron operaciones antiguas porque decidir entre conservar deslizamiento historico, normalizar al nivel del plan o borrar evidencia requiere una politica explicita y una copia previa.

## 5. Volumen en Supabase

En la captura de auditoria la base completa ocupaba aproximadamente 76,9 MB. Las tablas directamente relacionadas con este ciclo ocupaban:

| Tabla | Filas o contenido relevante | Tamano total con indices |
|---|---:|---:|
| `price_ticks` | 50.534 filas | 7.929.856 bytes |
| `operations` | 276 operaciones | 573.440 bytes |
| `wallet_events` | eventos de cartera | 221.184 bytes |

Dentro de `price_ticks` habia 20.465 filas de ventanas de salida de un minuto y 1.719 filas exactamente duplicadas por operacion, fuente, instante y precio. Tambien habia 17 eventos `operation_closed` redundantes repartidos entre 14 operaciones.

La correccion local evita crecimiento provocado por abrir pantallas o consultar ticks. El worker autonomo del lote anterior guarda por defecto un unico tick terminal compacto por cierre, no una ventana densa.

## 6. Cambios locales

- Eliminadas las llamadas de reparacion retrospectiva desde ambos endpoints GET.
- Eliminadas las dos funciones internas que actualizaban evidencia e insertaban ticks desde esas lecturas.
- Anadida una prueba que reproduce la insercion no deseada al consultar ticks.
- Anadida una prueba que impide reintroducir el backfill desde el listado de operaciones.
- Anadida una prueba de carrera: un candidato de cierre obsoleto no puede repetir ticks, saldo ni eventos.

La correccion de los GET no necesita cambios de esquema. El lote conjunto del monitor si incorpora la tabla local `operation_worker_state`, limitada a una fila sustituible mediante `UPSERT`; no se ejecuto ninguna migracion ni se borro ninguna fila de Supabase.

## 7. Pruebas

- Suite completa: 697 pruebas superadas.
- Compilacion de los modulos Python modificados: correcta.
- Comprobacion de sintaxis de `app.js`: correcta.
- Prueba de caracterizacion antes de corregir: fallo esperado porque el GET inserto un `auto_exit` nuevo.
- La misma prueba despues de corregir: superada, cero filas nuevas.

## 8. Limpieza historica propuesta, no ejecutada

Una limpieza segura debe ser un lote separado y requerir autorizacion expresa:

1. Exportar las filas candidatas y sus identificadores.
2. Conservar una fila canonica por grupo exactamente duplicado.
3. Revisar por separado el tick incorrecto de la operacion 81 y los casos legacy 1 y 3.
4. Borrar solo los duplicados aprobados: hasta 1.719 ticks exactos y 17 eventos de cierre redundantes segun la captura actual.
5. Repetir el inventario y comprobar que saldos, PnL y operaciones no cambian.

Esta limpieza reduciria ruido y algo de espacio, pero no es urgente: el crecimiento futuro queda atacado en el origen y `price_ticks` ocupa actualmente menos de 8 MB incluidos sus indices.

## 9. Decision

- Estado funcional de operaciones activas: correcto.
- Idempotencia de cierres actuales: verificada.
- Defecto actual encontrado: escrituras retrospectivas desde endpoints GET.
- Defecto corregido en local: si.
- Datos historicos de produccion corregidos: no.
- Commit y push autorizados posteriormente por el usuario: si.
- Despliegue o aplicacion del esquema en produccion: no.
