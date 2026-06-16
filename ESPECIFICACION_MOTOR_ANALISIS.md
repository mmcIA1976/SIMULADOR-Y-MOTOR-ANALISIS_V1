# Motor de analisis y aprendizaje

El sistema debe evitar una pantalla saturada de graficas. La interfaz principal debe mostrar una conclusion operativa clara basada en un analisis profundo y registrable.

No debe funcionar como recomendacion financiera, sino como entrenador de decisiones en operaciones simuladas.

## Resultado visible para el usuario

La pantalla principal debe mostrar solo lo esencial:

- Estado de la operacion simulada.
- Probabilidad estimada de take profit.
- Probabilidad estimada de stop loss.
- Riesgo estimado: bajo, medio, alto o extremo.
- Calidad del setup: A, B, C, D.
- Confianza del analisis: baja, media o alta.
- Decision de entrenamiento:
  - operar en simulacion
  - observar
  - descartar
  - ajustar stop
- Tres a cinco razones principales.
- Alertas criticas si existen eventos o condiciones anormales.
- Recomendaciones sobre parametros si el usuario las solicita:
  - entrada
  - stop loss
  - take profit
  - apalancamiento
  - margen
  - esperar confirmacion
  - invalidar la idea

Ejemplo:

```text
Setup B
Probabilidad TP: 57%
Probabilidad SL: 43%
Riesgo: medio-alto
Confianza: media

Lectura:
La tendencia corta acompana, pero el funding esta elevado y el precio esta cerca de una zona de liquidaciones. El sistema recomienda simular con tamano prudente o esperar confirmacion.
```

## Flujo obligatorio pre-operacion

Antes de iniciar una simulacion, el sistema debe analizar la propuesta del usuario.

El usuario propone:

- activo
- direccion: long o short
- entrada deseada
- tipo de entrada: mercado, limite, ruptura/trigger o DCA planificado
- margen
- apalancamiento
- stop loss
- take profit
- plan de salidas parciales si aplica
- horizonte temporal aproximado si aplica
- motivo de entrada opcional

El sistema responde con:

- probabilidad estimada de take profit
- probabilidad estimada de stop loss
- probabilidad de quedar en rango sin resolver en el horizonte estimado
- riesgo de liquidacion o riesgo de perdida excesiva
- calidad del setup
- confianza del analisis
- decision sugerida
- parametros sugeridos si procede
- razones principales
- alertas criticas
- datos insuficientes si los hubiera

La simulacion solo debe iniciarse despues de que exista un analisis pre-operacion registrado.

## Recomendacion de parametros

Cuando el usuario lo pida, el motor puede proponer ajustes. Estos ajustes deben ser explicables y conservadores.

Parametros que puede revisar:

### Entrada

- confirmar entrada actual
- sugerir esperar retroceso
- sugerir esperar ruptura
- sugerir no entrar si el precio esta en zona desfavorable
- sugerir entrada por tramos si mejora la relacion riesgo/beneficio

### Stop loss

- evaluar si esta demasiado cerca para la volatilidad actual
- evaluar si esta demasiado lejos respecto al beneficio potencial
- sugerir stop tecnico basado en rango, ATR o estructura
- advertir si el stop implica perdida excesiva con el apalancamiento elegido

### Take profit

- evaluar si el objetivo es realista respecto al rango actual
- sugerir TP parcial o TP mas conservador
- detectar si el TP esta antes/despues de una zona relevante
- sugerir salida por tramos si el recorrido tiene resistencias intermedias

### Apalancamiento

El apalancamiento no debe modificar la probabilidad direccional ni la recomendacion tecnica del setup.

Regla actual del motor:

- el leverage escala PnL, exposicion y sensibilidad monetaria;
- no cambia si el precio tiene mas o menos probabilidad de llegar a TP o SL;
- no debe aparecer como razon para observar, aceptar o descartar una operacion;
- puede mostrarse como dato de gestion monetaria, pero no como senal de mercado.

Esta regla evita mezclar calidad de analisis con tamano de apuesta.

### Margen

- sugerir reduccion si el riesgo absoluto supera limite definido
- sugerir mantener si el riesgo esta dentro de tolerancia

