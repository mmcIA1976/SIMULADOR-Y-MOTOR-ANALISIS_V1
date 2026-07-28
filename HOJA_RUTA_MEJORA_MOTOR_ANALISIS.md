# Hoja de ruta vinculante - Mejora del motor de analisis actual

Fecha de formalizacion: 2026-07-27
Estado: ACTIVA
Prioridad del proyecto: MAXIMA
Contrato rector: `CONTRATO_FASE_1_MOTOR_ANALISIS.md`
Cobertura objetivo: `COBERTURA_ANALITICA_FASE_1.md`
Auditoria de partida: `auditorias_motor/2026-07-24_plan_auditoria_integral_motor.md`

## 1. Objetivo unico

El trabajo prioritario es mejorar el motor de analisis actual hasta que pueda
estimar, antes de abrir una operacion y con informacion disponible en ese
instante:

- `P(TP primero dentro del horizonte)`;
- `P(SL primero dentro del horizonte)`;
- `P(no resolucion del plan dentro del horizonte)`.

Para ordenes pendientes, la traza descompone la no resolucion en `no_entry`
y `expiry_after_entry`; ninguna de las dos puede ocultarse bajo una etiqueta
generica de rango.

El usuario propone activo, lado, entrada, TP, SL y uno de los tres marcos
vigentes. El motor actual es la base de codigo que se va a corregir y
evolucionar. La version productiva actual se conserva como baseline congelado
para poder medir, auditar y revertir cada cambio.

No se abandona el motor actual ni se inicia un proyecto distinto. Una version
candidata significa una revision controlada del mismo motor, todavia no visible
en produccion.

## 2. Prioridad y limites

Hasta completar el nucleo riguroso del motor:

- el motor de aprendizaje queda fuera del trabajo activo;
- no se recopilan 50 operaciones como siguiente fase;
- no se modifican pesos a partir de evaluaciones antiguas;
- no se amplian liquidaciones ni proveedores como objetivo paralelo;
- no se incorporan funciones secundarias ajenas al nucleo;
- no se cambia el resultado visible en produccion;
- no se llama probabilidad a un score heuristico;
- no se presenta infraestructura de prueba como motor mejorado;
- no se da por validada una regla porque su indicador sea conocido;
- no se asignan pesos o umbrales por criterio subjetivo.

La infraestructura de versionado, ejecucion interna, apagado y reversion ya
construida se conserva apagada. Solo se utilizara cuando exista una revision
real y documentada del motor actual.

## 3. Estado real de partida

Version productiva congelada:

- reglas: `rules-v0.12.1-liquidations-readable`;
- scoring: `scoring-v0.11-underweighted-risk-cluster`.

Hechos demostrados:

- la salida actual es un score heuristico no calibrado;
- la distancia concreta a TP y SL no gobierna suficientemente el resultado;
- existen discontinuidades, doble conteo y umbrales no justificados;
- la matriz E1.5 contiene 86 elementos ejecutables: 82 pertenecen al motor
  productivo actual y 4 son calculos deterministas aislados en la
  infraestructura contractual;
- 68 elementos actuales no estan autorizados para trasladarse sin revision;
- 0 reglas predictivas tienen validacion temporal independiente;
- no se ha corregido todavia ninguna formula, peso o probabilidad visible;
- no existe una revision funcional del motor con reglas nuevas aprobadas.

Trabajo anterior reutilizable:

- contrato de Fase 1;
- matriz de los 34 bloques;
- inventario y trazabilidad del codigo;
- auditoria de procedencia, coherencia e impacto;
- separacion de datos pre-trade y post-trade;
- reconstruccion historica TP/SL, MFE y MAE;
- horizontes exactos de 4 h, 24 h y 7 dias;
- normalizacion economica;
- infraestructura apagada de versionado y reversion.

Este trabajo es una base de diagnostico y control. No constituye por si mismo
una mejora del calculo.

## 4. Reglas de ejecucion de la hoja de ruta

1. Solo puede existir una fase activa.
2. Antes de iniciar una fase se declara su objetivo, alcance y criterio de
   cierre.
3. Cada cierre registra lo realizado, lo no realizado, pruebas, limitaciones,
   archivos y commit.
4. Una fase no se considera cerrada sin aprobacion expresa del propietario.
5. No se inicia la fase siguiente antes de cerrar la actual.
6. Toda desviacion modifica primero esta hoja de ruta y explica el motivo.
7. Ninguna fase puede cambiar produccion salvo la fase M9.
8. Cada regla se documenta antes de programarse.
9. Cada dato se valida antes de utilizarse en una formula.
10. Cada afirmacion distingue definicion, teoria, hipotesis y evidencia.
11. Los 34 bloques deben recibir una decision explicita, aunque se pospongan o
    rechacen.
12. Toda regla activa debe funcionar en los pares y marcos declarados; cuando
    no pueda hacerlo debe bloquearse con motivo visible.

## 5. Jerarquia de respaldo

Cada regla separara cuatro niveles que no pueden confundirse:

1. `definicion`: formula estandar o descripcion verificable del dato.
2. `fundamento_tecnico`: interpretacion publicada o mecanismo financiero.
3. `evidencia_predictiva_externa`: estudio que relaciona la variable con un
   resultado futuro comparable.
4. `hipotesis_del_proyecto`: efecto que se desea comprobar especificamente
   para TP, SL y horizonte.

