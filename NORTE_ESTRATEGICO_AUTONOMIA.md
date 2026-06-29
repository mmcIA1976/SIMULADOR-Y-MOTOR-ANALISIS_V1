# Norte estrategico: autonomia, fiabilidad y aprendizaje

Fecha: 2026-06-29

Este documento fija el sentido del proyecto para que cada cambio futuro se mida contra el objetivo real. No es una nota de producto ni una lista de deseos: es el criterio operativo que debe guiar el desarrollo.

## Vision

La app debe evolucionar desde un simulador donde el usuario propone operaciones hacia un sistema autonomo capaz de:

- observar el mercado de forma periodica;
- analizar multiples activos, direcciones, horizontes y tipos de entrada;
- detectar los setups con mejor probabilidad ajustada a riesgo;
- decidir si existe una oportunidad o si lo correcto es no operar;
- simular de forma autonoma la mejor oportunidad cuando el sistema tenga reglas suficientes;
- aprender de resultados auditados;
- acercarse gradualmente a un bot de trading real solo cuando la muestra y la fiabilidad lo justifiquen.

El objetivo final no es una app visual. El objetivo es una plataforma de decision, simulacion, auditoria y aprendizaje que pueda convertirse en base de trading automatizado.

## Principio central

El navegador es solo una pantalla. El backend es el sistema operativo.

Ninguna regla critica puede depender de que haya un usuario mirando la app. Esto incluye:

- activacion de ordenes pendientes;
- cierre por take profit;
- cierre por stop loss;
- actualizacion de ranking;
- registro de evidencia;
- generacion de aprendizaje;
- recarga o ajustes de cartera simulada.

Si una operacion toca un nivel critico, el sistema debe procesarlo aunque nadie este conectado.

## Prioridad absoluta

Antes de mejorar visuales, rankings, metricas secundarias o nuevas capas de analisis, la base debe ser fiable:

1. Motor operativo autonomo.
2. Auditoria historica de operaciones.
3. Aprendizaje limpio y trazable.
4. Scanner periodico de mercado.
5. Recomendador autonomo.
6. Simulacion autonoma controlada.
7. Solo despues, camino hacia bot real.

## Reglas no negociables

- Toda operacion debe tener una fuente de mercado definida y coherente con su grafica.
- Para futuros crypto, la fuente operativa actual es Binance USD-M Futures.
- Una operacion `PENDING_ENTRY` debe activarse si el mercado toca su nivel.
- Una operacion `OPEN` debe cerrarse si toca TP o SL.
- Si TP y SL ocurren dentro de la misma vela, se debe intentar resolver el orden con trades agregados.
- `closed_at` debe representar la hora real del evento de mercado, no la hora en la que la app proceso tarde el cierre.
- El PnL, ranking y aprendizaje deben derivarse del evento real.
- El aprendizaje no puede usar resultados no auditados como si fueran verdad.
- Un TAKE PROFIT no refuerza automaticamente el analisis si el motor habia recomendado observar o advertia riesgo.
- Un STOP LOSS no invalida automaticamente el motor si el analisis ya habia advertido el riesgo.
- El apalancamiento no cambia la probabilidad tecnica; solo escala ganancia/perdida.

## Filtro para cualquier nueva tarea

Antes de implementar una mejora, responder:

1. Mejora la fiabilidad operativa?
2. Mejora la calidad del analisis?
3. Mejora el aprendizaje con datos limpios?
4. Aumenta la autonomia del sistema?
5. Aporta trazabilidad o auditoria?
6. Acerca el proyecto al recomendador/bot futuro?

Si la respuesta es no a casi todo, la tarea es secundaria.

## Motor operativo autonomo

Debe existir un worker backend que ejecute periodicamente:

1. Buscar operaciones `PENDING_ENTRY` y `OPEN`.
2. Agrupar por simbolo.
3. Consultar mercado Futures.
4. Revisar entrada pendiente desde el ultimo punto controlado.
5. Revisar TP/SL desde el ultimo punto controlado.
6. Activar o cerrar con transacciones seguras.
7. Guardar evidencia de mercado.
8. Actualizar cartera, ranking y aprendizaje.
9. Registrar estado del worker.

