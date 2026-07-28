# Motor con 11 reglas predictivas activas v0.4

Fecha: 2026-07-28

## Orden aplicada

El catalogo predictivo contiene exclusivamente factores que:

1. reciben datos durante el analisis;
2. producen una senal numerica;
3. modifican TP, SL o vencimiento;
4. registran su contribucion individual;
5. pueden vincularse posteriormente con el resultado observado.

Los calculos internos, contenedores duplicados, controles y formulas
economicas dejan de contabilizarse como reglas predictivas.

## Versiones

- Aplicacion: `app-v0.22.0-active-predictive-rules`
- Motor: `M6-ACTIVE-PREDICTIVE-RULES-v0.4`
- Scoring: `M6-calibrated-plus-active-rules-v0.4`
- Atribucion de reglas: `M6-active-predictive-rules-v0.1`
- Aprendizaje: `learning-v0.3-rule-attribution`

## Catalogo activo

| Regla | Dato | Integracion |
|---|---|---|
| Path structure | Eficiencia firmada H | Contribucion provisional |
| Prior extrema | Extremo previo entre entrada y TP | Coeficiente existente |
| Volatility rank | Percentil frente a 60 ventanas | Coeficiente existente |
| MTF hierarchy | Eficiencias 2H y 4H | Coeficientes existentes |
| Continuous regime | Eficiencia H x regimen de volatilidad | Contribucion provisional |
| Aggressor imbalance | ATI taker buy/sell | Contribucion provisional |
| Open interest change | Cambio logaritmico OI en H | Contribucion provisional de movimiento |
| Price-OI state | Direccion precio x cambio OI | Contribucion provisional |
| Spot-Futures basis | Basis sincronizado | Contribucion provisional |
| Mark-index premium | Prima mark/index | Contribucion provisional |
| Funding state | Ultima tasa observada | Contribucion provisional |

Total: `11` reglas predictivas activas cuando sus datos estan disponibles.

## Contribuciones provisionales

Las reglas sin coeficiente previo utilizan senales acotadas a `[-1,1]`.
El peso se aplica en espacio logaritmico y las tres probabilidades se
normalizan de nuevo para conservar masa uno.

| Regla | Senal | Peso inicial |
|---|---|---:|
| Path structure | `side * SE_H` | `0.12` |
| Continuous regime | `side * SE_H * (2*q_RV-1)` | `0.08` |
| Aggressor imbalance | `side * ATI_H` | `0.12` |
| Open interest change | `tanh(50*abs(dOI_H))` | `0.06` |
| Price-OI state | `side*sign(D_H)*tanh(50*dOI_H)` | `0.10` |
| Spot-Futures basis | `-side*tanh(100*b_mid)` | `0.06` |
| Mark-index premium | `-side*tanh(200*premium)` | `0.06` |
| Funding state | `-side*tanh(last_rate/0.0005)` | `0.08` |

Para reglas direccionales:

```text
log_weight_TP += weight * signal
log_weight_SL -= weight * signal
```

Para actividad de OI:

```text
log_weight_TP += weight * signal
log_weight_SL += weight * signal
log_weight_expiry -= weight * signal
```

Estos pesos son iniciales y quedan identificados como provisionales. El
motor no los presenta como coeficientes ya validados.

## Elementos excluidos del catalogo predictivo

- reglas 1-5: operaciones internas del modelo base;
- regla 6: compuerta MARKET;
- regla 7: suavizado sin parametro;
- regla 19: contenedor duplicado de derivados;
- reglas 20-27: ejecucion, costes, exposicion y controles economicos.

Pueden conservarse como trazas o informacion complementaria, pero no
incrementan el numero de reglas predictivas.

## Atribucion para aprendizaje

Cada recomendacion conserva por regla:

- estado y hash de la traza;
- senal preoperacion;
- peso o coeficientes;
- probabilidades antes y despues;
- delta exacto de TP y SL;
- version del motor.

Al cerrar la operacion, `structured_json` enlaza esa fotografia con:

- TP primero;
- SL primero;
- ninguna barrera o caso censurado.

Esto permite evaluar y reajustar cada regla individualmente sin reescribir
el snapshot preoperacion.

## Verificacion

Prueba real BTCUSDT:

- reglas activas: `11`;
- contribuciones provisionales producidas: `8/8`;
- masa final: `1.0`;
- motor: `M6-ACTIVE-PREDICTIVE-RULES-v0.4`.

Suite completa: `620/620`.

No se ha realizado commit, push ni despliegue.