Ejemplo de salida:

```json
{
  "analysis_type": "pre_trade",
  "tp_probability": 0.54,
  "sl_probability": 0.38,
  "range_probability": 0.08,
  "risk_level": "medio",
  "setup_grade": "B",
  "confidence": "media",
  "training_decision": "simular con ajustes",
  "parameter_advice": {
    "entry": {
      "action": "esperar",
      "suggested_value": 76620,
      "reason": "Mejoraria la relacion riesgo/beneficio y reduce entrada tardia."
    },
    "stop_loss": {
      "action": "ajustar",
      "suggested_value": 75880,
      "reason": "El stop actual esta cerca del ruido de volatilidad reciente."
    },
    "take_profit": {
      "action": "mantener",
      "suggested_value": 79500,
      "reason": "Objetivo compatible con rango superior si hay continuidad."
    },
    "leverage": {
      "action": "mantener",
      "suggested_value": 10,
      "reason": "El apalancamiento afecta exposicion/PnL, pero no modifica la lectura de mercado."
    }
  },
  "reasons": [
    "Momentum corto favorable",
    "Relacion riesgo/beneficio aceptable si mejora la entrada",
    "Volatilidad reciente exige mas margen para el stop"
  ],
  "alerts": []
}
```

## Ordenes simuladas y DCA

El sistema debe permitir planificar ordenes simuladas antes de abrir una operacion.

Tipos de orden simulada:

- entrada a mercado
- entrada limite
- entrada por ruptura o stop trigger
- DCA de entrada
- take profit unico
- salidas parciales
- DCA de salida
- stop loss global
- stop loss por tramo si aplica
- cierre manual

Estas ordenes no ejecutan trading real. Solo definen el plan de simulacion.

## DCA de entrada

El DCA de entrada debe usarse como herramienta de planificacion, no como excusa para promediar perdidas sin control.

El sistema debe analizar:

- numero de tramos
- precio de cada tramo
- margen asignado a cada tramo
- precio medio resultante
- stop loss global
- perdida maxima si se completa todo el DCA
- ratio riesgo/beneficio con entrada parcial y completa
- si el DCA mejora o empeora la probabilidad ajustada por riesgo

Reglas de control:

- maximo de tramos por defecto: 3
- no permitir DCA infinito
- no aumentar margen si invalida el riesgo maximo definido
- cada tramo debe estar justificado por estructura, volatilidad o zona tecnica
- si el precio llega al stop antes de completar tramos, la operacion se cierra

Ejemplo:

```text
Entrada DCA long:
Tramo 1: 40% en 76766
Tramo 2: 35% en 76380
Tramo 3: 25% en 76080
Entrada media si completa: 76463
Stop global: 75880
```

## DCA de salida

El DCA de salida o salida parcial debe servir para realizar beneficios en zonas logicas y reducir presion emocional.

El sistema debe analizar:

- numero de objetivos
- porcentaje a cerrar en cada objetivo
- beneficio realizado si toca cada tramo
- posicion restante
- stop ajustado si aplica
- efecto sobre esperanza matematica

Ejemplo:

```text
Salida parcial:
TP1: cerrar 40% en 78200
TP2: cerrar 35% en 79000
TP3: cerrar 25% en 79500
```

Ventajas que debe evaluar:

- reduce presion psicologica
- captura beneficio parcial
- permite dejar correr una parte si el movimiento continua

Riesgos que debe evaluar:

- puede reducir beneficio si el objetivo principal se alcanza
- puede generar cierres demasiado tempranos en usuarios impacientes
- requiere reglas claras de stop para la posicion restante

## Ordenes de inicio de operacion

El sistema debe poder simular operaciones que no empiezan inmediatamente.

Tipos:

- iniciar al precio actual
- iniciar si el precio baja/sube a una entrada limite
- iniciar si rompe un nivel
- iniciar al cierre de vela confirmada
- iniciar despues de evento macro
- iniciar solo si se cumple condicion adicional

Ejemplos de condicion adicional:

- precio por encima/debajo de EMA 21
- ruptura de maximo reciente
- delta comprador positivo
- funding dentro de rango aceptable
- no hay evento macro critico en los proximos X minutos