Este worker debe ejecutarse en Railway aunque no haya usuarios conectados.

## Auditoria historica

Las operaciones anteriores al motor autonomo quedan bajo sospecha hasta ser auditadas.

La auditoria debe reconstruir para cada operacion:

- entrada real o activacion pendiente;
- primer TP/SL desde la entrada;
- precio de cierre correcto;
- hora real de cierre;
- resultado monetario;
- evidencia de mercado;
- correspondencia con el analisis previo.

Clasificacion minima:

- correcta;
- motivo incorrecto;
- precio incorrecto;
- hora incorrecta;
- sin evidencia suficiente;
- cierre manual/no auditable como TP/SL automatico;
- aprendizaje pendiente de regeneracion.

Hasta completar esta auditoria, las conclusiones de aprendizaje existentes deben tratarse como material provisional.

## Aprendizaje limpio

El aprendizaje solo sirve si los resultados son verdaderos.

Por tanto:

- no modificar pesos del motor con historico no auditado;
- regenerar evaluaciones despues de corregir operaciones;
- separar aprendizaje pre-auditoria y post-auditoria;
- exigir muestra minima antes de aceptar hipotesis;
- guardar hipotesis y resultados en `auditorias_aprendizaje/`.

## Scanner y recomendador autonomo

Cuando la base operativa sea fiable, el sistema debe pasar de analizar solo propuestas del usuario a analizar oportunidades de forma periodica.

El scanner debe comparar:

- activos;
- long y short;
- entrada a mercado;
- orden pendiente/limit;
- temporalidades;
- probabilidad TP;
- probabilidad SL;
- rango/no ejecucion;
- EV esperado;
- regimen de mercado;
- tendencia multi-TF;
- niveles;
- liquidez;
- volatilidad;
- derivados;
- Fibonacci;
- riesgo de barrida;
- calidad del camino al TP.

La salida esperada no siempre es operar. Una decision valida es:

```text
No hay setup con ventaja suficiente.
```

## Simulacion autonoma antes de bot real

Antes de operar dinero real, el sistema debe demostrar valor en simulacion autonoma.

Condiciones minimas:

- reglas de riesgo maximo;
- limite de operaciones simultaneas;
- limite de perdida diaria/semanal;
- no duplicar setups correlacionados;
- registro explicable de por que el sistema decidio operar;
- muestra suficiente de operaciones auditadas;
- comparacion contra no operar;
- rendimiento estable por activo, direccion y horizonte.

## Camino hacia bot real

El bot real no es una fase estetica ni inmediata. Solo tiene sentido si:

- el motor operativo simulado es autonomo y fiable;
- el historico esta auditado;
- el aprendizaje es consistente;
- el scanner encuentra oportunidades con ventaja real;
- el sistema sabe no operar;
- existen controles de riesgo estrictos;
- existe trazabilidad completa para cada decision.

## Forma de trabajar

El desarrollo debe ser exigente y estructurado:

- leer el codigo antes de cambiarlo;
- entender el flujo real de datos;
- implementar una fase cada vez;
- probar con datos reales cuando sea necesario;
- auditar despues de cada cambio critico;
- registrar cambios del motor en `HISTORIAL_CAMBIOS_MOTOR_ANALISIS.md`;
- no hacer push de `db.py`, `.codex_backups` ni `ABRIR_APP_LOCAL.md` salvo orden expresa;
- no avanzar a funciones secundarias si la base operativa no es fiable.

## Estado inmediato

Prioridad actual:

1. Implementar worker autonomo backend.
2. Crear estado/monitor del worker.
3. Auditar operaciones activas y cerradas por TP/SL.
4. Corregir operaciones con evidencia clara.
5. Regenerar aprendizaje afectado.
6. Solo despues continuar con mejoras del motor de analisis y scanner autonomo.

Este documento debe consultarse antes de decidir prioridades de desarrollo.
