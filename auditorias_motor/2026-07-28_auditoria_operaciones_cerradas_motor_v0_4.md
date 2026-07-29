# Auditoria de operaciones cerradas: motor v0.4

## Cobertura

- Registros finalizados en base de datos: 245.
- Operaciones ejecutadas y cerradas: 238.
- Operaciones con desenlace inequívoco auditadas: 237.
- Operaciones cerradas excluidas por desenlace ambiguo: 1.
- Casos con variables preoperación de velas: 237.

## Resultado global

| Motor | Brier | Log-loss | Acierto principal | Prob. media al resultado real |
|---|---:|---:|---:|---:|
| Antiguo | 0.660784 | 1.129288 | 43.88% | 40.54% |
| Nuevo, núcleo 3 reglas | 0.482142 | 0.769423 | 63.71% | 50.82% |
| Nuevo, repetición estricta, hasta 7 reglas | 0.482423 | 0.769166 | 62.87% | 50.92% |
| Nuevo, repetición ampliada, hasta 10 reglas | 0.488813 | 0.775675 | 62.87% | 50.71% |

- Mejora estricta frente al antiguo: Brier 26.99%, log-loss 31.89%.
- Mejora ampliada frente al antiguo: Brier 26.03%, log-loss 31.31%.
- Mayor probabilidad asignada al resultado real: nuevo 155, antiguo 82, empate 0.

## Prueba final independiente

- Casos sellados: 21.
- Brier antiguo frente a repetición ampliada: 0.811794 frente a 0.574059.
- Log-loss antiguo frente a repetición ampliada: 1.207481 frente a 0.856842.
- Acierto principal antiguo frente a repetición ampliada: 23.81% frente a 61.90%.

## Ablacion por regla

| Regla | Mejora Brier | Mejora log-loss |
|---|---:|---:|
| `M4-RULE-VOLATILITY-RANK-001` | +0.012570 | +0.029664 |
| `M4-RULE-MTF-HIERARCHY-001` | +0.011585 | +0.015116 |
| `M4-RULE-PRIOR-EXTREMA-001` | +0.002458 | +0.004745 |
| `M4-RULE-FUNDING-STATE-001` | +0.000527 | +0.000412 |
| `M4-RULE-MARK-INDEX-PREMIUM-001` | +0.000056 | +0.000161 |
| `M4-RULE-SPOT-FUTURES-BASIS-001` | +0.000000 | +0.000000 |
| `M4-RULE-CONTINUOUS-REGIME-001` | -0.000369 | -0.000253 |
| `M4-RULE-OPEN-INTEREST-CHANGE-001` | -0.000404 | -0.000095 |
| `M4-RULE-AGGRESSOR-IMBALANCE-001` | -0.000463 | -0.000424 |
| `M4-RULE-PATH-STRUCTURE-001` | -0.000975 | -0.000592 |
| `M4-RULE-PRICE-OI-STATE-001` | -0.005593 | -0.006046 |

## Limite de la repeticion

- El basis spot/futuros queda neutralizado: las cotizaciones sincronizadas no se almacenaron en los analisis antiguos.
- Taker, OI y precio-OI usan el periodo historico almacenado mas cercano; no siempre coincide exactamente con H.
- Por ello, la repeticion de hasta 7 reglas usa solo datos exactos disponibles y la de hasta 10 es diagnostica. No existe una repeticion historica exacta de las 11.
- Solo 1 caso guardo H exacto; 236 usan la politica temporal congelada reconstruida.

Motor ampliado mejor que el antiguo en Brier y log-loss: si.
Cambio de produccion autorizado por esta auditoria: no.
