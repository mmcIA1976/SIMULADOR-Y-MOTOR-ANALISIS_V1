# Matriz de admisibilidad predictiva - E1.5.1

Version: `E1.5.1-v0.1`

Estado: COMPLETADA

## Respuesta principal

Actualmente no existe ninguna regla predictiva del champion que haya superado validacion temporal independiente, calibracion y validacion entre pares. Por tanto, ninguna formula predictiva actual queda autorizada para trasladarse automaticamente al challenger.

Esto no invalida los datos ni las formulas tecnicas estandar. La matriz separa expresamente poder calcular una variable de poder utilizarla como predictor de TP/SL.

## Conteos

- Reglas exactas registradas: 86.
- Reglas predictivas o decisionales: 69.
- Predictivas validadas temporalmente: 0.
- Predictivas autorizadas en produccion: 0.
- Datos permitidos sin inferencia predictiva: 7.
- Calculos permitidos sin inferencia predictiva: 6.
- Formulas actuales bloqueadas: 68.
- Hipotesis solo para investigacion: 4.

## Escalera de fiabilidad

- `R0_data_definition`: Dato con definicion oficial; no implica poder predictivo. Casos actuales: 7.
- `R1_standard_calculation`: Calculo estandar fiel; no implica senal predictiva. Casos actuales: 6.
- `R2_research_hypothesis`: Hipotesis investigable con respaldo conceptual externo. Casos actuales: 4.
- `R3_internal_provisional`: Indicio interno no independiente y aun insuficiente. Casos actuales: 24.
- `R4_temporally_validated`: Supera validacion temporal independiente. Casos actuales: 0.
- `R5_production_authorized`: Validada, calibrada y autorizada para produccion. Casos actuales: 0.
- `RX_blocked`: Formula actual bloqueada por incoherencia, duplicidad o falta de respaldo. Casos actuales: 45.

## Criterio de admision

Una regla predictiva solo puede entrar en sombra cuando tiene afirmacion de fuente acotada, implementacion fiel, coherencia, traza completa, ablation incremental, holdout temporal, validacion por pares y horizontes, calibracion y muestra suficiente.

Ninguna costumbre de trading sustituye estos gates.

## Clasificacion por familia

### Datos

Precio, velas, depth, trades, funding, OI y ratios tienen definicion oficial. Se admiten como datos con controles de disponibilidad y frescura. Sus proveedores no respaldan interpretaciones predictivas.

### Calculos tecnicos

Las distancias TP/SL, duracion y lado del plan tienen transformaciones deterministas y la EMA estandar puede calcularse como feature descriptiva. Ninguna queda autorizada como predictor por ese hecho. RSI y ATR actuales son variantes no etiquetadas y quedan bloqueados hasta corregirse o renombrarse. EMA200 fallback queda bloqueada.

### Hipotesis investigables

Tendencia, niveles y order flow tienen respaldo suficiente para formular experimentos. No tienen respaldo para los thresholds y pesos actuales, por lo que aun no entran en sombra.

### Reglas bloqueadas

Todos los pesos del score, los 19 gates de calibracion y las transformaciones TP/SL actuales quedan bloqueados. Precio-entrada, caps, SL residual, bandas de probabilidad, confianza y defaults por datos ausentes tienen ademas fallos de coherencia demostrados.

### Evidencia interna

Los gates v0.10/v0.11 permanecen como evidencia provisional del champion congelado. La traza historica guarda flags pero agrega sus efectos, de modo que ningun gate individual puede considerarse validado.

## Cobertura automatica

- Contribuciones E1.4 cubiertas: 29.
- Gates de calibracion cubiertos: 19.
- Funciones predictivas/decisionales E1.2 cubiertas: 36.
- SHA-256: `a59cb1e2b941e2ae989a402e6a1ed8b6aaad75f3a50ea730f50241675837e2b2`.

## Siguiente paso

E1.5.3-E1.5.5 definen el challenger desde cero usando solo datos admitidos y features calculables. Las hipotesis R2/R3 se incorporaran una por una como experimentos preregistrados, nunca como pesos heredados.
