# Contrato vinculante - Fase 1 del motor de analisis

Fecha de formalizacion: 2026-07-24
Estado: VIGENTE
Precedencia: maxima para cualquier trabajo sobre el motor de analisis

## 0. Prioridad operativa vigente

Desde el 2026-07-27, la ejecucion de este contrato se rige por
`HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md`.

La prioridad unica es mejorar el motor de analisis actual. La version
productiva se conserva congelada como baseline mientras se documentan,
corrigen, desactivan o incorporan sus reglas de forma versionada. Esto no
significa abandonar el motor actual ni crear un proyecto independiente.

El motor de aprendizaje y cualquier acumulacion de casos destinada a
aprendizaje quedan pausados hasta que exista una revision rigurosa del motor de
analisis. La validacion empirica posterior sigue siendo obligatoria, pero no
puede preceder a la definicion e implementacion de reglas y formulas.

## 1. Motivo

Este documento materializa las instrucciones expresas del propietario del
proyecto y corrige cualquier interpretacion anterior incompatible con ellas.

No es una propuesta, una lista de deseos ni una especificacion provisional. Es
el criterio obligatorio para analizar, disenar, implementar, probar, auditar y
aprobar la Fase 1.

Cuando otro documento, comentario de codigo, implementacion anterior o
conclusion tecnica contradiga este contrato, prevalece este contrato y la
contradiccion debe registrarse.

## 2. Proyecto completo

### Fase 1 - Analizar la operacion propuesta por el usuario

El usuario define como minimo:

- activo;
- lado long o short;
- entrada;
- take profit;
- stop loss;
- horizonte temporal.

La aplicacion recoge los datos disponibles en ese instante, aplica diferentes
metodos de analisis mediante reglas documentadas y devuelve dos porcentajes
principales:

- probabilidad preoperacion de alcanzar el TP;
- probabilidad preoperacion de alcanzar el SL.

La Fase 1 no elige todavia la operacion por el usuario y no ejecuta dinero real.

### Fase 2 - Proponer la mejor operacion

La aplicacion genera y compara candidatos por activo, lado, entrada, TP, SL y
horizonte. Debe poder concluir que no existe una operacion suficientemente
buena. La seleccion utilizara el mismo nucleo riguroso construido en la Fase 1.

### Fase 3 - Bot de trading automatico

La aplicacion analiza, propone, ejecuta y gestiona operaciones reales con
controles estrictos de riesgo, ejecucion, recuperacion, monitorizacion y
trazabilidad.

Ninguna fase posterior puede construirse responsablemente sobre un motor de
Fase 1 no validado.

## 3. Objetivo exacto de la Fase 1

Construir un motor capaz de transformar:

```text
plan del usuario
+ datos pre-trade actuales e historicos disponibles
+ reglas tecnicas, cuantitativas y financieras documentadas
----------------------------------------------------------------
probabilidad TP + probabilidad SL + explicacion completamente auditable
```

Los porcentajes deben corresponder al plan concreto. Deben depender, cuando
proceda, de:

- distancia de entrada a TP;
- distancia de entrada a SL;
- horizonte;
- volatilidad;
- estructura y regimen;
- volumen y flujo;
- derivados;
- liquidez y ejecucion;
- condiciones adicionales demostrablemente utiles.

No se permite presentar como probabilidad una suma arbitraria de puntos.

### Naturaleza preoperacion

El analisis se realiza antes de abrir la operacion. En ese instante no se ha
alcanzado TP ni SL. Los dos porcentajes son estimaciones sobre acontecimientos
futuros del plan propuesto, calculadas exclusivamente con informacion
disponible hasta el momento del analisis.

El resultado real solo existe posteriormente. Cuando el mercado alcance TP,
alcance SL o finalice el horizonte sin resolver el plan, ese outcome se
vinculara al analisis original para aprendizaje. En ordenes pendientes debe
distinguirse entre `no_entry` y `expiry_after_entry`. La observacion posterior
no puede alterar retrospectivamente los datos ni las reglas preoperacion.

### Marcos temporales vigentes

La Fase 1 conserva los tres marcos temporales actuales:

- `intraday_short`: intradia corto, 30 minutos-4 horas;
- `intraday_wide`: intradia amplio, 4-24 horas;
- `short_swing`: swing corto, 1-7 dias.

Cada regla debe declarar en cuales de estos marcos es valida. No se adopta un
horizonte general de 3-60 horas.

### Universo de pares

El motor debe ser valido para todos los pares admitidos por la aplicacion. No
se construira un modelo exclusivamente para BTC.

Toda regla activa debe:

- utilizar unidades comparables entre pares;
- declarar cualquier normalizacion necesaria;
- demostrar validez en los pares donde se aplique;
- bloquearse de forma explicita cuando falten datos fiables;
- evitar parametros ocultos especificos de BTC.

Una regla contextual puede comportarse de forma distinta por mercado si esa
diferencia esta documentada, versionada y validada. No puede presentarse como
regla general si solo ha sido comprobada en un par.

## 4. Flujo obligatorio del analisis

```text
1. Capturar datos fiables y sincronizados
2. Validar disponibilidad, frescura, fuente y unidades
3. Calcular variables cuantificables
4. Ejecutar reglas atomicas
5. Ejecutar reglas contextuales y combinadas
6. Aplicar reglas de bloqueo o exclusion
7. Integrar evidencia sin doble conteo
8. Calcular TP y SL mediante un metodo probabilistico documentado
9. Incorporar costes y calidad de ejecucion sin falsear la direccion
10. Guardar la traza completa
11. Mostrar resultado y explicacion
12. Vincular posteriormente el resultado real para aprendizaje
```

## 5. Prohibiciones expresas

Queda prohibido:

- inventar umbrales o pesos por parecer razonables;
- convertir votos alcistas/bajistas en porcentajes;
- llamar probabilidad a un score no calibrado;
- introducir una regla sin fuente, formula y trazabilidad;
- asumir que un indicador habitual es valido para este motor;
- sumar varias veces informacion correlacionada;
- utilizar etiquetas post-trade como variables pre-trade;
- modificar produccion a partir de pocos casos;
- elegir una formula porque produce resultados visualmente convincentes;
- ocultar falta de datos con valores neutrales que aparenten evidencia;
- ampliar el alcance con funciones secundarias antes de validar el nucleo;
- presentar una comprobacion de software como validacion financiera;
- interpretar una fuente oficial de datos como respaldo de un peso predictivo;
- aplicar automaticamente conclusiones del motor de aprendizaje.

## 6. Contrato obligatorio de cada regla

Toda regla debe existir en un registro versionado con:

- identificador estable;
- nombre;
- version;
- estado;
- tipo de regla;
- fecha y motivo de incorporacion;
- fuente teorica, manual, investigacion o evidencia interna;
- afirmacion exacta que la fuente respalda;
- limite de lo que la fuente no respalda;
- formula exacta;
- variables de entrada;
- fuente de cada variable;
- unidad;
- frecuencia y antiguedad maxima;
- activo y mercado;
- horizontes aplicables;
- condiciones de activacion;
- condiciones de no aplicacion;
- resultado intermedio;
- efecto permitido sobre TP;
- efecto permitido sobre SL;
- interacciones;
- caps, bloqueos y prioridades;
- pruebas unitarias;
- prueba de coherencia;
- evidencia historica;
- tamano y composicion de muestra;
- validacion temporal independiente;
- decision actual: investigar, sombra, activa, limitada, suspendida o retirada.

Una regla sin esta ficha no puede afectar al resultado.

## 7. Tipos de reglas

### Regla atomica

Evalua una condicion individual, por ejemplo distancia del TP normalizada por
volatilidad.

### Regla contextual

Solo tiene validez en determinados activos, horizontes o regimenes.

### Regla combinada

Se activa cuando coincide un conjunto declarado de reglas o condiciones. Debe
demostrar valor incremental frente a sus componentes por separado.

### Regla de bloqueo

Impide o limita el uso de otras reglas o del resultado completo cuando falla
una condicion critica de datos, riesgo o ejecutabilidad.

### Regla de presentacion

Explica o resume, pero no puede modificar probabilidades.

## 8. Reglas combinadas e interacciones

