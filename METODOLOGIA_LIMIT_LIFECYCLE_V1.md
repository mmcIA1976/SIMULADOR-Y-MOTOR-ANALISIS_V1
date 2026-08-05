# Metodologia LIMIT-6: activacion y cierre completos

Version de runtime: `limit-lifecycle-runtime-v0.1`.

Version de contrato: `limit-order-contract-v1.4`.

## 1. Recalculo al activar

La previsualizacion M6 de colocacion se conserva sin sobrescribir. Cuando el
precio toca la entrada solicitada, el worker ejecuta un M6 nuevo usando:

- la entrada LIMIT solicitada como fill simulado;
- la hora real del toque como corte del analisis;
- el horizonte completo elegido empezando de nuevo en la activacion.

Si el worker reconstruye una activacion pasada desde velas, usa exclusivamente
datos historicos cerrados hasta ese instante. No mezcla el libro, funding,
posicionamiento o liquidaciones actuales con un evento antiguo. Las fuentes no
reconstruibles quedan marcadas como tales.

Un fallo de datos M6 no deshace un toque de precio real. La orden se activa y el
snapshot registra `blocked` con su codigo, sin inventar probabilidades.

## 2. Dos vencimientos distintos

- Si no se toca la entrada antes del vencimiento de activacion, la orden pasa de
  `PENDING_ENTRY` a `CLOSED` con `pending_entry_expired`.
- Si la orden activa pero no toca TP ni SL dentro del horizonte posterior, pasa
  de `OPEN` a `CLOSED` con `outcome_expired`.

El segundo reloj empieza en `triggered_at`; nunca reutiliza el tiempo consumido
esperando la entrada. TP y SL observados despues del vencimiento no se atribuyen
al plan LIMIT.

## 3. Eventos terminales y aprendizaje

Se conectan seis resultados sin mezclarlos:

- TP: `activation_then_tp_first`;
- SL: `activation_then_sl_first`;
- vencimiento posterior: `activation_then_neither_barrier`;
- vencimiento sin activar: `not_activated_by_expiry`;
- cancelacion pendiente: `censored_before_activation`;
- cierre manual activado: `censored_after_activation`.

Las cancelaciones y cierres manuales son censura; no se convierten en evidencia
falsa de fracaso o acierto del modelo.

## 4. Persistencia acotada

No se guardan velas ni cada ciclo del worker. Para una operacion seleccionada se
mantienen como maximo:

- 3584 bytes al colocar;
- 1280 bytes al activar;
- 1024 bytes al cerrar.

El snapshot de activacion conserva probabilidades M6 resumidas, numero de reglas,
modo vivo/historico y estados de fuentes. El cierre conserva etiqueta, tiempo,
MFE, MAE, PnL y multiple de riesgo. La escritura sigue siendo idempotente y una
sola fila por tipo de evento.

## 5. Interfaz y compatibilidad

Tras activar, la app muestra TP/SL/rango del M6 recalculado y lo identifica como
lectura de activacion. La recomendacion de colocacion permanece intacta para
auditoria. Las operaciones a mercado no cargan contrato LIMIT ni cambian su
flujo de apertura o cierre.

## 6. Alcance no incluido

`LONG stop_breakout` y `SHORT stop_breakdown` quedan registrados en
`BACKLOG_MOTORES_ORDENES_PENDIENTES.md` para un motor futuro de ruptura.
