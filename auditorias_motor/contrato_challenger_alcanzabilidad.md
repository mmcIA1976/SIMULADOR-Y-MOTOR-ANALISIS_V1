# Contrato del challenger de alcanzabilidad - E1.5

Fecha: 2026-07-25
Estado: VIGENTE PARA INVESTIGACION
Champion congelado: `rules-v0.12.1-liquidations-readable`
Challenger: `challenger-v0.1-contract-only`

## 1. Objetivo

El challenger estima, antes de abrir la operacion y usando solo informacion
disponible en ese instante, tres sucesos mutuamente excluyentes:

- `TP_first`: TP es la primera barrera alcanzada dentro del horizonte.
- `SL_first`: SL es la primera barrera alcanzada dentro del horizonte.
- `expiry_unresolved`: vence el horizonte sin tocar TP ni SL.

Los resultados principales visibles son:

```text
P(TP_first | plan, datos pre-trade)
P(SL_first | plan, datos pre-trade)
```

La expiracion se conserva internamente y debe mostrarse como contexto. Las tres
probabilidades deben sumar exactamente uno. TP y SL son probabilidades
incondicionales dentro del horizonte; no se renormalizan ocultando expiraciones.

## 2. Alcance y tiempo cero

El tiempo cero es `analysis_at`. El plan debe incluir:

- par;
- lado;
- entrada;
- TP;
- SL;
- uno de los tres marcos vigentes;
- duracion concreta dentro de ese marco.

Los rangos autorizados son:

- `intraday_short`: 30 minutos a 4 horas;
- `intraday_wide`: 4 a 24 horas;
- `short_swing`: 1 a 7 dias.

Una orden pendiente que no se activa queda en `expiry_unresolved`. No se
reinterpreta retrospectivamente el analisis desde su eventual activacion.

## 3. Geometria e invariantes

Para long debe cumplirse `SL < entrada < TP`. Para short debe cumplirse
`TP < entrada < SL`. Cualquier otra geometria bloquea el calculo.

Las distancias basicas usan log-retornos positivos y simetricos:

```text
long:
  d_tp = ln(TP / entrada)
  d_sl = ln(entrada / SL)

short:
  d_tp = ln(entrada / TP)
  d_sl = ln(SL / entrada)
```

Las mismas distancias economicas producen las mismas variables para long y
short. Las variables de distancia, horizonte y volatilidad no pueden
sustituirse por etiquetas cualitativas.

El artefacto debe cumplir estos invariantes manteniendo las demas variables:

- aumentar `d_tp` no puede aumentar `P(TP_first)`;
- aumentar `d_sl` no puede aumentar `P(SL_first)`;
- aumentar la duracion no puede aumentar `P(expiry_unresolved)`.

Para el baseline lineal se fuerzan mediante el orden de coeficientes entre
logits. Tambien se bloquean interacciones ocultas con entrada, TP, SL u
horizonte. Una futura interaccion debe declarar sus dependencias y demostrar
monotonicidad con pruebas propias antes de incorporarse.

Antes de incorporar volatilidad se registrara su formula exacta, ventana,
muestreo, anualizacion y tratamiento de huecos. El ATR actual no se hereda
porque E1.5.1 lo clasifico como variante de implementacion.

## 4. Arquitectura probabilistica inicial

El baseline investigable es una regresion multinomial interpretable de tres
clases. No se hereda ningun peso, threshold, cap o gate del champion.

Para cada resultado `k`:

```text
x'_j = (x_j - centro_j) / escala_j
z_k  = intercepto_k + sum_j(coeficiente_jk * x'_j)
p_k  = exp(z_k / T) / sum_m(exp(z_m / T))
```

`T` es un parametro de calibracion aprendido exclusivamente en una particion
posterior a entrenamiento y anterior al test final. La eleccion de temperature
scaling es una hipotesis metodologica sencilla, no una prueba de calibracion
para nuestros datos. Debe compararse con el modelo sin calibrar y abandonarse
si no mejora el holdout.

El modelo multinomial se elige como primer baseline por:

- producir una distribucion coherente de tres clases;
- hacer visible cada coeficiente y contribucion;
- permitir regularizacion y ablation reproducibles;
- ser mas facil de refutar que una arquitectura opaca.

No se afirma que sea la arquitectura definitiva. Si un modelo de riesgos
competitivos o supervivencia trata mejor censura y tiempo hasta barrera, sera
un challenger posterior con contrato y version propios.

## 5. Admisibilidad de variables

Una variable solo puede llegar al modelo cuando su dato o calculo figura como
admitido en la matriz usada para entrenar el artefacto. El artefacto guarda el
SHA-256 exacto de esa matriz. Esto autoriza calcular la variable, no su
coeficiente: el uso predictivo pertenece al modelo completo y debe superar el
protocolo temporal.