Cada combinacion debe registrar:

- identificador propio;
- reglas padre;
- operador logico y orden de evaluacion;
- condiciones obligatorias y excluyentes;
- razon tecnica de la interaccion;
- efecto individual de cada componente;
- efecto incremental de la combinacion;
- posibles duplicidades;
- muestra de componentes aislados;
- muestra de la combinacion;
- comparacion mediante ablation;
- control de multiples hipotesis;
- validacion con datos posteriores.

No se permite buscar combinaciones ilimitadas hasta encontrar una que parezca
ganadora. Las hipotesis deben quedar registradas antes de evaluarse.

## 9. Traza obligatoria por analisis

No basta con guardar la salida final. Para cada analisis debe conservarse:

- identificador y version del motor;
- fecha y hora;
- plan completo;
- snapshot pre-trade inmutable;
- fuentes consultadas;
- timestamps de proveedor y captura;
- edad y calidad de cada dato;
- variables calculadas;
- reglas evaluadas;
- reglas no evaluadas y motivo;
- reglas activadas;
- reglas bloqueadas;
- resultado antes y despues de cada regla;
- contribucion exacta a TP y SL;
- reglas combinadas y padres que las activaron;
- interacciones y doble conteo evitado;
- caps y saturaciones;
- incertidumbre;
- resultado final;
- explicacion generada desde la misma traza.

La explicacion visible nunca puede contradecir la traza ejecutable.

## 10. Resultado posterior de la operacion

Cuando la operacion termine o venza su horizonte, debe enlazarse con:

- TP primero, SL primero, no entrada, expiracion posterior a entrada, cierre
  manual u otro estado censurado;
- primera barrera alcanzada;
- hora real del evento;
- precio real del evento;
- MFE;
- MAE;
- tiempo hasta TP, SL o expiracion;
- recorrido del precio;
- calidad de evidencia;
- comisiones;
- slippage;
- funding;
- PnL;
- retorno sin apalancar;
- retorno sobre margen;
- R-multiple.

Los cierres ambiguos deben conservar su ambiguedad y no forzarse a una etiqueta.

## 11. Funcion exacta del motor de aprendizaje

El motor de aprendizaje existe exclusivamente para valorar y mejorar el motor
de analisis mediante resultados auditados.

Estado operativo desde el 2026-07-27: PAUSADO. Esta seccion define su funcion
futura y no autoriza trabajo actual sobre aprendizaje. No existe nada fiable
que aprender de los porcentajes heuristicos actuales para asignar nuevos pesos.
Su reanudacion exige completar la hoja de ruta del motor y autorizacion expresa
del propietario.

Debe medir para cada regla y combinacion:

- numero de veces evaluada;
- numero de veces activada;
- contextos de activacion;
- distribucion de TP, SL y expiracion;
- calibracion con y sin la regla;
- discriminacion;
- impacto en EV neta;
- MFE y MAE;
- tiempo hasta barrera;
- efecto incremental;
- duplicidad con otras reglas;
- estabilidad por version;
- estabilidad por activo, lado, horizonte y regimen;
- incertidumbre estadistica.

Puede proponer:

- mantener;
- reducir influencia;
- aumentar influencia;
- modificar formula;
- limitar contexto;
- suspender;
- retirar.

No puede aplicar el cambio directamente. Toda propuesta debe crear un
challenger, probarse con datos posteriores e independientes y recibir
aprobacion humana antes de promocionarse.

## 12. Datos

Solo pueden utilizarse:

- datos disponibles antes o durante el instante del analisis;
- APIs publicas y gratuitas mientras no se autorice expresamente otra cosa;
- fuentes identificadas;
- unidades normalizadas;
- datos con timestamp, frescura y calidad conocidas;
- historico reconstruible sin look-ahead.

Cada proveedor acredita sus datos, no la interpretacion que haga el motor.

Cuando un dato no sea fiable:

- se marca ausente o degradado;
- se bloquean las reglas dependientes;
- no se sustituye silenciosamente por un valor neutral;
- se registra el impacto sobre la incertidumbre.

## 13. Metodos de analisis

