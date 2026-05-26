# Sistema de entrenamiento de trading

Este proyecto parte del simulador visual actual y evolucionara hacia un laboratorio de entrenamiento para operaciones simuladas con datos reales de mercado.

El objetivo no es ejecutar ordenes reales ni prometer resultados, sino ayudar a estudiar condiciones, decisiones, riesgo y resultados para mejorar el criterio operativo antes de invertir capital real.

## Vision

Crear una app sencilla para el usuario, pero con una capa interna cada vez mas rica de analisis:

- Registrar cada operacion simulada.
- Guardar el contexto de mercado en el momento de entrada.
- Medir riesgo, recorrido, volatilidad y resultado.
- Aprender de cada victoria, error o cierre prematuro.
- Detectar patrones de condiciones favorables y desfavorables.
- Convertir el historico en entrenamiento practico y revisable.

## Principios

- No ejecutar operaciones reales.
- No usar claves API privadas en la primera fase.
- Separar claramente simulacion, analisis y entrenamiento.
- Priorizar explicabilidad sobre automatismos opacos.
- Guardar datos estructurados desde el principio.
- Mantener la interfaz simple aunque el analisis interno crezca.

## Fase 1: Registro de operaciones

Convertir el simulador actual en una app que pueda crear, seguir y cerrar operaciones simuladas.

Datos minimos por operacion:

- activo
- direccion: long o short
- entrada
- margen
- apalancamiento
- stop loss
- take profit
- precio actual durante la vida de la operacion
- timestamps de cada actualizacion
- estado: abierta, stop loss, take profit, cierre manual
- PnL final
- duracion
- comentario del usuario
- motivo de entrada
- emocion o confianza percibida

Resultado esperado:

- Historial local de operaciones.
- Ficha individual por operacion.
- Exportacion futura a CSV o base de datos.

## Fase 2: Variables de mercado

Agregar variables reales que describan el contexto de cada entrada.

Variables candidatas:

- volatilidad reciente
- rango de precio en ultimos minutos/horas
- distancia a maximos y minimos recientes
- tendencia de corto plazo
- volumen si la API lo permite
- momentum
- desviacion del precio respecto a medias moviles
- relacion riesgo/beneficio
- distancia porcentual al stop loss
- distancia porcentual al take profit
- ratio entre posible perdida y posible beneficio

Resultado esperado:

- Cada operacion queda acompañada de un snapshot del mercado.
- El usuario puede comparar operaciones ganadoras y perdedoras con contexto.

## Fase 3: Motor de evaluacion de riesgo

Crear una puntuacion explicable antes de abrir la operacion simulada.

Ejemplos de senales:

- Riesgo bajo: stop cercano, volatilidad controlada, ratio riesgo/beneficio favorable.
- Riesgo medio: condiciones mixtas.
- Riesgo alto: stop demasiado lejano, volatilidad elevada, tendencia contraria.

Importante:

La puntuacion no debe presentarse como recomendacion financiera. Debe funcionar como herramienta de entrenamiento y revision.

## Fase 4: Aprendizaje de resultados

Analizar el historico acumulado.

Preguntas que el sistema debe poder responder:

- En que condiciones se gana mas a menudo.
- En que condiciones se pierde mas.
- Que activos funcionan mejor en simulacion.
- Que apalancamientos generan mas errores.
- Si los stops suelen estar demasiado cerca o demasiado lejos.
- Si el usuario tiende a operar mejor en long o short.
- Que setups tienen mejor relacion entre probabilidad y riesgo.

Resultado esperado:

- Panel de aprendizaje.
- Estadisticas por setup.
- Reglas sugeridas basadas en el propio historico.

## Fase 5: Entrenamiento guiado

Convertir el analisis en ejercicios.

Ideas:

- Modo practica: elegir entrada, stop y take profit sobre datos reales.
- Modo revision: estudiar operaciones pasadas y clasificar errores.
- Modo desafio: operar solo si se cumplen reglas predefinidas.
- Modo diario: resumen de decisiones, aciertos, errores y mejoras.

## Arquitectura inicial propuesta

Frontend:

- HTML, CSS y JavaScript nativo en la primera version.
- Canvas para graficas.
- Paneles sencillos para operacion, historico y aprendizaje.

Backend:

- Python con servidor web.
- API publica de mercado.
- Persistencia centralizada.
- Modo local solo para desarrollo.
- Despliegue preparado para compartir la app con varios usuarios.

Datos:

- Tabla de usuarios.
- Tabla de operaciones.
- Tabla de ticks/precios por operacion.
- Tabla de snapshots de mercado.
- Tabla de notas/revisiones.
- Tabla de metricas calculadas.

## Primer gran hito

El siguiente paso recomendable es construir la base de datos local y el registro de operaciones.

Objetivo del hito:

1. Crear una operacion simulada desde la app.
2. Guardarla en SQLite.
3. Registrar automaticamente cada precio consultado.
4. Cerrar la operacion por stop loss, take profit o cierre manual.
5. Mostrar un historial de operaciones.

Este hito convierte el simulador en una herramienta real de entrenamiento.

## Direccion de producto

La interfaz no debe llenarse de graficas. El valor principal sera una conclusion simple basada en un analisis profundo:

- probabilidad estimada de TP
- probabilidad estimada de SL
- riesgo
- calidad del setup
- confianza
- razones principales
- alertas

Cada recomendacion debe quedar guardada para compararse despues con el resultado real de la operacion simulada. El aprendizaje nace de esa comparacion.

## Entrenamiento multiusuario

El sistema debe permitir que varios usuarios participen abriendo operaciones simuladas. Esto aumenta el numero de casos, acelera el aprendizaje y permite comparar patrones por perfil.

Se debe distinguir entre:

- aprendizaje individual de cada usuario
- aprendizaje agregado anonimo
- recomendaciones personalizadas
- recomendaciones generales del sistema

Esto exige introducir usuarios desde el primer diseno de base de datos.

El acceso inicial sera simple:

- nombre de usuario
- contrasena
- sesion web

No se usara un selector local de usuario en produccion. Cada usuario accedera con sus credenciales.

## Analisis antes de simular

Antes de abrir cualquier simulacion, el sistema debe analizar la propuesta del usuario. La simulacion no empieza desde una decision vacia, sino desde una recomendacion registrada.

El flujo sera:

1. El usuario propone activo, direccion, entrada, margen, apalancamiento, stop loss y take profit.
2. El motor analiza datos de mercado y contexto disponible.
3. El sistema devuelve probabilidades, riesgo, confianza y recomendacion.
4. Si el usuario lo pide, propone ajustes de entrada, stop, take profit, margen y apalancamiento.
5. El usuario decide si simula la idea original o la idea ajustada.
6. Al cerrar la operacion, se compara el resultado real con la recomendacion inicial.

Este flujo es clave para aprender no solo del resultado, sino de la calidad de la prediccion previa.

## DCA y ordenes simuladas

El sistema debe contemplar estrategias de entrada y salida por tramos.

Tipos:

- entrada inmediata
- entrada limite
- entrada por ruptura
- entrada condicionada
- DCA de entrada
- salida unica
- salida parcial
- DCA de salida

El DCA debe ser planificado antes de la simulacion. No debe usarse como reaccion emocional para promediar perdidas sin limite.

El motor debe evaluar:

- si el DCA mejora la entrada media
- si aumenta demasiado el riesgo total
- si el stop global sigue siendo razonable
- si las salidas parciales mejoran el control emocional
- si reducen demasiado el beneficio esperado
- si esperar una orden de inicio mejora la probabilidad

Cada tramo ejecutado debe quedar registrado para comparar despues la estrategia propuesta contra el resultado real.

## Estudio emocional por usuario

El sistema debe estudiar tambien el comportamiento de cada usuario. En trading, el factor emocional puede explicar errores que el analisis tecnico no detecta.

Aunque una cuenta simulada no reproduce el estres de una cuenta real, si puede revelar patrones:

- exceso de confianza
- frustracion tras perdidas
- operaciones impulsivas
- sobreapalancamiento
- cierre temprano de ganadoras
- modificacion de stop loss sin plan
- sobreoperacion

El registro emocional no se pedira antes de abrir la operacion. Se recogera al cerrar la operacion, cuando el usuario pueda valorar como actuo realmente.

Al cierre se podra preguntar:

- emocion al cerrar
- si cumplio el plan
- si movio stop o take profit
- si cerro por miedo, impulso o plan
- aprendizaje percibido

Esto permitira generar recomendaciones personalizadas, no solo tecnicas.

## Universo inicial de activos

El sistema se centrara inicialmente en crypto.

Prioridad:

- BTC
- ETH
- principales pares USDT
- activos relevantes dentro del top 1000 por capitalizacion o liquidez

La disponibilidad real dependera de que el activo tenga datos suficientes en las APIs gratuitas conectadas.

## Fuentes iniciales gratuitas

En la primera fase se integraran fuentes gratuitas o con planes gratuitos razonables que permitan conectividad recurrente:

- Binance public API para precio, velas, volumen, order book y derivados disponibles.
- CoinGecko public/free API para ranking, capitalizacion y universo de activos.
- APIs gratuitas de noticias/sentimiento cuando permitan uso recurrente.
- Fuentes macro/calendario gratuitas o con acceso demo si son estables.

Las fuentes premium quedaran preparadas como conectores futuros, pero no bloquearan el primer desarrollo.

## Ciclo infinito de mejora

El proyecto debe funcionar como un sistema de mejora continua.

Cada operacion produce:

- una prediccion
- una recomendacion
- una simulacion
- un resultado
- un error o acierto de calibracion
- una oportunidad de ajustar futuras conclusiones

El objetivo no es acertar siempre, sino mejorar la calidad probabilistica del motor:

- que las operaciones estimadas al 60% ganen aproximadamente un 60% en muestras suficientes
- que el sistema detecte cuando esta siendo demasiado optimista
- que aprenda que variables pesan mas en cada contexto
- que personalice recomendaciones segun cada usuario
- que reduzca setups de baja esperanza

Este ciclo es el proposito final del sistema. Sin comparacion entre prediccion y resultado, el simulador no aprende.

Ver tambien:

- `ESPECIFICACION_MOTOR_ANALISIS.md`
