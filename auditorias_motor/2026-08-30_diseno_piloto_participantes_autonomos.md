# Piloto de participantes autonomos del concurso

Fecha: 2026-08-30

## Objetivo

Generar casos prospectivos comparables con decisiones tomadas antes de conocer el
resultado, usando el mismo motor de produccion `TP-SL-EMPIRICAL-ANALOG-v0.9` y el
mismo cierre de operaciones y aprendizaje de la aplicacion. No se introduce un
segundo motor de probabilidad ni se permite que las reglas observacionales alteren
la seleccion.

## Politicas fijadas

| Participante | Horizonte | Escaneo | Maximo diario | Umbral de ventaja TP-SL |
|---|---:|---:|---:|---:|
| Bot Intradia Corto | 0-4 h | 15 min | 3 | 10 puntos porcentuales |
| Bot Intradia Medio | 0-24 h acumulativo | 60 min | 2 | 10 puntos porcentuales |
| Bot Swing Corto | 0-7 d acumulativo | 6 h | 1 | 2 puntos porcentuales |

Gates comunes: probabilidad TP >= 30%, masa sin resolver <= 55% y al menos 80
analogos seleccionados en cada tramo ejecutado. Universo inicial: BTC, ETH, SOL,
BNB, XRP e INJ, evaluando LONG y SHORT. La operacion usa entrada a mercado,
margen ficticio de 100 USDT y apalancamiento x1.

Los umbrales son provisionales. La reproduccion cronologica dio resultados
descriptivos positivos para esas configuraciones, pero los intervalos agrupados
por dia incluyeron cero. Por tanto son una politica de recogida prospectiva, no
evidencia de rentabilidad.

## Flujo

1. El worker mantiene una unica cotizacion reemplazable para los seis simbolos.
2. Al vencer el turno, el participante obtiene esa cotizacion fresca y calcula
   TP/SL con la volatilidad del horizonte solicitado.
3. Ejecuta v0.9 para los doce candidatos (seis pares por dos direcciones).
4. Aplica gates y ordena por ventaja TP-SL, probabilidad TP y masa sin resolver.
5. Repite una unica vez v0.9 para el candidato ganador con el precio y corte de
   datos mas recientes. Si deja de cumplir los gates, decide `NO_TRADE`.
6. Puede decidir `NO_TRADE`; la cuota es un maximo, no una obligacion.
7. Antes de abrir vuelve a leer el precio fresco del worker. Si el desplazamiento
   supera el 10% de la volatilidad del horizonte (con suelo de 0,02%), descarta
   la apertura para no simular una entrada retroactiva. Si es aceptable, traslada
   la geometria porcentual al precio real de ejecucion y lo deja en el contrato.
8. En simulacion registra `would_open`. En modo activo crea operacion y
   recomendacion en la misma transaccion, ya vinculadas desde el origen.
9. El worker cierra las operaciones reales con el procedimiento actual. Los
   candidatos conservados se evalúan despues con velas de 1 minuto y primer
   toque TP/SL, sin guardar las velas.

## Persistencia compacta

- Un resumen por escaneo realmente ejecutado.
- Panel completo del bot corto cada 4 h: 72 filas/dia.
- Panel completo de los bots medio y swing una vez al dia: 12 + 12 filas/dia.
- Hasta 12 candidatos no pertenecientes a panel al dia, contando primero los
  seleccionados y despues los casos frontera.
- Maximo de diseno: 108 candidatos compactos/dia.
- No se guardan velas, arrays de profundidad, transacciones ni mapas de
  liquidacion sin procesar.
- El JSON observacional tiene un limite de 12 KB y no interviene en la
  probabilidad.

Los analisis completos se guardan solo para el candidato que abre una operacion.
Esto evita volver a crear recomendaciones sin operacion vinculada.

## Despliegue seguro

El codigo se entrega desactivado y en simulacion por defecto:

```text
AUTONOMOUS_CONTEST_ENABLED=false
AUTONOMOUS_CONTEST_DRY_RUN=true
AUTONOMOUS_CONTEST_SCAN_POLL_SECONDS=30
```

El worker principal debe tener `OPERATION_WORKER_DRY_RUN=false` para publicar
precios. El orden de activacion previsto es: aplicar migracion, desplegar,
activar el concurso autonomo manteniendo `AUTONOMOUS_CONTEST_DRY_RUN=true`,
observar la recogida y solo despues autorizar aperturas reales cambiandolo a
`false`.