Se investigaran todos los bloques para los que puedan obtenerse datos fiables,
incluidos los ya disponibles. Ningun bloque entra completo por aparecer en una
lista. Cada variable y regla supera individualmente el contrato de este
documento.

La arquitectura objetivo es:

```text
regimen
-> estructura y direccion
-> alcanzabilidad TP/SL
-> confirmacion de volumen y flujo
-> posicionamiento de derivados
-> riesgo de evento
-> ejecutabilidad y costes
-> probabilidades finales trazables
```

Patrones discrecionales, velas, Fibonacci, SMC, ICT, Elliott, Gann y similares
solo pueden incorporarse si se definen matematicamente, se reproducen de forma
consistente y demuestran valor incremental.

## 14. Estado real del motor actual

El champion `rules-v0.12.1-liquidations-readable` no cumple este contrato como
motor probabilistico:

- `tp_probability` es una suma heuristica;
- `sl_probability` se calcula en parte como residuo;
- varios pesos y umbrales son internos y no calibrados;
- existe una discontinuidad de cinco puntos demostrada por 872/873;
- no hay traza completa de contribucion por regla en cada analisis;
- el aprendizaje ha generado frenos manuales provisionales, no calibracion
  estadistica;
- las pruebas existentes verifican ejecucion, no validez financiera.

La version productiva concreta debe tratarse como referencia historica
congelada. La base de codigo del motor actual si es el objeto de mejora, pero
ninguna de sus reglas se considera valida por herencia. Las Fases 2 y 3 del
proyecto solo pueden apoyarse en una revision del motor que cumpla este
contrato.

## 15. Criterios de aceptacion de la Fase 1

La Fase 1 no se considera terminada hasta que:

1. Todas las reglas activas cumplen el contrato.
2. Toda salida es reproducible desde una traza guardada.
3. TP y SL tienen semantica matematica aprobada.
4. Distancias, horizonte y volatilidad respetan invariantes.
5. No existen discontinuidades no justificadas.
6. Se controla doble conteo.
7. Los datos pre-trade estan separados de outcomes y etiquetas.
8. Existe validacion walk-forward independiente.
9. Se publican Brier, log-loss y curvas de calibracion.
10. Se incluyen costes reales o estimaciones documentadas.
11. Se comparan champion y challenger.
12. El sistema sabe declarar evidencia insuficiente.
13. El aprendizaje puede atribuir resultados a reglas y combinaciones.
14. Ningun cambio llega a produccion sin aprobacion humana.

## 16. Control contra desviaciones

Antes de desarrollar una regla o modulo se debe responder por escrito:

1. Que problema de la Fase 1 resuelve?
2. Que dato fiable utiliza?
3. Que formula aplica?
4. Que fuente la respalda?
5. Como influye en TP y SL?
6. Como se registrara esa influencia?
7. Como la evaluara el aprendizaje?
8. Como se evitara doble conteo?
9. Que prueba puede refutarla?
10. Que criterio permite retirarla?

Si alguna respuesta falta, el desarrollo queda bloqueado.

## 17. Decisiones expresamente fijadas

- El objetivo central son los porcentajes TP y SL.
- El analisis se realiza con datos recogidos por API en ese momento y con
  historico disponible sin leakage.
- Las reglas deben ser solidas, documentadas, registradas y trazables.
- Se admiten reglas atomicas, contextuales, combinadas y de bloqueo.
- El aprendizaje valora cada regla y puede proponer modificarla o retirarla.
- No existe prisa que justifique rebajar el rigor.
- La Fase 1 es el nucleo de las Fases 2 y 3.
- El objetivo es maxima precision posible con incertidumbre honesta, no
  apariencia de precision.
- Las fuentes de pago quedan fuera mientras no exista autorizacion expresa.

## 18. Decisiones de producto confirmadas

1. El analisis es previo a la operacion. TP y SL son estimaciones sobre
   acontecimientos futuros, no resultados ya observados.
2. Se mantienen `intraday_short`, `intraday_wide` y `short_swing` con sus
   duraciones actuales.
3. Las reglas deben ser validas para todos los pares con los que trabaja la
   aplicacion; no se limitan a BTC.

No quedan dudas abiertas sobre estos tres puntos.