Estas condiciones deben quedar registradas para evaluar si el sistema recomendo esperar correctamente.

## Ordenes pendientes implementadas

El motor distingue entre entrada a mercado y orden pendiente.

Tipos actuales:

- `market`: la operacion empieza al precio de entrada usado por el usuario.
- `pending` con `price_lte`: se activa si el precio toca o cae por debajo de la entrada.
- `pending` con `price_gte`: se activa si el precio toca o supera la entrada.

Tipo operativo derivado:

- long + `price_lte`: `limit_pullback`
- long + `price_gte`: `stop_breakout`
- short + `price_gte`: `limit_pullback`
- short + `price_lte`: `stop_breakdown`

La orden pendiente queda registrada como `PENDING_ENTRY` hasta que el mercado toca el nivel. Al activarse:

- pasa a `OPEN`;
- guarda `triggered_at`;
- guarda `trigger_price`;
- guarda evidencia de activacion en `activation_evidence_json`;
- empieza a evaluarse contra TP/SL desde la activacion.

## Analisis de zona para ordenes pendientes

Una orden pendiente no se debe analizar igual que una entrada a mercado.

El motor calcula `zone_analysis` para separar tres preguntas:

1. Si el precio tiene probabilidad razonable de activar la orden.
2. Si la zona de activacion tiene confluencia tecnica suficiente.
3. Si, una vez activada, la reaccion esperada favorece el plan o aumenta riesgo de barrida/falsa ruptura.

Campos internos principales:

- `entry_order_type`
- `entry_zone_type`
- `distance_to_activation_pct`
- `atr_units_to_activation`
- `range_units_to_activation`
- `zone_confluence_score`
- `activation_probability`
- `reaction_bias`
- `rejection_probability`
- `breakout_probability`
- `liquidity_sweep_risk`
- `pullback_quality`
- `breakout_quality`
- `invalidation_quality`
- `target_path_quality`
- `zone_summary`
- `zone_reasons`
- `zone_alerts`

El motor v0.9 crea tambien `zone_probability_context`.

Reglas de prudencia:

- una zona favorable puede sumar como maximo `+0.025` a la probabilidad direccional;
- una zona desfavorable puede restar como maximo `-0.035`;
- una orden con baja probabilidad de activacion aumenta `range/no ejecucion` en vez de castigarse como mala direccion;
- el riesgo de barrida, mala invalidacion o barreras antes del TP pueden aumentar `risk_score`;
- no se deben ampliar estos caps sin al menos 30 casos comparables.

Interpretacion correcta:

- Si una orden no se activa, no significa que la direccion fuera mala.
- Si una orden se activa en una zona advertida y falla, refuerza el riesgo de zona.
- Si una orden gana pese a advertencias de zona, no refuerza automaticamente esas advertencias; se investiga como oportunidad infravalorada.

## Lo que se guarda por debajo

Cada analisis debe quedar registrado aunque el usuario solo vea una conclusion simple.

Datos por recomendacion:

- id de usuario
- id de operacion
- tipo de analisis: pre-operacion, seguimiento o post-operacion
- fecha y hora del analisis
- activo
- lado: long o short
- entrada
- margen
- apalancamiento
- stop loss
- take profit
- probabilidad TP
- probabilidad SL
- riesgo estimado
- calidad del setup
- confianza
- decision sugerida
- recomendaciones de parametros
- plan de ordenes simuladas
- contexto de orden pendiente: tipo de entrada, condicion de activacion, tipo de orden y precio solicitado
- `zone_analysis` si aplica
- `zone_probability_context` si aplica
- plan DCA de entrada si existe
- plan DCA de salida si existe
- razones principales
- alertas
- snapshot completo de variables
- version del motor de analisis

Cuando la operacion termina, se registra:

- resultado real: TP, SL, cierre manual o abierta
- PnL final
- duracion
- maximo favorable
- maximo adverso
- si la recomendacion fue acertada o no
- desviacion entre probabilidad estimada y resultado
- ejecucion real de tramos DCA
- diferencia entre entrada propuesta y entrada media real
- efecto de salidas parciales sobre PnL
- notas del usuario
- aprendizaje estructurado de zona pendiente si aplica