Fuentes admisibles, por orden de preferencia:

- documentacion oficial del proveedor para significado y calidad del dato;
- publicaciones academicas y trabajos cuantitativos primarios;
- manuales tecnicos o financieros reconocidos para definiciones y metodos;
- documentacion metodologica institucional;
- evidencia interna reproducible, identificada como tal.

Una fuente de datos acredita el dato, no su poder predictivo. Un manual puede
respaldar una formula o interpretacion, pero no un peso numerico del motor. Los
pesos solo pueden proceder de un metodo probabilistico documentado y de
evidencia compatible con el objetivo.

## 6. Contrato de cada regla

Antes de escribir codigo, cada regla debe registrar:

- identificador y version;
- bloque analitico;
- objetivo concreto;
- tipo: determinista, atomica, contextual, combinada, bloqueo o presentacion;
- dato bruto y proveedor;
- mercado, simbolo, timestamp, unidad y frescura;
- transformacion y formula exacta;
- normalizacion entre pares;
- marcos temporales aplicables;
- condiciones de activacion y de no aplicacion;
- fuente y afirmacion exacta respaldada;
- afirmaciones que la fuente no respalda;
- hipotesis predictiva separada;
- relacion esperada con TP, SL o expiracion;
- reglas relacionadas y riesgo de doble conteo;
- comportamiento cuando falta el dato;
- pruebas unitarias, limites e invariantes;
- traza que producira;
- criterio de refutacion, suspension o retirada;
- estado: propuesta, documentada, implementada interna, verificada, aprobada,
  limitada, suspendida o retirada.

Una regla sin ficha completa no puede influir en la salida.

## 7. Fases obligatorias

### M0 - Formalizacion y correccion de la hoja de ruta

Estado: COMPLETADA Y APROBADA EL 2026-07-27

Objetivo:

- fijar esta secuencia como prioridad unica;
- corregir documentos que todavia envian el trabajo hacia aprendizaje,
  acumulacion de casos o ampliaciones prematuras;
- conservar las fases anteriores como antecedentes, no como mejora del
  calculo.

Entregables:

- esta hoja de ruta;
- contrato y matriz de cobertura enlazados;
- plan de aprendizaje marcado como pausado;
- auditoria E1 marcada como cerrada y redirigida a M1.

Criterio de cierre:

- no existe ningun documento maestro que declare la antigua Fase 7 como
  siguiente trabajo;
- el siguiente paso unico queda identificado como M1;
- Git muestra exclusivamente cambios documentales deliberados;
- aprobacion expresa del propietario.

### M1 - Decision sobre cada elemento auditado y reconciliacion del motor actual

Estado: COMPLETADA Y APROBADA EL 2026-07-27

Objetivo:

- convertir los 86 elementos de la matriz E1.5 en una decision exhaustiva,
  distinguiendo los 82 elementos del motor productivo actual de los 4 calculos
  contractuales que no intervienen en produccion.

Trabajo:

1. Clasificar primero el origen: motor productivo actual o infraestructura
   contractual aislada.
2. Vincular cada elemento con uno o varios de los 34 bloques.
3. Identificar su ruta completa desde el dato hasta la salida.
4. Registrar formula, unidades, umbrales, pesos, caps e interacciones.
5. Separar calculos deterministas de afirmaciones predictivas.
6. Clasificar respaldo y evidencia.
7. Detectar duplicidad, leakage, discontinuidad y dependencia de otro score.
8. Asignar una decision:
   - conservar como dato o calculo;
   - reformular;
   - convertir en regla de presentacion;
   - desactivar;
   - retirar;
   - investigar antes de decidir.
9. Registrar la correccion necesaria y el bloque que la sustituira.

Entregables:

- matriz humana y estructurada de decisiones;
- reconciliacion
  `82 productivas + 4 contractuales = 86 auditadas = 86 decididas`;
- lista exacta de contribuciones actuales que deben dejar de intervenir;
- mapa de dependencias y doble conteo.

Criterio de cierre:

- ningun elemento queda omitido o autorizado por defecto;
- cada decision tiene motivo y evidencia;
- todavia no se modifica produccion;
- aprobacion expresa del propietario.

Resultado implementado:

- 82 elementos del motor productivo actual reconciliados;
- 4 calculos contractuales aislados reconciliados;
- 86/86 decisiones explicitas y reproducibles;
- 34/34 bloques registrados, incluidos 13 sin elemento actual;
- 29 ajustes predictivos actuales destinados a salir de la ruta
  probabilistica en M5;
- 19 gates empiricos destinados a salir de la ruta probabilistica en M5;
- 5 transformaciones finales de probabilidad destinadas a reconstruccion en
  M6;
- 0 efectos predictivos autorizados por M1;
- 0 cambios funcionales o productivos;
- 142/142 pruebas superadas.

Artefactos:

- `build_m1_rule_decisions.py`;
- `auditorias_motor/matriz_decisiones_m1_v0_1.json`;
- `auditorias_motor/2026-07-27_M1_decision_reglas_resultado.md`;
- `tests/test_m1_rule_decisions.py`.

Anexo solicitado tras el cierre:

- `M1-A - Catalogo exacto de reglas y formulas`.
- Estado: COMPLETADA Y APROBADA EL 2026-07-27.
- Objetivo: extraer las 86 fichas completas con formula vigente, constantes,
  umbrales, efectos, referencias ejecutables, fuentes, limites y decision M1.
