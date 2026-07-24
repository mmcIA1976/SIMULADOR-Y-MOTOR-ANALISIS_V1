# Contrato vinculante - Fase 1 del motor de analisis

Fecha de formalizacion: 2026-07-24
Estado: VIGENTE
Precedencia: maxima para cualquier trabajo sobre el motor de analisis

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

- probabilidad de TP;
- probabilidad de SL.

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

- TP, SL, cierre manual o expiracion/no resolucion;
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

Debe tratarse como referencia historica congelada, no como base valida para las
Fases 2 o 3.

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

## 18. Decisiones pendientes de confirmacion

Solo quedan abiertas estas definiciones de producto:

1. Semantica exacta de los dos porcentajes cuando no se toca TP ni SL dentro del
   horizonte.
2. Horizonte operativo definitivo de la Fase 1.
3. Universo inicial de activos para construir y validar el primer modelo.

Estas decisiones deben resolverse antes de definir el modelo probabilistico
challenger. No autorizan desviaciones mientras permanecen abiertas.
