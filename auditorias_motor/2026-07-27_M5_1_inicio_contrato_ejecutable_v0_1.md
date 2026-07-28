# M5.1 - Inicio y contrato ejecutable

Fecha: 2026-07-27
Estado: M5 INICIADA; M5.1 COMPLETADA

## Autorizacion

Orden expresa del propietario: `bien inicia m5`.

La autorizacion inicia la implementacion interna trazable. No
autoriza produccion, probabilidades, aprendizaje ni trading automatico.

## Alcance congelado

- Reglas: 27 (26 nucleares y 1 auxiliar).
- Formulas identificadas: 80.
- Dependencias del DAG: 32.
- Invariantes con prueba M5 obligatoria: 108.
- Entradas: MARKET; la rama pendiente permanece diferida.
- Valor esperado: interfaz obligatoria, evaluacion bloqueada hasta M6.

## Contrato de implementacion

Cada regla conserva sus datos, formula literal, dependencias,
condiciones, bloqueo por ausencia y campos de traza aprobados en M4.
Cada formula y cada prueba futura posee un identificador estable.

## Frontera

- Efecto en el resultado productivo: NINGUNO.
- Pesos o puntos: NO AUTORIZADOS.
- Probabilidades: M6, NO INICIADA.
- Motor de aprendizaje: FUERA DE ALCANCE.
- M5 cerrada: NO.

## Siguiente subfase

`M5.2`: implementar en codigo los contratos de entrada, salida y
traza antes de programar las transformaciones de las reglas.

SHA-256 del payload canonico: `b3d8d7f43aee5ab3984748f479970570d1b686a64b0265f59faf03608be76106`.