- Este anexo no reabre M1, no inicia M2 y no modifica el motor.
- Resultado: 86/86 definiciones actuales completas, 67 referencias de funcion
  resueltas y 19/19 gates desglosados en todas sus dimensiones de efecto.
- Artefactos:
  `build_m1_exact_formula_catalog.py`,
  `auditorias_motor/catalogo_exacto_reglas_formulas_m1_v0_1.json`,
  `auditorias_motor/2026-07-27_M1_A_catalogo_exacto_reglas_formulas.md` y
  `tests/test_m1_exact_formula_catalog.py`.

### M2 - Semantica, geometria e invariantes del resultado

Estado: COMPLETADA Y APROBADA EL 2026-07-27

Objetivo:

- definir antes de las senales el problema matematico que debe resolver el
  motor.

Trabajo:

1. Validar geometria long y short.
2. Definir entrada inmediata y orden pendiente.
3. Fijar tiempo cero y vencimiento exacto.
4. Normalizar distancias a TP y SL, preferentemente en espacio logaritmico y
   tambien respecto a volatilidad.
5. Definir los tres outcomes condicionales tras ejecutar la entrada y los
   cuatro outcomes globales de una orden pendiente.
6. Definir censura, ambiguedad y plan no activado.
7. Separar:
   - probabilidad de recorrido de mercado;
   - calidad tecnica del plan;
   - ejecutabilidad y costes;
   - exposicion y gestion de riesgo.
8. Fijar invariantes de monotonicidad, simetria long/short, continuidad,
   unidades, masa probabilistica e insuficiencia de evidencia.
9. Definir la explicacion minima visible y su correspondencia con la traza.

Entregables:

- especificacion matematica aprobable;
- bateria de casos limite, incluido 872/873;
- pruebas que inicialmente deben fallar contra el scoring actual;
- contrato de salida sin pesos ni senales heredadas.

Criterio de cierre:

- TP mas lejano no puede aumentar su probabilidad manteniendo todo lo demas
  constante sin una justificacion matematica explicita;
- para entrada a mercado, TP primero, SL primero y expiracion suman uno;
- para orden pendiente, la traza separa TP primero, SL primero, expiracion
  posterior a entrada y no entrada, y las cuatro masas suman uno;
- la salida visible conserva TP, SL y no resolucion sumando uno, sin ocultar
  que la no resolucion puede proceder de expiracion o de no entrada;
- horizonte, distancia y volatilidad afectan de forma coherente;
- ejecucion, conducta y apalancamiento no falsean la direccion del mercado;
- aprobacion expresa del propietario.

Resultado aprobado:

- contrato matematico previo a cualquier eleccion de senales o modelo;
- tiempo cero fijado en `analysis_at`, corte de datos pre-trade y vencimiento
  absoluto que no se reinicia al ejecutar tarde una orden pendiente;
- geometria long/short validada mediante distancias logaritmicas positivas,
  simetricas y normalizacion obligatoria por una escala de volatilidad
  aprobada para el horizonte;
- arbol de eventos que separa entrada, no entrada, TP primero, SL primero y
  expiracion posterior a entrada;
- 19 invariantes sobre tiempo, geometria, masa, monotonicidad, continuidad,
  simetria, separacion de conceptos, datos y trazabilidad;
- 15 casos limite, incluida la discontinuidad de los analisis 872/873;
- 9 incumplimientos reproducibles del scoring actual, 6 de severidad critica;
- 0 cambios en `analysis_engine.py`, `data_engine.py` o la salida productiva;
- 0 metodos probabilisticos, pesos o senales seleccionados prematuramente;
- 12/12 pruebas especificas M2 superadas.

Artefactos:

- `build_m2_semantic_contract.py`;
- `auditorias_motor/contrato_semantico_m2_v0_1.json`;
- `auditorias_motor/auditoria_invariantes_m2_motor_actual_v0_1.json`;
- `auditorias_motor/2026-07-27_M2_semantica_geometria_resultado.md`;
- `tests/test_m2_semantic_contract.py`.

Registro de cierre:

- aprobacion expresa del propietario: 2026-07-27;
- criterios semanticos y documentales: cumplidos;
- suite completa al cierre: 160/160 pruebas;
- cambios funcionales o productivos: ninguno;
- commit asociado: pendiente de preparacion conjunta; no creado durante el
  cierre documental.

Aclaracion posterior al cierre:

- `M3-CLARIFICATION-001`, identificada durante M4.2 el 2026-07-27;
- se incorpora `trigger_condition` a los campos de `M3-DATA-001` porque ya
  forma parte de `POST /api/analyze` y es imprescindible para reconstruir una
  entrada pendiente;
- no cambia proveedor, endpoint, disponibilidad, conclusiones ni produccion.
- `M3-CLARIFICATION-002`, identificada durante M4.5 el 2026-07-27;
- se incorporan `margin` y `leverage` a `M3-DATA-001` porque ya forman parte
  de `POST /api/analyze` y son imprescindibles para separar geometria de
  mercado, exposicion y perdida sobre margen;
- no cambia proveedor, endpoint, disponibilidad, conclusiones ni produccion.

### M3 - Contrato y auditoria de datos pre-trade

