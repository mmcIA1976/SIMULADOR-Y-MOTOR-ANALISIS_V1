# Contrato LIMIT v1

Version ejecutable: `limit-order-contract-v1.0`.

Estado: contrato aislado y probado. No activa todavia el analisis de ordenes
pendientes en produccion y no modifica M6 para entradas `market`.

## 1. Alcance

La primera version cubre exclusivamente ordenes limit de retroceso:

- `LONG limit`: el precio actual esta por encima de la entrada solicitada y la
  condicion de activacion es `price_lte`;
- `SHORT limit`: el precio actual esta por debajo de la entrada solicitada y la
  condicion de activacion es `price_gte`.

`stop_breakout` y `stop_breakdown` quedan fuera de LIMIT v1. Se incorporaran en
un contrato posterior porque el movimiento de llegada y el movimiento esperado
despues de la entrada tienen una semantica distinta.

## 2. Dos relojes independientes

La orden tiene dos horizontes que no pueden mezclarse:

1. Ventana de activacion: empieza en `analysis_at` y termina al consumir el
   horizonte seleccionado.
2. Ventana de resultado: solo empieza en la hora real de activacion y obtiene un
   horizonte M6 nuevo del mismo perfil.

Una activacion observada exactamente en el limite temporal cuenta como
activacion. Una observada despues se clasifica como no activada dentro del
horizonte.

## 3. Estados y eventos

No se anaden estados artificiales a la operacion. Se conservan los estados
actuales:

```text
PENDING_ENTRY -> OPEN -> CLOSED
      |                    ^
      +--------------------+
```

La activacion es el evento `pending_entry_activated`, no un estado estable.
Una pendiente tambien puede pasar directamente a `CLOSED` por expiracion o
cancelacion.

## 4. Etiquetas de aprendizaje

- pendiente expirada: `not_activated_by_expiry`;
- pendiente cancelada: `censored_before_activation`;
- activada y TP: `activation_then_tp_first`;
- activada y SL: `activation_then_sl_first`;
- activada sin barrera antes del vencimiento: `activation_then_neither_barrier`;
- cierre manual tras activar: `censored_after_activation`.

Una cancelacion no es evidencia de que el precio no hubiera alcanzado la
entrada. Por eso queda censurada y no entrena la clase de no activacion.

## 5. Espacios probabilisticos

Etapa A:

- `activated_by_expiry`;
- `not_activated_by_expiry`.

Etapa B, condicionada a activacion:

- `tp_first_within_outcome_horizon`;
- `sl_first_within_outcome_horizon`;
- `neither_barrier_before_outcome_expiry`.

Resultado completo:

- `activation_then_tp_first`;
- `activation_then_sl_first`;
- `activation_then_neither_barrier`;
- `not_activated_by_expiry`.

Las masas de cada distribucion deben sumar uno con tolerancia de `1e-12`.

## 6. Precio solicitado, disparo y fill

Se registran por separado:

- `requested_entry`: barrera solicitada e inmutable;
- `trigger_observed_price`: precio de mercado que aporta la evidencia;
- `simulated_fill_price`: precio usado por la operacion y por M6 tras activar.

LIMIT v1 usa de forma conservadora el precio limite solicitado y no concede una
mejora artificial de precio. Los fills parciales quedan fuera del alcance.

## 7. Fotografias

Se definen tres snapshots distintos, que nunca se sobrescriben:

1. Colocacion: plan, ventana, vectores de activacion/zona y estado de fuentes.
2. Activacion: evidencia, tiempo de espera, fill y nuevo vector de mercado.
3. Cierre: resultado, evidencia, MFE/MAE y resultado economico.

LIMIT-1 solo define los campos. La persistencia se implementara en LIMIT-4.

## 8. Limite de almacenamiento

El nuevo payload de aprendizaje tendra un presupuesto maximo de 8 KiB por
operacion. Queda prohibido persistir como parte de este contrato:

- velas crudas;
- libros de ordenes completos;
- heatmaps crudos de liquidaciones;
- un registro por cada ciclo del worker.

Solo se conservaran variables derivadas compactas y los tres eventos relevantes.

## 9. Invariantes

- Probabilidad de activacion no es probabilidad de TP.
- No activacion no es lo mismo que ninguna barrera despues de activar.
- Una cancelacion pendiente es un caso censurado.
- La fotografia inicial no se sustituye al activar.
- M6 `market` no cambia por este lote.
- La ausencia de una fuente opcional no puede rellenarse con datos inventados.
- Ninguna regla cambia probabilidades sin coeficientes validados.

## 10. Puerta a LIMIT-2

LIMIT-2 podra empezar cuando:

- el contrato ejecutable y sus pruebas esten verdes;
- las transiciones y etiquetas sean coherentes con la aplicacion actual;
- la API productiva continue rechazando `pending` hasta que exista un calculo de
  activacion validado;
- las pruebas de M6 market sigan pasando sin cambios.
