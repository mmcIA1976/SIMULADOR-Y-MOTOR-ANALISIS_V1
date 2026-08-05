# Metodologia LIMIT-4: persistencia compacta y acotada

Version: `limit-learning-snapshot-v0.1`.

Estado: implementada y probada en codigo, pero no conectada todavia al flujo
online ni aplicada manualmente sobre la base remota.

## 1. Que se persiste

El motor puede analizar varios pares durante cada ciclo, pero esos candidatos
son temporales. Supabase solo recibe el caso finalmente seleccionado y, como
maximo, tres fotografias de su ciclo de vida:

1. `placement`: plan elegido, baseline de activacion y vectores contextuales;
2. `activation`: evidencia del toque, tiempo de espera y vector fresco;
3. `closure`: evento terminal, etiqueta de aprendizaje y resultado economico.

No se crea una fila por polling del worker ni por cada par descartado.

## 2. Presupuesto por operacion

El contrato conserva un techo absoluto de 8192 bytes, pero la asignacion v0.1
solo permite 5888 bytes:

| Evento | Maximo |
|---|---:|
| Colocacion | 3584 bytes |
| Activacion | 1280 bytes |
| Cierre | 1024 bytes |
| Total reservado | 5888 bytes |

El tamano se calcula sobre JSON canonico UTF-8. La tabla vuelve a comprobar que
`payload_bytes` coincide con los bytes realmente recibidos.
Los numeros derivados se normalizan a 12 cifras significativas: suficiente para
reproducir y estudiar estas variables, sin arrastrar decimales binarios inutiles.

Quedan excluidos velas, klines, bids/asks, trades crudos, order books y clusters o
heatmaps de liquidaciones. Las liquidaciones se reducen a conteos, masa visible,
wallets conocidas y distancia del cluster mas cercano.

## 3. Limite diario

Solo `placement` consume un slot diario. La combinacion
`selected_case_day + daily_slot` es unica y el slot solo puede estar entre 1 y
50. Por tanto, la base no puede aceptar mas de 50 operaciones LIMIT seleccionadas
por dia, aunque el motor haya evaluado muchos mas candidatos.

Con el presupuesto completo de 5888 bytes, 50 casos diarios representan:

- 294400 bytes de payload al dia;
- 8832000 bytes en 30 dias;
- 107456000 bytes en 365 dias, aproximadamente 102.5 MiB.

Estas cifras son un maximo del payload de LIMIT. PostgreSQL anade cabeceras de
fila e indices, y las demas tablas de la aplicacion tambien consumen espacio.
Supabase documenta actualmente un limite de base de datos de 500 MB para
proyectos Free:
https://supabase.com/docs/guides/platform/database-size

## 4. Idempotencia y auditoria

Existe una sola fotografia de cada tipo por operacion mediante
`UNIQUE(operation_id, snapshot_type)`.

- un reintento con el mismo hash devuelve `idempotent_skip`;
- un reintento con contenido distinto se rechaza y no sobrescribe el original;
- activacion y cierre exigen que exista antes la colocacion;
- un cierre por expiracion o cancelacion no exige una activacion inexistente;
- las filas aceptadas son append-only.

El hash SHA-256 se calcula sobre el JSON canonico. Los campos principales para
estudio (`symbol`, `side`, `time_horizon`, tipo, fecha y etiqueta) tambien quedan
en columnas, evitando abrir el JSON para filtros habituales.

## 5. Esquema

La tabla propuesta es `limit_learning_snapshots`. El repositorio mantiene su
esquema de dos formas coherentes con el procedimiento actual:

- `supabase/schema.sql` para instalaciones o revisiones manuales;
- `db.py` para la inicializacion idempotente al arrancar una version desplegada.

LIMIT-4 no ejecuta ese SQL contra Supabase. La aplicacion online seguira sin
guardar estas filas hasta que LIMIT-5 conecte de forma controlada los eventos.

## 6. Puerta a LIMIT-5

Antes de activar escritura online se debera:

- desplegar y verificar el esquema en el entorno elegido;
- conectar solo el caso seleccionado, nunca todos los candidatos;
- probar reintentos, slot 50/51 y los tres eventos con una operacion real;
- medir `pg_total_relation_size('limit_learning_snapshots')` para conocer el
  coste real de filas e indices, no solo el payload teorico.