Estados:

- `data_allowed_not_predictive`: dato utilizable con control de calidad.
- `calculation_allowed_nonpredictive`: transformacion calculable sin afirmar
  poder predictivo.
- `research`: puede estudiarse, no generar probabilidades sombra.
- `shadow`: regla predictiva que puede evaluarse en paralelo.
- `production`: supero todos los gates y tiene aprobacion humana.
- `suspended` o `retired`: queda bloqueada.

Los datos oficiales acreditan el significado del campo, no su capacidad
predictiva. Cada feature derivada necesita ficha propia aunque sus datos
subyacentes sean fiables.

## 6. Datos ausentes y calidad

Cada valor registra fuente, timestamp del proveedor, timestamp de captura,
unidad, calidad y antiguedad maxima. Si una variable obligatoria:

- falta;
- no es finita;
- llega del futuro;
- esta obsoleta;
- tiene calidad degradada;
- o no esta admitida;

se bloquea toda la prediccion. No se imputa cero, neutralidad ni un promedio
silencioso. Otro modelo reducido solo puede utilizarse si fue entrenado,
calibrado y validado como artefacto independiente.

## 7. Etiquetas posteriores

El outcome se reconstruye con datos posteriores sin modificar el snapshot:

- primera barrera y timestamp;
- expiracion completa observada;
- no activacion de orden pendiente;
- ambiguedad si TP y SL aparecen en la misma vela sin orden resoluble;
- censura por falta de datos o cierre manual previo a barrera;
- calidad de reconstruccion.

Solo casos con outcome no ambiguo entran en el baseline multinomial. Casos
ambiguos y censurados se conservan y se informan; no se fuerzan a TP, SL o
expiracion. La posible seleccion introducida al excluirlos debe medirse.

## 8. Traza por prediccion

Cada evaluacion registra:

- plan completo y tiempo cero;
- versiones de challenger, modelo y esquema;
- SHA-256 de la matriz de admisibilidad;
- variables crudas y normalizadas;
- regla, fuente, unidad, frescura y calidad de cada variable;
- interceptos, coeficientes y contribuciones a cada logit;
- logits antes de calibracion;
- metodo y version de calibracion;
- logits calibrados;
- las tres probabilidades y su masa total;
- variables bloqueadas o no evaluadas y motivo;
- efecto en produccion, siempre `none` durante sombra.

La explicacion visible debe generarse desde esta traza.

## 9. Artefacto obligatorio

Sin artefacto no hay probabilidad. El artefacto contiene como minimo:

- version y esquema;
- estado `shadow` o `production`;
- corte temporal de entrenamiento;
- identificador de dataset;
- SHA-256 de matriz y codigo;
- pares y horizontes validados;
- lista ordenada de variables y reglas;
- centro y escala aprendidos solo en train;
- interceptos y coeficientes;
- regularizacion e hiperparametros;
- calibrador y particion utilizada;
- informe de validacion;
- aprobaciones y fecha;
- motivo de retirada o sustitucion.

`challenger_engine.py` aplica este bloqueo de forma ejecutable.

## 10. Separacion del champion

El challenger:

- no se importa desde `app.py`;
- no escribe recomendaciones ni operaciones;
- no modifica TP, SL, grado, decision ni textos del champion;
- no reutiliza sus scores como features;
- solo puede compararse mediante una estructura separada;
- puede desactivarse eliminando la seleccion del artefacto sombra.

La comparacion sombra no crea operaciones ficticias por cada analisis. Compara
predicciones pre-trade con outcomes auditados cuando estos existan.

## 11. Fundamento y limites

- Brier (1950) respalda evaluar previsiones probabilisticas, no este modelo.
- Gneiting y Raftery (2007) respaldan proper scoring rules, no estos features.
- Dimitriadis, Gneiting y Jordan respaldan diagnosticos reproducibles de
  calibracion, no acreditan calibracion actual.
- Guo et al. (2017) documentan temperature scaling; su evidencia procede de
  otros dominios y solo justifica investigarlo.

Referencias:

- https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2
- https://doi.org/10.1198/016214506000001437
- https://arxiv.org/abs/2008.03033
- https://proceedings.mlr.press/v70/guo17a.html

## 12. Estado actual

La infraestructura es `contract-only`. No existe todavia un artefacto entrenado
y aprobado. Por tanto, el resultado correcto hoy es:

```text
status = blocked
block_code = model_artifact_absent
probabilities = null
```

Esto es una proteccion deliberada contra volver a presentar un score como
probabilidad.