## Aprendizaje por zonas pendientes

El aprendizaje guarda cada operacion cerrada en `learning_evaluations.structured_json`.

Para ordenes pendientes debe incluir:

- `pending_entry_context`: tipo de entrada, condicion, tipo de orden, precio solicitado, activacion y precio/hora de disparo;
- `analysis_context.zone`: confluencia, probabilidad de activacion, reaccion esperada, riesgo de barrida, invalidacion, camino al TP y ajustes v0.9;
- `zone_learning`: categoria interna para saber si la zona debe reforzarse, investigarse o tratarse como advertencia confirmada.

Categorias internas relevantes:

- `reinforce_favorable_pending_zone`
- `investigate_failed_favorable_pending_zone`
- `reinforce_warned_pending_zone_risk`
- `investigate_success_against_pending_zone_warning`
- `pending_zone_not_activated`
- `pending_zone_context_only`

Las auditorias agregadas usan `/api/learning/pending-zone-audit` para agrupar por:

- tipo de orden;
- tipo de zona;
- sesgo de reaccion;
- riesgo de barrida;
- bucket de ajuste de zona;
- categoria de aprendizaje;
- lado y temporalidad.

Ninguna conclusion debe considerarse robusta con muestras pequenas.

## Multiusuario

El sistema debe permitir que diferentes usuarios participen en el entrenamiento abriendo operaciones simuladas. Esto acelera el aprendizaje porque aumenta la cantidad y diversidad de casos.

Cada usuario debe tener:

- id interno
- nombre visible o alias
- fecha de alta
- nivel de experiencia declarado
- perfil de riesgo declarado
- estadisticas propias
- historial propio de operaciones
- historial propio de recomendaciones

El sistema debe aprender en dos niveles:

1. Aprendizaje individual:
   - como opera cada usuario
   - donde suele acertar
   - donde suele fallar
   - que activos domina peor o mejor
   - que tipos de entrada y zonas suele gestionar mejor o peor

2. Aprendizaje agregado:
   - patrones comunes entre todos los usuarios
   - setups que funcionan de forma general
   - condiciones de mercado donde casi todos fallan
   - diferencias por nivel de experiencia
   - errores repetidos por perfil de riesgo

La recomendacion final puede combinar ambos niveles:

```text
Probabilidad base del setup segun todos los usuarios
+ ajuste por el historial del usuario actual
+ ajuste por condiciones actuales de mercado
```

Ejemplo:

```text
El setup tiene buen comportamiento general, pero este usuario suele cerrar peor las ordenes pendientes activadas en zonas de barrida alta. Se mantiene la lectura de mercado, pero se reduce confianza operativa hasta tener mas casos comparables.
```

## Privacidad y separacion de datos

Aunque el aprendizaje agregado use datos de varios usuarios, la app debe separar:

- datos privados del usuario
- estadisticas agregadas anonimas
- recomendaciones generales
- recomendaciones personalizadas

La interfaz de un usuario no debe mostrar operaciones privadas de otro usuario salvo que exista un modo administrador o grupo de entrenamiento autorizado.

## Roles

Roles iniciales:

- administrador: ve usuarios, operaciones agregadas, metricas globales y configuracion del motor
- usuario entrenador: abre operaciones simuladas, recibe analisis y registra notas
- observador: puede ver resultados agregados sin modificar datos

## Riesgo de sesgo

Al incorporar varios usuarios, el sistema debe controlar sesgos:

- usuarios con demasiadas operaciones no deben dominar todo el modelo sin ponderacion
- operaciones duplicadas o copiadas deben marcarse
- resultados por suerte en muestras pequenas no deben sobreponderarse
- el nivel de experiencia debe usarse como contexto, no como juicio absoluto
- el sistema debe distinguir entre mala operacion y mal mercado

## Metricas multiusuario

Metricas utiles:

- win rate global
- win rate por usuario
- win rate por setup
- PnL medio por setup
- error medio de probabilidad estimada
- calibracion por rangos de probabilidad
- setups con mayor consenso
- setups con mayor desacuerdo
- usuarios que mejor identifican condiciones favorables
- usuarios que mejor evitan operaciones malas