Estado: COMPLETADA Y APROBADA EL 2026-07-27

Objetivo:

- demostrar que cada dato necesario puede obtenerse de forma fiable, gratuita
  y previa al analisis para todos los pares y marcos declarados.

Trabajo por dato:

1. Proveedor y endpoint exactos.
2. Mercado real: spot, USD-M Futures, opciones u otro.
3. Campo, unidad, precision y normalizacion.
4. Timestamp del proveedor y timestamp de captura.
5. Frecuencia, frescura maxima y ventana historica.
6. Cobertura por par y marco.
7. Limites, retencion, rate limit y errores conocidos.
8. Posibilidad de reconstruccion historica sin look-ahead.
9. Fallback permitido o bloqueo obligatorio.
10. Prueba contra ejemplos reales y datos degradados.

Orden obligatorio:

- primero los datos P0;
- despues los P1 aprobados;
- P2 y P3 permanecen fuera hasta que el nucleo funcione.

Entregables:

- catalogo de fuentes y campos;
- matriz dato-regla-par-horizonte;
- pruebas de frescura, unidad y ausencia;
- lista de reglas inviables por falta de datos.

Criterio de cierre:

- ninguna regla P0 depende de un dato supuesto;
- toda ausencia bloquea o degrada de forma explicita;
- no se usan proxies sin nombre, alcance y limitacion;
- aprobacion expresa del propietario.

Resultado de cierre:

- 18 contratos de datos P0 con proveedor, endpoint, mercado, campos, unidades,
  timestamps, frescura, retencion, limitaciones y efecto de ausencia;
- verificacion viva de 76/76 consultas publicas: 4 globales y 72 por
  endpoint-par para los seis pares declarados;
- comision efectiva identificada como fuente oficial condicionada a
  autenticacion, sin fingir su disponibilidad anonima;
- matriz completa de 216 combinaciones: 12 bloques P0 x 6 pares x 3 marcos;
- 15 incumplimientos del snapshot actual reproducidos: 10 criticos y 5 altos;
- politica ejecutable que rechaza datos futuros, obsoletos, lentos,
  desordenados, velas abiertas y capturas temporalmente dispersas;
- 15/15 pruebas especificas de M3 superadas;
- cambios funcionales o productivos: ninguno;
- M4 iniciada: no.

Registro de cierre:

- aprobacion expresa del propietario: 2026-07-27;
- criterios documentales, temporales y de cobertura: cumplidos;
- suite completa al cierre: 176/176 pruebas;
- cambios funcionales o productivos: ninguno;
- commit asociado: pendiente de preparacion conjunta; no creado durante el
  cierre documental.

Artefactos:

- `audit_m3_live_sources.py`;
- `build_m3_data_contracts.py`;
- `auditorias_motor/2026-07-27_M3_verificacion_viva_fuentes.json`;
- `auditorias_motor/catalogo_contratos_datos_m3_v0_1.json`;
- `auditorias_motor/matriz_dato_bloque_par_horizonte_m3_v0_1.json`;
- `auditorias_motor/auditoria_datos_motor_actual_m3_v0_1.json`;
- `auditorias_motor/2026-07-27_M3_contrato_auditoria_datos_pretrade_resultado.md`;
- `tests/test_m3_data_contracts.py`.

### M4 - Catalogo formal de reglas y combinaciones P0

Estado: EN CURSO DESDE EL 2026-07-27

Objetivo:

- definir las reglas del nucleo antes de implementarlas.

Bloques P0:

- 1, estructura del precio;
- 3, multi-timeframe;
- 7, order flow;
- 9, open interest;
- 10, funding;
- 15, spot contra futuros;
- 24, regimen;
- 26, estadistica, volatilidad y alcanzabilidad;
- 28, probabilidad TP/SL;
- 29, ejecucion y costes;
- 30, gestion de riesgo;
- 32, evaluacion del rendimiento.

Orden interno:

1. Alcanzabilidad por distancia, volatilidad y horizonte.
2. Regimen.
3. Estructura y direccion.
4. Jerarquia multi-timeframe.
5. Flujo spot y Futures.
6. OI, funding y posicionamiento derivado necesario.
7. Ejecucion y costes.
8. Riesgo separado de probabilidad de mercado.
9. Combinaciones preregistradas.

Subfases de control:

1. `M4.1`, alcance, criterios de admision y reconciliacion M1-M3.
2. `M4.2`, alcanzabilidad por geometria, volatilidad y horizonte.
3. `M4.3`, regimen, estructura y jerarquia multi-timeframe.
4. `M4.4`, order flow, spot-Futures, OI y funding.
5. `M4.5`, ejecucion, costes, riesgo y evaluacion.
6. `M4.6`, combinaciones, doble conteo y reconciliacion final.
7. `M4.7`, artefactos reproducibles, pruebas y revision del propietario.

Estado interno actual:

- `M4.1`: COMPLETADA EL 2026-07-27;
- `M4.2`: COMPLETADA EL 2026-07-27;
- `M4.3`: COMPLETADA EL 2026-07-27;
- `M4.4`: COMPLETADA EL 2026-07-27;
- `M4.5`: COMPLETADA EL 2026-07-27;
- `M4.6`: COMPLETADA EL 2026-07-27;
- `M4.7`: EN REVISION DEL PROPIETARIO DESDE EL 2026-07-27.

