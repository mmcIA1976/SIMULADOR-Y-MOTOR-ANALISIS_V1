# M4.7 - Decision P1: entradas de mercado

Fecha: 2026-07-27

Estado: RESUELTA POR EL PROPIETARIO

## 1. Decision

El alcance actual de la fase 1 admite exclusivamente entradas `MARKET`.

- El analisis se realiza usando el precio actual de mercado.
- La operacion se inicia a mercado.
- `LIMIT`, `STOP_MARKET` y `STOP_LIMIT` quedan fuera del alcance inmediato.
- `trigger_condition`, estados de activacion y `timeInForce` no son aplicables
  al flujo actual.
- El tipo de orden no se inferira a partir del lado y de la posicion relativa
  del precio de entrada.

## 2. Motivo

Las ordenes pendientes no son operables con rigor mientras la aplicacion
dependa de actividad del usuario o de peticiones del cliente para observar el
mercado y no exista un proceso autonomo continuo que pueda gestionar ordenes y
fills sin una sesion abierta.

Las entradas pendientes se reconsideraran cuando exista ese proceso autonomo.
En ese momento requeriran un contrato separado para tipo de orden, trigger,
`timeInForce`, fill parcial, fill completo, cancelacion y vencimiento.

## 3. Consecuencia para el analisis

El precio de entrada usado por el analisis y el precio de ejecucion de mercado
deben pertenecer a una captura temporal coherente. La politica exacta de
referencia, frescura y tratamiento de una variacion entre analisis e inicio de
operacion se resolvera en P2.

No se autoriza reutilizar silenciosamente un analisis si su precio de entrada
ya no representa el precio actual aceptado por el contrato P2.

## 4. Cierre automatico por tiempo

La posibilidad propuesta de cerrar automaticamente una operacion al agotarse
una duracion elegida no pertenece a P1. Se registra como requisito para P4:

- la duracion concreta se elegira dentro del perfil temporal;
- si TP o SL no se alcanzan antes, existira una rama `expiry`;
- un cierre real sin usuario conectado requerira un proceso autonomo continuo;
- el precio y los costes de salida en `expiry` no se inventaran;
- las opciones exactas por perfil se decidiran en P4.

## 5. Estado

- P1: RESUELTA.
- P2: PENDIENTE.
- P3: PENDIENTE.
- P4: PENDIENTE.
- Ola 3 implementada: NO.
- Motor productivo modificado: NO.
- M4 cerrada: NO.
- M5 iniciada: NO.