## Variables internas

El motor debe cotejar variables de distintas familias.

### Precio y tendencia

- EMA 9, 21, 50, 200
- pendiente de medias
- distancia del precio a medias
- VWAP
- estructura de mercado
- rango reciente
- ruptura o rechazo

### Volatilidad

- ATR
- rango porcentual reciente
- compresion o expansion
- distancia del stop respecto a volatilidad
- riesgo de barrido de stop

### Volumen y flujo

- volumen relativo
- delta comprador/vendedor
- CVD
- absorcion
- agresion compradora o vendedora

### Derivados

- funding rate
- open interest
- cambio de open interest
- liquidaciones recientes
- basis spot/perpetuo
- exceso de longs o shorts

### Mercado cruzado

- Nasdaq
- S&P 500
- DXY
- yields
- VIX
- oro
- correlacion BTC/riesgo

### Eventos

- noticias economicas relevantes
- FOMC
- CPI
- NFP
- decisiones de tipos
- guerras o eventos geopoliticos
- regulacion crypto
- hackeos o crisis de exchanges

### Usuario

- tasa historica de acierto por activo
- tasa de acierto por long/short
- tasa de acierto por apalancamiento
- rendimiento por rango horario
- errores repetidos
- condiciones donde el usuario suele perder
- estado emocional declarado antes de operar
- confianza declarada
- impulsividad percibida
- cumplimiento de plan
- tendencia a mover stop o take profit
- tendencia a sobreoperar

## Factor emocional

El sistema debe estudiar tambien el comportamiento del usuario, porque en trading el factor emocional puede pesar mas que la lectura tecnica.

Aunque una cuenta simulada no reproduce todo el estres de una cuenta real, permite detectar patrones:

- entrar por impulso
- operar por aburrimiento
- perseguir precio despues de un movimiento
- subir apalancamiento tras una perdida
- cerrar ganadoras demasiado pronto
- dejar correr perdedoras
- mover stop loss sin razon tecnica
- operar peor en determinados horarios
- repetir un setup despues de una perdida para recuperarse
- ignorar alertas del sistema

## Registro emocional ligero

El sistema no debe convertir cada operacion en un interrogatorio. Debe recoger pocos datos, pero consistentes.

Antes de simular:

- motivo de entrada:
  - setup tecnico
  - noticia/evento
  - impulso
  - recuperacion de perdida
  - prueba/entrenamiento
- disciplina esperada:
  - seguire el plan
  - podria cerrar manualmente
  - no estoy seguro

Durante la operacion:

- cierre manual con motivo
- modificacion de stop loss
- modificacion de take profit
- nota rapida del usuario

Despues de cerrar:

- cumplio el plan: si/no/parcial
- emocion al cerrar
- error principal percibido
- aprendizaje del usuario

## Perfil emocional por usuario

Cada usuario debe tener un perfil de comportamiento que evoluciona con el historico.

Metricas utiles:

- win rate cuando declara confianza alta
- win rate cuando declara ansiedad o frustracion
- frecuencia de operaciones impulsivas
- frecuencia de cierres manuales antes de TP o SL
- frecuencia de mover stop
- operaciones tras una perdida
- variacion de resultados por horario
- apalancamiento medio tras ganar
- apalancamiento medio tras perder
- cumplimiento del plan

Ejemplos de conclusiones:

```text
Este usuario tiende a perder cuando opera frustrado despues de una perdida.
```

```text
El usuario acierta mas cuando declara confianza media que confianza maxima, lo que sugiere exceso de seguridad en setups agresivos.
```

```text
El sistema recomienda bloquear simulaciones x10 durante 30 minutos despues de 2 stop loss consecutivos en entrenamiento.
```

## Correcciones personalizadas

El motor debe poder sugerir entrenamiento conductual:

- reducir exposicion o margen tras una racha negativa, como gestion conductual y no como cambio de probabilidad de mercado
- esperar una vela o una confirmacion adicional
- limitar numero de operaciones por sesion
- pausar tras dos perdidas consecutivas
- comparar la operacion actual con errores repetidos del usuario
- pedir confirmacion extra si detecta operacion impulsiva
- recomendar observacion en vez de simulacion si el contexto emocional es malo