Registro de inicio:

- inicio autorizado expresamente por el propietario: 2026-07-27;
- version productiva y formulas visibles: congeladas;
- aprendizaje: pausado;
- M5: no iniciada;
- primer trabajo obligatorio: reconciliar los 30 elementos remitidos a M4
  por M1 con los contratos de datos M3 y con los 12 bloques P0.

Resultado de `M4.1`:

- 30/30 elementos remitidos por M1 reconciliados individualmente;
- 17 familias semilla identificadas, expresamente no consideradas reglas;
- 0 puntos, pesos o efectos probabilisticos antiguos autorizados;
- Fibonacci bloqueado en P1 y pospuesto a M10;
- ajustes procedentes del aprendizaje antiguo retirados;
- duplicidades CVD/taker, niveles, MTF, OI y funding fusionadas por familia;
- seis pares, tres horizontes, 12 bloques P0 y contratos M3 preservados;
- 11/11 pruebas especificas superadas;
- produccion, motor de analisis y M5: sin cambios.

Artefactos de `M4.1`:

- `build_m4_reconciliation.py`;
- `auditorias_motor/reconciliacion_candidatos_m4_v0_1.json`;
- `auditorias_motor/2026-07-27_M4_1_alcance_reconciliacion_resultado.md`;
- `tests/test_m4_reconciliation.py`.

Resultado de `M4.2`:

- 6 fichas formales: seleccion temporal, geometria, retornos logaritmicos,
  volatilidad realizada anterior, alcanzabilidad TP/SL y activacion pendiente;
- formulas continuas `d_TP`, `d_SL`, `RV_prev(H)`, `sigma_prev(H)`, `z_TP`,
  `z_SL` y `z_entry`;
- horizonte exacto sin redondeo y al menos 24 retornos cerrados por ventana;
- 3 hipotesis separadas, prerregistradas y sin efecto productivo;
- 0 probabilidades, puntos, bandas o pesos autorizados;
- ATR actual, precio-contra-entrada y penalizaciones de volatilidad/zona
  retirados de la futura ruta P0;
- simetria long/short, invariancia de escala, continuidad y monotonicidad
  exigidas por pruebas;
- 17/17 pruebas especificas superadas;
- produccion, motor de analisis y M5: sin cambios.

Artefactos de `M4.2`:

- `build_m4_reachability.py`;
- `auditorias_motor/catalogo_alcanzabilidad_m4_2_v0_1.json`;
- `auditorias_motor/2026-07-27_M4_2_alcanzabilidad_resultado.md`;
- `tests/test_m4_reachability.py`.

Resultado de `M4.3`:

- 6 fichas formales: operador de suavizado exponencial, estructura de
  trayectoria, extremos del horizonte anterior, percentil de volatilidad,
  jerarquia `H`, `2H`, `4H` y vector continuo de regimen;
- formulas continuas `D_W`, `TV_W`, `E_W`, `SE_W`, percentil RV midrank y
  vector `(q_RV, SE_H)`;
- EMA conservada solo como operador matematico, sin periodos aprobados ni
  valor predictivo;
- tendencia y acuerdo multi-timeframe descritos sin votos, pesos o
  penalizaciones;
- maximos y minimos anteriores registrados sin etiquetarlos automaticamente
  como soporte, resistencia o barrera;
- 5 hipotesis separadas y prerregistradas, con limites de transferencia
  explicitos para activo, mercado y horizonte;
- 3 familias de evidencia no aditivas para impedir doble conteo;
- 0 probabilidades, puntos, bandas o pesos autorizados;
- 19/19 pruebas especificas superadas;
- produccion, motor de analisis, aprendizaje y M5: sin cambios.

Artefactos de `M4.3`:

- `build_m4_structure_regime.py`;
- `auditorias_motor/catalogo_regimen_estructura_mtf_m4_3_v0_1.json`;
- `auditorias_motor/2026-07-27_M4_3_regimen_estructura_mtf_resultado.md`;
- `tests/test_m4_structure_regime.py`.

Resultado de `M4.4`:

- 7 fichas formales: desequilibrio de operaciones agresoras ejecutadas,
  cambio de OI, estado conjunto precio-OI, basis spot-Futures, prima
  mark-index, estado de funding y vector de contexto de derivados;
- formulas continuas `ATI_H`, `dOI_H`, `(D_H,dOI_H)`, tres razones
  logaritmicas de basis, prima mark-index y funding observado por hora;
- taker imbalance separado expresamente del OFI completo y del CVD;
- operaciones agregadas, volumen taker periodico y volumen taker de velas
  tratados como fuentes alternativas, nunca como tres senales sumables;
- OI conservado como cantidad bruta abierta, sin atribuir largos o cortos;
- Spot y Futures sin liderazgo permanente, dado que la evidencia publicada
  cambia por mercado y muestra;
- `lastFundingRate` tratado como ultima tasa observada, no como tasa futura;
- cinco familias de evidencia no aditivas y 7 hipotesis prerregistradas;
- 0 probabilidades, puntos, umbrales o pesos autorizados;
- 23/23 pruebas especificas superadas;
- produccion, motor de analisis, aprendizaje y M5: sin cambios.

Artefactos de `M4.4`:

- `build_m4_derivatives_context.py`;
- `auditorias_motor/catalogo_contexto_derivados_m4_4_v0_1.json`;
- `auditorias_motor/2026-07-27_M4_4_orderflow_oi_basis_funding_resultado.md`;
- `tests/test_m4_derivatives_context.py`.

Resultado de `M4.5`:

- 8 fichas economicas formales: spread cotizado, barrido de profundidad,
  comisiones por rol, funding firmado, exposicion del plan, payoff neto por
  resultado, identidad de valor esperado y estado de disponibilidad;
- separacion obligatoria entre probabilidad de mercado, ejecucion,
  exposicion monetaria, evaluacion economica y politica de decision;
- spread y profundidad tratados como una sola familia no aditiva: el
  shortfall contra midpoint ya incorpora medio spread y barrido visible;
- comisiones calculadas con tasas autenticadas maker, taker o RPI; sin tasa
  disponible se bloquea el coste exacto;
- funding conservado con signo, numero real de eventos y notional de cada
  evento; la ultima tasa observada no se proyecta al futuro;
- margen y apalancamiento escalan cantidad, PnL y riesgo sobre margen, pero
  no alteran la probabilidad de que el mercado alcance TP o SL;
- payoff separado para TP, SL, expiry y no-entry; un componente ausente
  bloquea la rama en vez de sustituirlo por una constante;
- identidad `EV=sum(p_k*payoff_k)` conservada, pero el EV queda bloqueado
  hasta M6 y hasta disponer de payoffs completos;
- `risk score`, grade, confianza numerica y decision heuristica retirados de
  la ruta P0; disponibilidad se expresa mediante estados y faltantes;
- umbrales universales RR>=3 y distancias 0.25%/3% retirados;
- 0 hipotesis predictivas, probabilidades, puntos, pesos o efectos
  productivos autorizados;
- 23/23 pruebas especificas superadas;
- produccion, motor de analisis, aprendizaje y M5: sin cambios.

Artefactos de `M4.5`:

- `build_m4_execution_risk.py`;
- `auditorias_motor/catalogo_ejecucion_riesgo_m4_5_v0_1.json`;
- `auditorias_motor/2026-07-27_M4_5_ejecucion_costes_riesgo_resultado.md`;
- `tests/test_m4_execution_risk.py`.

Resultado de `M4.6`:

- universo completo reconciliado: 27 reglas formales, 15 hipotesis, 30
  elementos antiguos, 17 familias semilla y 12 bloques P0;
- 15 slots canonicos definidos para que cada observacion tenga una sola
  representacion utilizable;
- 16 relaciones explicitas de dependencia, redundancia exacta, fuente
  alternativa, contenedor, coste solapado o separacion de capas;
- `E_H=abs(SE_H)`, etiquetas MTF, vectores contenedores `POI_H`, `R_t` y
  `DC_H`, copias de ATI y desplazamiento `D_H` duplicado excluidos como
  votos adicionales;
- volatilidad absoluta y percentil de volatilidad autorizados solo en sus
  funciones distintas: escala de alcanzabilidad y contexto de interaccion;
- basis cross-venue y prima mark-index tratados como modos alternativos,
  nunca como dos votos acumulables;
- 8 combinaciones prerregistradas: alcanzabilidad base, arbol pendiente,
  estructura, flujo, precio-OI, derivados, candidato completo y evaluacion
  economica;
- interacciones definidas como productos exactos y sometidas a jerarquia
  fuerte: una interaccion conserva siempre sus dos efectos principales;
- el candidato completo elimina por identificador canonico cualquier efecto
  principal o interaccion repetidos;
- `SCORE-CONTRADICTION_PENALTY` retirado: los estados mixtos se conservan
  como datos y solo se estudian mediante interacciones prerregistradas;
- las 30 reglas antiguas tienen disposicion final expresa y ninguna conserva
  puntos, pesos o autorizacion productiva;
- probabilidad, coeficientes, umbrales de promocion y politica de decision
  siguen expresamente pendientes de M6-M8;
- 23/23 pruebas especificas superadas;
- produccion, motor de analisis, aprendizaje y M5: sin cambios.

Artefactos de `M4.6`:

- `build_m4_combinations.py`;
- `auditorias_motor/catalogo_combinaciones_reconciliacion_m4_6_v0_1.json`;
- `auditorias_motor/2026-07-27_M4_6_combinaciones_reconciliacion_resultado.md`;
- `tests/test_m4_combinations.py`.

Resultado tecnico de `M4.7`, pendiente de aprobacion del propietario:

- auditoria transversal completa de 27/27 reglas, 15/15 hipotesis y 8/8
  combinaciones;
- las 8 fichas economicas de M4.5 se han alineado con el contrato documental
  completo: objetivo, bloques, datos, unidades, formula, condiciones,
  fuentes, limites, doble conteo, ausencia, pruebas, traza y refutacion;
- todas las combinaciones declaran reglas padre, hipotesis padre, operador,
  orden, exclusiones, condiciones, fuentes, limites, traza y refutacion;
- catalogo unico de auditoria con las 27 reglas, sus formulas exactas,
  datos, fuentes, limites, trazas y criterios de refutacion;
- manifiesto reproducible de 29 artefactos con ruta, tamano y SHA-256;
- hashes de los seis modulos productivos registrados para la revision;
- comandos exactos de generacion, comprobacion y pruebas documentados;
- seis decisiones del propietario preparadas y expresamente pendientes;
- la aprobacion de M4 se define como aceptacion del alcance documental para
  M5, nunca como validacion predictiva, rentabilidad o autorizacion
  productiva;
