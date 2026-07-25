# Protocolo de validacion del challenger - E1.5.4

Fecha: 2026-07-25
Estado: PREREGISTRADO

## 1. Unidad experimental

Una fila es un analisis pre-trade inmutable y su outcome posterior auditable.
No se mezclan reanalisis del mismo snapshot como observaciones independientes.
El grupo temporal evita que snapshots proximos de una misma situacion queden
repartidos entre train y test.

## 2. Elegibilidad del dataset

Cada caso debe contener:

- plan valido y duracion concreta;
- snapshot anterior o igual a `analysis_at`;
- version de todas las reglas y datos;
- outcome TP, SL o expiracion sin ambiguedad;
- cobertura completa hasta primera barrera o vencimiento;
- par y horizonte admitidos;
- identificador para detectar duplicados.

Se excluye del entrenamiento, pero se conserva en el informe:

- cierre manual antes de resolver barreras;
- TP y SL dentro de la misma vela sin orden temporal;
- huecos que impiden conocer la primera barrera;
- snapshot contaminado con informacion posterior;
- observacion incompleta del horizonte.

## 3. Particion temporal

El orden siempre es cronologico:

```text
train -> calibracion -> test final
```

El test final permanece sellado hasta fijar variables, formulas,
hiperparametros y calibrador. Dentro de train se usa rolling origin para
seleccion. Nunca se barajan observaciones temporalmente.

Los centros, escalas, imputaciones prohibidas, coeficientes, hiperparametros y
temperature se aprenden sin mirar el test.

## 4. Baselines

Todo challenger se compara contra:

- frecuencia historica de train por horizonte;
- frecuencia historica de train por horizonte y par cuando haya muestra;
- modelo de geometria del plan sin datos de mercado;
- ultimo challenger aceptado.

El champion heuristico se informa como referencia operativa, pero no se evalua
como distribucion calibrada porque sus salidas actuales no forman una
probabilidad coherente.

## 5. Metricas primarias

Para las tres clases:

```text
multiclass_log_loss = -mean(log(p_observada))
multiclass_brier    = mean(sum_k((p_k - y_k)^2))
```

Se publican tambien:

- Brier y log-loss one-vs-rest para TP y SL;
- curvas CORP/reliability y error de calibracion;
- discriminacion separada de calibracion;
- matriz de confusion solo como diagnostico secundario;
- cobertura y tasa de bloqueo;
- intervalos de confianza por block bootstrap temporal.

PnL, R-multiple, drawdown, MFE, MAE y tiempo hasta barrera son secundarios.
Nunca sustituyen calibracion y proper scores.

## 6. Ablation y reglas

Cada experimento queda registrado antes de abrir el test con:

- hipotesis;
- regla y formula exactas;
- variables padre;
- efecto esperado;
- segmentos aplicables;
- modelo base;
- metrica primaria;
- criterio de exito y retirada;
- numero de comparaciones simultaneas.

Se ejecutan:

- modelo sin la regla;
- modelo con la regla;
- componentes aislados;
- combinacion preregistrada;
- comparacion de contribucion incremental;
- estabilidad de coeficiente y metrica entre ventanas.

Una interaccion no se acepta porque el conjunto funcione: debe mejorar sobre
sus componentes y sobrevivir a datos posteriores.

## 7. Pares y horizontes

Se informa por separado para BTCUSDT, ETHUSDT y SOLUSDT y para:

- `intraday_short`;
- `intraday_wide`;
- `short_swing`.

El modelo puede usar entrenamiento conjunto si normaliza unidades, pero no se
declara valido para un par u horizonte sin resultados propios. Un estrato con
muestra insuficiente queda bloqueado; no hereda automaticamente la validez de
BTC ni del agregado.

## 8. Minimos de gobernanza

Estos minimos son decisiones conservadoras del proyecto, no leyes financieras:

- menos de 50 casos nuevos comparables: no se propone cambiar influencia;
- menos de 10 TP o menos de 10 SL: no se estima efecto direccional fiable;
- una clase sin representacion: no se entrena el multinomial;
- una sola ventana temporal favorable: evidencia insuficiente;
- menos de 50 casos en un par/horizonte: ese estrato no se promociona.

Superar los minimos permite evaluar; no demuestra validez.

## 9. Gates de promocion a sombra

Una regla solo pasa de `research` a `shadow` si:

1. Tiene fuente y limite de transferencia documentados.
2. La implementacion coincide con su formula.
3. Supera invariantes de coherencia.
4. Tiene traza individual completa.
5. El experimento fue preregistrado.
6. Existe muestra elegible suficiente.
7. Mejora incrementalmente frente al baseline en ventanas no usadas.
8. No degrada materialmente calibracion.
9. No depende de un unico par u horizonte sin declararlo.
10. Su incertidumbre y fallos quedan publicados.

## 10. Gates de promocion a produccion

La promocion exige:

- test temporal final sin reutilizacion;
- mejora consistente en log-loss o Brier frente a los baselines declarados;
- calibracion aceptable con intervalo de incertidumbre;
- ausencia de degradacion grave en cualquier estrato autorizado;
- estabilidad del signo y magnitud de contribuciones;
- cobertura operativa y bloqueo correctos;
- version, kill switch y rollback probados;
- revision del informe;
- aprobacion humana expresa.

No se fija ahora un porcentaje minimo de mejora: se declarara antes de entrenar
cada experimento segun tamano y variabilidad de su muestra. Elegirlo despues de
ver el test invalidaria la prueba.

## 11. Rechazo, suspension y retirada

Una regla se rechaza o retira cuando:

- empeora proper scores fuera de train;
- aparenta ventaja solo dentro de muestra;
- pierde calibracion;
- cambia de signo inestablemente;
- duplica informacion sin valor incremental;
- falla en pares u horizontes declarados;
- necesita leakage o etiquetas retrospectivas;
- su fuente o dato deja de ser fiable;
- su implementacion ya no coincide con la ficha;
- el intervalo de incertidumbre no permite distinguirla del baseline.

El resultado negativo se conserva para evitar repetir la misma busqueda.

## 12. Champion/challenger y reversibilidad

Durante sombra se guarda una comparacion append-only sin afectar al usuario ni
crear una operacion simulada. El champion sigue siendo la salida servida.

Todo artefacto tiene:

- `deployment_state`;
- fecha de activacion;
- version anterior;
- motivo;
- hash de codigo, datos y matriz;
- interruptor independiente;
- procedimiento de rollback.

Cambiar `shadow` a `production` nunca es automatico.

## 13. Estado de la muestra actual

E1.4 encontro 86 snapshots comparables, 20 outcomes completos y solo 7 casos
ETH. Esta muestra no permite entrenar, calibrar y reservar un test independiente
entre pares y horizontes. E1.5 deja preparado el protocolo; no inventa un
artefacto con esos datos.