Ejemplo:

```text
La operacion tecnicamente es aceptable, pero coincide con un patron personal de riesgo: entrada impulsiva despues de perdida reciente. Recomendacion: reducir exposicion, pausar o esperar nueva confirmacion.
```

## Motor de probabilidad inicial

Primera version: scoring explicable por reglas.

No se empieza con machine learning complejo. Primero se necesita historico limpio.

Cada variable aporta:

- sesgo positivo
- sesgo negativo
- neutral
- alerta

El motor devuelve:

```json
{
  "tp_probability": 0.57,
  "sl_probability": 0.43,
  "risk_level": "medio-alto",
  "setup_grade": "B",
  "confidence": "media",
  "training_decision": "observar",
  "reasons": [
    "Tendencia corta favorable",
    "Funding elevado contra entradas long tardias",
    "Stop demasiado cerca para la volatilidad actual"
  ],
  "alerts": [
    "Evento macro relevante en menos de 2 horas"
  ]
}
```

## Aprendizaje continuo

El aprendizaje debe comparar recomendacion contra resultado.

Preguntas clave:

- Cuando el sistema da 60% de probabilidad, acierta cerca del 60%?
- Que variables estan sobrevaloradas?
- Que variables anticipan mejor los fallos?
- Que setups parecen buenos pero fallan en ciertos horarios?
- Que combinaciones de condiciones generan peor PnL?
- Que recomendaciones deberian volverse mas conservadoras?

## Ciclo infinito de mejora

El proposito final del sistema es mejorar continuamente la calidad de sus conclusiones y recomendaciones de probabilidad.

Cada operacion debe recorrer este ciclo:

1. Propuesta del usuario.
2. Analisis pre-operacion.
3. Probabilidades estimadas.
4. Recomendacion de parametros.
5. Simulacion.
6. Resultado real.
7. Comparacion entre prediccion y resultado.
8. Calibracion del motor.
9. Ajuste de recomendaciones futuras.

El sistema no debe limitarse a guardar si una operacion gano o perdio. Debe medir la calidad de la prediccion.

Preguntas clave despues de cada operacion:

- La probabilidad de TP estaba sobreestimada o infraestimada?
- La probabilidad de SL estaba bien calibrada?
- El riesgo estimado coincidio con el comportamiento real?
- El stop propuesto era razonable para la volatilidad?
- El take profit era realista?
- El apalancamiento recomendado fue adecuado?
- El DCA mejoro o empeoro la entrada?
- La salida parcial mejoro o redujo el resultado?
- Esperar una orden de inicio habria mejorado la probabilidad?
- El usuario siguio o no siguio el plan?
- La emocion declarada afecto el resultado?
- Que variable explico mejor el desenlace?
- Que variable parecia importante pero no aporto valor?

## Medicion del error de prediccion

Cada recomendacion debe generar metricas de evaluacion.

Metricas iniciales:

- acierto direccional: si el resultado favorecio la tesis long/short
- acierto de evento: si llego a TP, SL o rango
- error de probabilidad: diferencia entre probabilidad estimada y resultado binario
- Brier score para calibracion probabilistica
- desviacion entre riesgo estimado y perdida/MAE real
- desviacion entre objetivo estimado y MFE real
- calidad del parametro sugerido
- calidad del plan DCA
- calidad de las ordenes de inicio

Ejemplo:

```text
El sistema estimo TP 65%, pero la operacion llego a SL.
No significa automaticamente que el sistema fallo: una probabilidad del 65% admite perdidas. Pero si muchas operaciones del grupo 60-70% fallan mas de lo esperado, el sistema esta mal calibrado.
```

## Calibracion por grupos

El sistema debe revisar grupos de operaciones, no solo casos aislados.

Agrupaciones utiles:

- probabilidad estimada: 40-50%, 50-60%, 60-70%, etc.
- activo
- long/short
- apalancamiento
- ratio riesgo/beneficio
- volatilidad
- funding bajo/medio/alto
- open interest subiendo/bajando
- horario
- usuario
- estado emocional
- evento macro cercano/no cercano