- 28/28 pruebas especificas superadas;
- puerta tecnica superada; puerta del propietario pendiente;
- M4 no cerrada y M5 no iniciada.

Artefactos de `M4.7`:

- `build_m4_review_package.py`;
- `build_m4_rule_audit_report.py`;
- `auditorias_motor/catalogo_27_reglas_formulas_m4_7_v0_1.json`;
- `auditorias_motor/2026-07-27_M4_7_27_reglas_formulas_auditoria.md`;
- `auditorias_motor/paquete_revision_m4_7_v0_1.json`;
- `auditorias_motor/2026-07-27_M4_7_paquete_revision_propietario.md`;
- `tests/test_m4_rule_audit_report.py`;
- `tests/test_m4_review_package.py`.

Para cada regla se cumplira el contrato de la seccion 6. Las combinaciones
deben declarar reglas padre, operador, orden, condiciones excluyentes,
duplicidad y efecto incremental esperado.

Entregables:

- fichas versionadas de todas las reglas P0 propuestas;
- bibliografia y enlaces exactos;
- formulas y pseudocodigo;
- matriz de interacciones;
- lista de reglas actuales sustituidas o desactivadas.

Criterio de cierre:

- ninguna regla P0 carece de formula, dato, fuente o limite;
- ninguna interpretacion tecnica se presenta como peso probabilistico;
- las combinaciones estan definidas antes de observar sus resultados;
- aprobacion expresa del propietario.

### M5 - Implementacion trazable de variables y reglas P0

Estado: PENDIENTE

Objetivo:

- programar dentro del motor actual las variables y reglas aprobadas sin
  alterar todavia el resultado productivo.

Trabajo:

1. Implementar adquisicion y validacion de datos aprobados.
2. Implementar transformaciones deterministas.
3. Implementar reglas atomicas y contextuales.
4. Implementar bloqueos por calidad o ausencia.
5. Implementar combinaciones preregistradas.
6. Registrar entradas, salidas, version, estado y motivo por regla.
7. Registrar reglas no evaluadas y motivo.
8. Evitar doble conteo mediante grupos de evidencia.
9. Mantener separada la capa de presentacion.
10. Comparar cada calculo con ejemplos manuales reproducibles.

Entregables:

- codigo versionado del mismo motor;
- traza completa por analisis interno;
- pruebas unitarias y de propiedades;
- informe de paridad de datos y formulas;
- lista de heuristicas antiguas que ya no intervienen en la revision interna.

Criterio de cierre:

- cada valor de la traza puede recalcularse;
- no existen contribuciones ocultas;
- la revision interna no modifica produccion;
- aprobacion expresa del propietario.

### M6 - Integracion probabilistica documentada

Estado: PENDIENTE

Objetivo:

- convertir geometria, volatilidad y evidencia aprobada en probabilidades
  coherentes sin sumar puntos arbitrarios.

Trabajo:

1. Investigar y elegir expresamente el metodo:
   - primera barrera/first passage;
   - riesgos competitivos o supervivencia;
   - modelo multinomial interpretable;
   - combinacion documentada de los anteriores.
2. Definir supuestos, parametros y limites.
3. Construir primero un baseline de alcanzabilidad basado en plan, volatilidad
   y horizonte.
4. Incorporar reglas tecnicas solo mediante un mecanismo cuantificado y
   trazable.
5. Impedir que manuales o intuiciones asignen coeficientes.
6. Separar calibracion de construccion de variables.
7. Incorporar incertidumbre y estado de evidencia insuficiente.
8. Mantener costes, ejecutabilidad y riesgo como capas identificables.

Entregables:

- decision metodologica con fuentes;
- formula completa de los tres outcomes;
- traza desde variable hasta probabilidad;
- pruebas de invariantes y sensibilidad;
- version interna reproducible del motor mejorado.

Criterio de cierre:

- no existe ningun punto, bonus o penalizacion sin derivacion;
- las probabilidades responden al plan concreto;
- todas las contribuciones son visibles;
- los casos 872/873 son coherentes;
- aprobacion expresa del propietario.

### M7 - Verificacion matematica, de software y cobertura

Estado: PENDIENTE

Objetivo:

- intentar refutar la revision interna antes de medir rendimiento.

Trabajo:

1. Casos limite de entrada, TP, SL y horizonte.
2. Simetria long/short.
3. Monotonicidad y continuidad.
4. Masa probabilistica.
5. Datos ausentes, obsoletos, parciales o contradictorios.
6. Cobertura de todos los pares soportados.
7. Cobertura de los tres marcos.
8. Pruebas de doble conteo e interacciones.
9. Reproducibilidad de la traza y explicacion.
10. Comparacion manual de una muestra de analisis.
11. Rendimiento, latencia y tolerancia a fallos.
12. Revision independiente del codigo y de las formulas.

Entregables:

- suite de pruebas;
- informe de fallos y correcciones;
- matriz par-marco-regla;
- demostracion de que la version productiva sigue intacta.

Criterio de cierre:

- cero fallos criticos abiertos;
- toda limitacion restante esta declarada;
- aprobacion expresa del propietario.

### M8 - Evaluacion empirica independiente del motor definido

Estado: BLOQUEADA HASTA M7

Objetivo:

- comprobar el motor ya definido, no aprender del score antiguo.

Condiciones previas:

- reglas, formulas, fuentes e integracion congeladas y versionadas;
- dataset construido desde datos de mercado y planes, sin utilizar los
  porcentajes del motor antiguo como verdad;
- cortes temporales definidos antes de evaluar;
- separacion cronologica de desarrollo, calibracion y prueba;
- cobertura suficiente por par, lado, marco y outcome.

El tamano necesario no se fijara por conveniencia. Se justificara mediante
incertidumbre, potencia y composicion de la muestra. El antiguo minimo de 50
casos no se considera prueba suficiente ni siguiente objetivo.

Metricas:

- Brier y log-loss multiclase;
- curvas de calibracion;
- discriminacion;
- intervalos de confianza;
- estabilidad por par, lado, marco y regimen;
- ablation por regla y combinacion;
- costes y resultado economico como evaluacion secundaria.

Criterio de cierre:

- el motor queda aprobado, rechazado o devuelto a una fase anterior con motivo
  cuantificado;
- no se retocan reglas despues de ver el conjunto de prueba;
- aprobacion expresa del propietario.

### M9 - Activacion controlada del motor actual mejorado

Estado: BLOQUEADA HASTA M8

Objetivo:

- sustituir la version productiva del motor actual por su revision aprobada.

Trabajo:

1. Version exacta de reglas, scoring, datos y formula probabilistica.
2. Copia y comprobacion del baseline.
3. Activacion gradual y reversible.
4. Interruptor de apagado probado.
5. Comparacion local y online del commit exacto.
6. Verificacion de endpoints, interfaz, trazas y resultados.
7. Registro de incidencias y criterio de rollback.
8. Aprobacion humana previa y posterior.

Criterio de cierre:

- produccion sirve el commit aprobado;
- la salida visible coincide con la traza;
- rollback probado;
- no quedan porcentajes heuristicos etiquetados como probabilidades.

### M10 - Expansion controlada de cobertura

Estado: BLOQUEADA HASTA M9

Objetivo:

- incorporar los bloques restantes uno por uno sin debilitar el nucleo.

P1:

- 2, indicadores tecnicos;
- 5, velas cuantificadas;
- 6, volumen, VWAP y subasta;
- 8, libro y microestructura;
- 11, prima, basis y curva;
- 12, liquidaciones;
- 13, posicionamiento long/short;
- 19, macroeconomia;
- 20, intermercado;
- 21, amplitud y rotacion;
- 25, estacionalidad;
- 34, riesgo operativo y contraparte.

P2:

- 14, opciones;
- 17, on-chain;
- 18, tokenomics y fundamental;
- 22, sentimiento;
- 23, noticias y eventos.

P3:

- 4, metodologias discrecionales;
- 16, cross-exchange y arbitraje;
- 27, machine learning e IA;
- 31, cartera;
- 33, psicologia y conducta.

Cada incorporacion repite M3-M9 para su dato, regla e impacto. Un bloque puede
ser rechazado o permanecer descriptivo. Cobertura no significa influencia
obligatoria sobre TP o SL.

## 8. Trabajo expresamente fuera de la prioridad activa

El motor de aprendizaje no se elimina, pero queda pausado. No se reanudara
hasta que:

- M1-M9 esten completadas;
- el motor mejorado produzca una traza valida por regla;
- exista una version productiva rigurosa que merezca ser evaluada;
- el propietario autorice un plan separado.

Las evaluaciones antiguas no pueden justificar pesos del motor mejorado. La
infraestructura previa de comparacion solo podra reutilizarse como mecanismo
tecnico de seguridad, no como evidencia de validez.

## 9. Relacion con las fases realizadas

Las fases 0-6 del plan de aprendizaje y E1.1-E1.5 permanecen registradas como
trabajo terminado. Su utilidad se limita a datos, auditoria, diagnostico,
trazabilidad, economia e infraestructura. No se presentan como correcciones del
scoring.

La antigua Fase 7 queda sustituida por M1-M8. La antigua Fase 8 queda absorbida
en M10, bloqueada hasta que el nucleo este aprobado y activo.

## 10. Estado de seguimiento

| Fase | Estado | Resultado exigido |
|---|---|---|
| M0 | Completada y aprobada | Hoja de ruta coherente y aprobada |
| M1 | Completada y aprobada | Decision sobre 82 elementos actuales y 4 contractuales |
| M1-A | Completada y aprobada | Catalogo exacto 86/86 de reglas, formulas y contratos actuales |
| M2 | Completada y aprobada | Semantica, geometria e invariantes |
| M3 | Completada y aprobada | Contratos reales de datos P0 |
| M4 | En curso | Catalogo documentado de reglas P0 |
| M5 | Pendiente | Reglas P0 implementadas y trazables |
| M6 | Pendiente | Integracion probabilistica documentada |
| M7 | Pendiente | Verificacion matematica y de software |
| M8 | Bloqueada | Evaluacion empirica independiente |
| M9 | Bloqueada | Activacion productiva reversible |
| M10 | Bloqueada | Expansion P1, P2 y P3 |

## 11. Siguiente paso unico

Revisar el paquete `M4.7` y registrar la decision expresa del propietario.
No cerrar M4 ni iniciar M5 sin esa aprobacion.