Ejemplo:

```text
Las operaciones long con probabilidad estimada 60-70%, funding alto y OI subiendo solo alcanzan TP el 43% de las veces. El motor debe penalizar ese contexto.
```

## Ajuste progresivo del motor

La primera fase debe usar reglas explicables. Con historico suficiente, el motor puede ajustar pesos.

Tipos de ajuste:

- aumentar peso de variables que anticipan mejor el resultado
- reducir peso de variables poco utiles
- penalizar combinaciones peligrosas
- personalizar reglas por usuario
- ajustar probabilidades por calibracion historica
- detectar condiciones en las que el sistema tiene baja confianza

El sistema debe distinguir:

- mala prediccion
- buena prediccion con resultado desfavorable posible
- mala ejecucion del usuario
- evento externo inesperado
- datos insuficientes

## Objetivo matematico

El objetivo no es alcanzar 100% de acierto. Eso seria irreal.

El objetivo es:

- mejorar la calibracion probabilistica
- reducir recomendaciones de baja calidad
- identificar mejores condiciones de entrada
- minimizar riesgo relativo
- aumentar esperanza matematica de las operaciones simuladas
- mejorar disciplina y ejecucion por usuario

La pregunta central del sistema debe ser:

```text
Con los datos disponibles y el historial acumulado, que decision tiene mejor esperanza ajustada por riesgo para esta operacion concreta?
```

## Memoria del sistema

El sistema debe tener memoria operativa:

- historico completo de recomendaciones
- historico completo de resultados
- evolucion de acierto del motor
- evolucion de acierto por usuario
- cambios de pesos del motor
- versiones del motor
- explicacion de por que una recomendacion futura cambia respecto a una anterior

Ejemplo:

```text
Antes el sistema aceptaba longs con funding alto si la tendencia era positiva. Tras 87 operaciones, esa combinacion muestra peor resultado del esperado. Nueva recomendacion: exigir mejor confirmacion de delta comprador o tratar el funding extremo como advertencia de entrada tardia.
```

## Calibracion

El sistema no solo mide acierto o fallo. Tambien calibra probabilidades.

Ejemplo:

- Si todas las operaciones con probabilidad TP 60-65% solo ganan 45%, el motor esta siendo optimista.
- Si operaciones con funding extremo fallan mas de lo esperado, el peso del funding aumenta.
- Si el usuario pierde mas al aumentar exposicion tras rachas negativas, el motor lo trata como senal conductual, no como menor probabilidad direccional del mercado.
- Si el usuario falla mas cuando declara frustracion o exceso de confianza, el motor reduce confianza o recomienda pausa.

## Interfaz recomendada

Pantalla simple:

1. Resumen de operacion.
2. Resultado del analisis.
3. Razones principales.
4. Alertas.
5. Estado emocional declarado.
6. Boton para registrar recomendacion.
7. Historial de recomendaciones y resultados.
8. Panel de aprendizaje personal.

Graficas:

- Solo una grafica principal de precio.
- El resto debe estar resumido en texto, puntuaciones y alertas.

## Proximo hito tecnico

Crear persistencia local y el primer motor de analisis.

Entregables:

- Base de datos SQLite.
- Tabla de usuarios.
- Autenticacion simple con nombre de usuario y contrasena.
- Flujo de analisis pre-operacion obligatorio.
- Endpoint para analizar propuesta antes de abrir operacion.
- Endpoint para crear operacion.
- Endpoint para crear plan de ordenes simuladas.
- Endpoint para registrar recomendacion.
- Endpoint para cerrar operacion.
- Endpoint para seleccionar usuario activo.
- Tabla de recomendaciones.
- Tabla de resultados.
- Primer score explicable usando variables disponibles actualmente:
  - distancia a stop
  - distancia a take profit
  - ratio riesgo/beneficio
  - apalancamiento
  - volatilidad simple del historico local
  - direccion
  - precio actual vs entrada
  - confianza declarada por usuario
  - estado emocional declarado
  - cumplimiento del plan
  - entrada unica vs DCA
  - salida unica vs salida parcial
