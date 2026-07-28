from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SOURCE_PATH = (
    ROOT / "auditorias_motor" / "matriz_admisibilidad_reglas_v0_1.json"
)
DEFAULT_MATRIX_PATH = (
    ROOT / "auditorias_motor" / "matriz_decisiones_m1_v0_1.json"
)
DEFAULT_REPORT_PATH = (
    ROOT / "auditorias_motor" / "2026-07-27_M1_decision_reglas_resultado.md"
)
AUDIT_VERSION = "M1-rule-decisions-v0.1"

HORIZONS = ["intraday_short", "intraday_wide", "short_swing"]
CONTRACT_ONLY_IDS = {
    "PLAN-TP-LOG-DISTANCE",
    "PLAN-SL-LOG-DISTANCE",
    "PLAN-LOG-HORIZON-SECONDS",
    "PLAN-SIDE-SIGN",
}

BLOCKS = {
    1: ("Estructura del precio", "P0"),
    2: ("Indicadores tecnicos", "P1"),
    3: ("Multi-timeframe", "P0"),
    4: ("Patrones y metodologias discrecionales", "P3"),
    5: ("Velas japonesas", "P1"),
    6: ("Volumen y subasta", "P1"),
    7: ("Order flow", "P0"),
    8: ("Libro y microestructura", "P1"),
    9: ("Open interest", "P0"),
    10: ("Funding", "P0"),
    11: ("Prima, basis y curva", "P1"),
    12: ("Liquidaciones", "P1"),
    13: ("Posicionamiento long/short", "P1"),
    14: ("Opciones", "P2"),
    15: ("Spot contra futuros", "P0"),
    16: ("Cross-exchange y arbitraje", "P3"),
    17: ("On-chain", "P2"),
    18: ("Tokenomics y fundamental", "P2"),
    19: ("Macroeconomia", "P1"),
    20: ("Intermercado", "P1"),
    21: ("Amplitud y rotacion", "P1"),
    22: ("Sentimiento", "P2"),
    23: ("Noticias y eventos", "P2"),
    24: ("Regimen de mercado", "P0"),
    25: ("Estacionalidad y tiempo", "P1"),
    26: ("Estadistica y cuantitativo", "P0"),
    27: ("Machine learning e IA", "P3"),
    28: ("Probabilidad TP/SL", "P0"),
    29: ("Ejecucion y costes", "P0"),
    30: ("Gestion de riesgo", "P0"),
    31: ("Cartera", "P3"),
    32: ("Evaluacion del rendimiento", "P0"),
    33: ("Psicologia y conducta", "P3"),
    34: ("Riesgo operativo y contraparte", "P1"),
}

RULE_BLOCKS = {
    "DATA-PRICE-KLINES": [1, 2, 3, 5, 6, 24, 26, 28],
    "DATA-DEPTH-TRADES": [7, 8, 29],
    "DATA-DERIVATIVES": [9, 10, 13],
    "DATA-BREADTH": [21],
    "DATA-GLOBAL": [21, 24],
    "DATA-SENTIMENT": [22],
    "DATA-LIQUIDATIONS": [12],
    "PLAN-TP-LOG-DISTANCE": [26, 28],
    "PLAN-SL-LOG-DISTANCE": [26, 28, 30],
    "PLAN-LOG-HORIZON-SECONDS": [26, 28],
    "PLAN-SIDE-SIGN": [26, 28],
    "IND-EMA-CORE": [1, 2, 3],
    "IND-EMA200-FALLBACK": [1, 2, 3, 34],
    "IND-RSI14-CURRENT": [2],
    "IND-ATR14-CURRENT": [2, 26, 28],
    "IND-EMA-STACK": [1, 2, 3],
    "IND-SUPPORT-RESISTANCE": [1],
    "IND-FIBONACCI": [4],
    "IND-ORDERBOOK-PROXY": [8],
    "IND-CVD-PROXY": [7],
    "IND-PENDING-ZONE": [1, 28, 29],
    "SCORE-TREND_BIAS": [1, 3],
    "SCORE-TECHNICAL_DIRECTION_BIAS": [1, 2, 3],
    "SCORE-PRICE_VS_ENTRY_BIAS": [26, 28],
    "SCORE-VOLUME_BIAS": [6],
    "SCORE-ORDER_BOOK_BIAS": [8],
    "SCORE-MOMENTUM_BIAS": [2],
    "SCORE-MARKET_REGIME_BIAS": [24],
    "SCORE-FIBONACCI_PROBABILITY_ADJUSTMENT": [4, 28],
    "SCORE-ZONE_PROBABILITY_ADJUSTMENT": [1, 28],
    "SCORE-TAKER_FLOW_BIAS": [7],
    "SCORE-CVD_BIAS": [7],
    "SCORE-OI_TREND_BIAS": [9],
    "SCORE-BREADTH_BIAS": [21],
    "SCORE-VOLATILITY_PENALTY": [26, 28],
    "SCORE-LIQUIDITY_PENALTY": [8, 29],
    "SCORE-OVEREXTENSION_PENALTY": [1, 2, 24],
    "SCORE-FUNDING_PENALTY": [10],
    "SCORE-FUNDING_RELATIVE_PENALTY": [10],
    "SCORE-CROWDING_PENALTY": [13],
    "SCORE-LEVEL_PENALTY": [1, 28],
    "SCORE-SENTIMENT_PENALTY": [22],
    "SCORE-HIGHER_TIMEFRAME_PENALTY": [1, 3],
    "SCORE-TECHNICAL_ENTRY_TIMING_PENALTY": [1, 2, 24],
    "SCORE-TECHNICAL_BARRIER_PENALTY": [1, 28],
    "SCORE-OI_CONTEXT_PENALTY": [9, 24],
    "SCORE-CONTRADICTION_PENALTY": [24, 28],
    "SCORE-RISK_CALIBRATION_TP_ADJUSTMENT": [28, 30, 32],
    "SCORE-ZONE_RANGE_PROBABILITY_ADJUSTMENT": [28],
    "SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT": [28, 30, 32],
    "GATE-SL_PROBABILITY_GTE_55": [28, 30, 32],
    "GATE-SL_PROBABILITY_GTE_50": [28, 30, 32],
    "GATE-DIRECTION_SCORE_LT_40": [28, 30, 32],
    "GATE-TECHNICAL_SCORE_LT_40": [2, 30, 32],
    "GATE-RR_RATIO_GTE_3": [28, 30, 32],
    "GATE-REWARD_DISTANCE_GTE_3": [28, 30, 32],
    "GATE-RISK_DISTANCE_LT_0_25": [28, 30, 32],
    "GATE-RISK_DISTANCE_GTE_3": [28, 30, 32],
    "GATE-TICKER_24H_CONTRA_SIDE": [1, 30, 32],
    "GATE-EMA_STACK_15M_CONTRA_SIDE": [1, 3, 30, 32],
    "GATE-PRICE_VS_EMA_1H_CONTRA_SIDE": [1, 3, 30, 32],
    "GATE-PENDING_ZONE_NEGATIVE_ADJUSTMENT": [1, 28, 30, 32],
    "GATE-PENDING_STOP_BREAKDOWN": [1, 28, 30, 32],
    "GATE-PENDING_LIQUIDITY_SWEEP_HIGH": [1, 7, 8, 30, 32],
    "GATE-PENDING_FALSE_BREAKOUT_RISK": [1, 7, 30, 32],
    "GATE-EXTREME_FIB_EXTREME_SENTIMENT_CLUSTER": [4, 22, 30, 32],
    "GATE-EXTREME_FIB_SENTIMENT_CVD_CONTRA": [4, 7, 22, 30, 32],
    "GATE-RSI_EXTREME_MULTI_RISK_CLUSTER": [2, 30, 32],
    "GATE-RSI_EXTREME_WITH_FIB_SENTIMENT_CLUSTER": [2, 4, 22, 30, 32],
    "OUT-TP-ADDITIVE": [28],
    "OUT-TP-CAPS": [28],
    "OUT-RANGE": [28],
    "OUT-SL-RESIDUAL": [28],
    "OUT-PROBABILITY-BANDS": [28, 32],
    "OUT-EV-COST": [29, 30, 32],
    "OUT-FEE": [29],
    "OUT-SLIPPAGE": [8, 29],
    "OUT-FUNDING-COST": [10, 29],
    "OUT-RISK-SCORE": [30, 32],
    "OUT-GRADE": [30, 32],
    "OUT-CONFIDENCE": [28, 32],
    "OUT-DECISION": [30, 32],
    "OUT-LAYERED-SCORES": [28, 32],
    "OUT-HORIZON-FALLBACK": [28, 34],
    "OUT-MISSING-DATA": [28, 34],
    "OUT-RISK-CAL-METRIC": [32],
}

LEGACY_ACTIONS = {
    "rebuild_single_feature": (
        "retirar_puntos_y_reformular",
        "Eliminar los puntos actuales y definir una unica variable estructural "
        "sin duplicidad multi-timeframe.",
    ),
    "rebuild_without_manual_points": (
        "retirar_puntos_y_reformular",
        "Eliminar la suma manual y reconstruir el contexto tecnico desde "
        "variables atomicas documentadas.",
    ),
    "retire_current_formula": (
        "retirar_formula_actual",
        "Eliminar la formula discontinua actual; M2 debe sustituirla por "
        "geometria continua del plan.",
    ),
    "research_continuous_transform": (
        "retirar_umbral_y_reformular",
        "Eliminar umbral y peso actuales; definir una transformacion continua "
        "antes de cualquier evaluacion.",
    ),
    "research_without_current_threshold": (
        "retirar_umbral_y_reformular",
        "Conservar el dato, retirar el corte actual y reformular la proxy.",
    ),
    "retire_current_thresholds": (
        "retirar_umbrales_actuales",
        "Retirar bandas y pesos actuales; corregir primero la definicion del "
        "indicador.",
    ),
    "rebuild_regime_as_single_context": (
        "retirar_puntos_y_reformular",
        "Reconstruir regimen como capa de contexto que habilita o bloquea "
        "reglas, no como bonus.",
    ),
    "retire_predictive_adjustment": (
        "retirar_efecto_predictivo",
        "Eliminar el ajuste predictivo; conservar solo informacion descriptiva "
        "si supera su contrato.",
    ),
    "rebuild_as_preregistered_interaction": (
        "retirar_puntos_y_reformular",
        "Retirar el ajuste compuesto y definir una interaccion con padres, "
        "operador y condiciones explicitas.",
    ),
    "research_continuous_feature": (
        "retirar_umbral_y_reformular",
        "Eliminar umbral y peso actuales; investigar una variable continua.",
    ),
    "research_with_correlation_control": (
        "retirar_puntos_y_reformular",
        "Retirar el efecto actual y reformular controlando correlacion y doble "
        "conteo.",
    ),
    "research_by_horizon": (
        "retirar_puntos_y_reformular",
        "Retirar el efecto actual y definir la hipotesis por horizonte.",
    ),
    "research_or_retire": (
        "retirar_efecto_y_posponer",
        "Eliminar el efecto actual; solo podra volver como hipotesis "
        "documentada y refutable.",
    ),
    "replace_with_barrier_model": (
        "retirar_penalizacion_y_reformular",
        "Eliminar la penalizacion discreta e incorporar volatilidad, distancia "
        "y horizonte al modelo de barreras.",
    ),
    "model_execution_separately": (
        "separar_de_probabilidad_de_mercado",
        "Retirar el castigo direccional y modelar spread en ejecutabilidad y "
        "costes.",
    ),
    "research_continuous_interaction": (
        "retirar_puntos_y_reformular",
        "Eliminar el ajuste actual y definir una interaccion continua, "
        "trazable y sin doble conteo.",
    ),
    "research_by_contract_and_horizon": (
        "retirar_puntos_y_reformular",
        "Retirar umbral y peso; estudiar por contrato y horizonte.",
    ),
    "research_by_pair": (
        "retirar_puntos_y_reformular",
        "Retirar corte y peso generales; comprobar cobertura y normalizacion "
        "por par.",
    ),
    "compare_level_models": (
        "retirar_penalizacion_y_reformular",
        "Eliminar el detector y peso actuales; comparar detectores de niveles "
        "reproducibles.",
    ),
    "merge_into_single_structure_feature": (
        "retirar_duplicidad_y_reformular",
        "Eliminar la penalizacion duplicada e integrarla en una unica capa "
        "jerarquica de estructura.",
    ),
    "compare_barrier_models": (
        "retirar_penalizacion_y_reformular",
        "Eliminar cortes actuales y comparar modelos de barrera normalizados.",
    ),
    "replace_with_explicit_interactions": (
        "retirar_conteo_y_reformular",
        "Eliminar el conteo de contradicciones y declarar interacciones "
        "concretas sin duplicidad.",
    ),
    "decompose_and_revalidate": (
        "retirar_ajuste_agregado",
        "Eliminar el ajuste agregado; ninguna regla puede ocultarse tras caps "
        "o contribuciones conjuntas.",
    ),
    "separate_activation_from_outcome": (
        "separar_semanticas",
        "Separar probabilidad de activacion de una orden y expiracion del plan.",
    ),
    "remove_until_defined": (
        "retirar_formula_actual",
        "Eliminar el ajuste hasta que exista una semantica y formula aprobadas.",
    ),
}

OUTPUT_ACTIONS = {
    "OUT-TP-ADDITIVE": (
        "retirar_y_reconstruir_salida",
        "Sustituir la suma de puntos por el metodo probabilistico de M6.",
    ),
    "OUT-TP-CAPS": (
        "retirar_caps_heuristicos",
        "Eliminar caps manuales; cualquier restriccion futura debe derivarse "
        "del modelo y su calibracion.",
    ),
    "OUT-RANGE": (
        "reformular_como_expiracion",
        "Sustituir rango por el outcome explicito de expiracion sin barrera.",
    ),
    "OUT-SL-RESIDUAL": (
        "retirar_y_reconstruir_salida",
        "Eliminar SL residual y estimar SL primero como outcome propio.",
    ),
    "OUT-PROBABILITY-BANDS": (
        "retirar_bandas_heuristicas",
        "Eliminar bandas visuales; la incertidumbre futura debe calcularse.",
    ),
    "OUT-FEE": (
        "reformular_coste",
        "Calcular fee por mercado, tipo de orden y tarifa documentada.",
    ),
    "OUT-SLIPPAGE": (
        "reformular_coste",
        "Modelar slippage con spread, profundidad, tamano y ejecucion.",
    ),
    "OUT-FUNDING-COST": (
        "reformular_coste",
        "Calcular signo, numero de periodos y horizonte real del funding.",
    ),
    "OUT-RISK-SCORE": (
        "reformular_capa_de_riesgo",
        "Separar riesgo de exposicion de la probabilidad de recorrido.",
    ),
    "OUT-GRADE": (
        "reformular_politica",
        "Derivar el grado desde probabilidades, riesgo y ejecucion aprobados.",
    ),
    "OUT-CONFIDENCE": (
        "reformular_incertidumbre",
        "Sustituir confianza heuristica por calidad de datos e incertidumbre.",
    ),
    "OUT-DECISION": (
        "reformular_politica",
        "Separar la politica simular/observar del calculo probabilistico.",
    ),
    "OUT-LAYERED-SCORES": (
        "convertir_en_traza",
        "Conservar capas solo como explicacion reproducible, sin votos ocultos.",
    ),
    "OUT-HORIZON-FALLBACK": (
        "retirar_fallback",
        "Exigir horizonte exacto y bloquear cuando falte.",
    ),
    "OUT-MISSING-DATA": (
        "retirar_defaults_neutrales",
        "Bloquear o degradar con motivo; no inventar evidencia neutral.",
    ),
}


def load_source() -> dict:
    return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def source_sha256() -> str:
    return hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()


def current_route(rule: dict) -> str:
    routes = {
        "market_data": (
            "proveedor -> market_data/data_engine -> snapshot pre-trade -> "
            "variables dependientes"
        ),
        "feature_transform": (
            "plan/snapshot -> transformacion -> score o contexto dependiente"
        ),
        "predictive_score": (
            "snapshot/variables -> ajuste analysis_engine -> TP score"
        ),
        "risk_calibration": (
            "scores/contexto -> gates v0.10/v0.11 -> TP/rango/riesgo/politica"
        ),
        "output_and_policy": (
            "scores y calibracion -> salida final, coste, riesgo o decision"
        ),
    }
    return routes[rule["layer"]]


def replacement_phase(rule: dict, block_ids: list[int]) -> str:
    rule_id = rule["id"]
    if rule_id in CONTRACT_ONLY_IDS:
        return "M2"
    if rule["kind"] == "data_definition":
        return "M3" if any(BLOCKS[item][1] == "P0" for item in block_ids) else "M10"
    if rule_id in {
        "OUT-TP-ADDITIVE",
        "OUT-TP-CAPS",
        "OUT-RANGE",
        "OUT-SL-RESIDUAL",
        "OUT-PROBABILITY-BANDS",
    }:
        return "M6"
    if rule_id in {"OUT-EV-COST", "OUT-RISK-CAL-METRIC"}:
        return "M7"
    if rule_id.startswith("OUT-"):
        return "M5" if any(BLOCKS[item][1] == "P0" for item in block_ids) else "M10"
    if rule_id.startswith("GATE-"):
        return "no_aplica_gate_exacto_retirado"
    if not any(BLOCKS[item][1] == "P0" for item in block_ids):
        return "M10"
    return "M4"


def initial_action_phase(rule: dict, replacement: str) -> str:
    if rule["kind"] in {
        "active_predictive_adjustment",
        "internal_empirical_gate",
    }:
        return "M5"
    return replacement


def decision_for(rule: dict) -> tuple[str, str]:
    rule_id = rule["id"]
    if rule["kind"] == "data_definition":
        return (
            "conservar_como_dato_sin_efecto_predictivo_directo",
            "Conservar el transporte del dato; M3 debe aprobar fuente, "
            "frescura, unidad, cobertura y ausencia.",
        )
    if rule_id in CONTRACT_ONLY_IDS:
        return (
            "conservar_calculo_contractual_aislado",
            "Conservar como identidad determinista no productiva; M2 debe "
            "aprobar su semantica y uso.",
        )
    if rule_id == "IND-EMA-CORE":
        return (
            "conservar_calculo_sin_peso_predictivo",
            "Conservar la formula EMA; periodos, contexto y efecto predictivo "
            "deben definirse aparte.",
        )
    if rule_id == "IND-EMA200-FALLBACK":
        return (
            "desactivar_fallback_mal_etiquetado",
            "No llamar EMA200 a una EMA de hasta 80 cierres; exigir historia "
            "suficiente o marcar el dato ausente.",
        )
    if rule_id in {"IND-RSI14-CURRENT", "IND-ATR14-CURRENT"}:
        return (
            "reformular_a_definicion_estandar_o_renombrar",
            "Corregir el suavizado de Wilder o declarar otra formula con "
            "identidad propia antes de utilizarla.",
        )
    if rule_id == "IND-EMA-STACK":
        return (
            "mantener_solo_como_hipotesis_estructural",
            "No conservar peso ni voto; M4 debe decidir una variable "
            "estructural unica y no redundante.",
        )
    if rule_id == "IND-SUPPORT-RESISTANCE":
        return (
            "reformular_detector_antes_de_uso",
            "Retirar la interpretacion del detector actual y comparar metodos "
            "de niveles reproducibles.",
        )
    if rule_id == "IND-FIBONACCI":
        return (
            "retirar_efecto_predictivo_conservar_solo_investigacion",
            "Mantener niveles solo como contexto experimental; no pueden "
            "afectar TP o SL.",
        )
    if rule_id in {"IND-ORDERBOOK-PROXY", "IND-CVD-PROXY"}:
        return (
            "reformular_proxy_sin_peso_actual",
            "Conservar datos brutos, retirar la proxy como senal y reconstruir "
            "una variable temporal con control de calidad.",
        )
    if rule_id == "IND-PENDING-ZONE":
        return (
            "conservar_solo_observacional_y_reformular_interaccion",
            "Separar activacion, estructura y recorrido; no mantener el "
            "compuesto actual.",
        )
    if rule_id.startswith("SCORE-"):
        return LEGACY_ACTIONS[rule["current_decision"]]
    if rule_id.startswith("GATE-"):
        return (
            "retirar_gate_del_calculo_conservar_evidencia_historica",
            "Eliminar el gate exacto y sus puntos; conservar su origen solo "
            "como hipotesis historica no autorizada.",
        )
    if rule_id == "OUT-EV-COST":
        return (
            "conservar_identidad_reconstruir_entradas",
            "Conservar la identidad de esperanza matematica, usando "
            "probabilidades y costes validos cuando existan.",
        )
    if rule_id in OUTPUT_ACTIONS:
        return OUTPUT_ACTIONS[rule_id]
    if rule_id == "OUT-RISK-CAL-METRIC":
        return (
            "presentacion_unicamente_redefinir",
            "No puede modificar probabilidades; solo mostrar una metrica "
            "definida y derivada de la traza.",
        )
    raise KeyError(f"Falta decision M1 para {rule_id}")


def target_role(rule: dict, decision: str) -> str:
    rule_id = rule["id"]
    if rule["kind"] == "data_definition":
        return "dato_pre_trade_con_contrato"
    if rule_id in CONTRACT_ONLY_IDS:
        return "geometria_determinista_del_plan"
    if rule_id.startswith("GATE-"):
        return "evidencia_historica_sin_ejecucion"
    if rule_id in {
        "OUT-TP-ADDITIVE",
        "OUT-TP-CAPS",
        "OUT-RANGE",
        "OUT-SL-RESIDUAL",
        "OUT-PROBABILITY-BANDS",
    }:
        return "salida_probabilistica_a_reconstruir"
    if rule_id in {"OUT-FEE", "OUT-SLIPPAGE", "OUT-FUNDING-COST"}:
        return "capa_de_ejecucion_y_costes"
    if rule_id in {"OUT-RISK-SCORE", "OUT-GRADE", "OUT-DECISION"}:
        return "capa_de_riesgo_o_politica_separada"
    if rule_id in {"OUT-LAYERED-SCORES", "OUT-RISK-CAL-METRIC"}:
        return "traza_o_presentacion_sin_efecto"
    if rule_id == "OUT-CONFIDENCE":
        return "incertidumbre_y_calidad_de_datos"
    if rule_id == "OUT-EV-COST":
        return "identidad_financiera_posterior"
    if decision.startswith("retirar"):
        return "sin_efecto_actual_hasta_reformulacion"
    return "variable_candidata_sin_peso_actual"


def current_probability_action(rule: dict) -> str:
    rule_id = rule["id"]
    if rule["kind"] == "active_predictive_adjustment":
        return "debe_salir_de_la_ruta_probabilistica_actual"
    if rule["kind"] == "internal_empirical_gate":
        return "debe_salir_de_la_ruta_probabilistica_actual"
    if rule_id in {
        "OUT-TP-ADDITIVE",
        "OUT-TP-CAPS",
        "OUT-RANGE",
        "OUT-SL-RESIDUAL",
        "OUT-PROBABILITY-BANDS",
    }:
        return "debe_reemplazarse_en_la_ruta_probabilistica"
    return "sin_autorizacion_de_efecto_predictivo_directo"


def build_matrix() -> dict:
    source = load_source()
    source_rules = source["rules"]
    source_ids = [rule["id"] for rule in source_rules]
    if len(source_ids) != 86 or len(set(source_ids)) != 86:
        raise ValueError("La matriz E1.5 no contiene 86 IDs unicos.")
    if set(source_ids) != set(RULE_BLOCKS):
        missing = sorted(set(source_ids) - set(RULE_BLOCKS))
        extra = sorted(set(RULE_BLOCKS) - set(source_ids))
        raise ValueError(f"Mapa de bloques incompleto. missing={missing} extra={extra}")

    decisions = []
    for source_rule in source_rules:
        block_ids = RULE_BLOCKS[source_rule["id"]]
        decision, action = decision_for(source_rule)
        replacement = replacement_phase(source_rule, block_ids)
        origin = (
            "contract_infrastructure_only"
            if source_rule["id"] in CONTRACT_ONLY_IDS
            else "current_production_engine"
        )
        decisions.append(
            {
                "id": source_rule["id"],
                "name": source_rule["name"],
                "origin": origin,
                "current_layer": source_rule["layer"],
                "current_kind": source_rule["kind"],
                "implementation_refs": source_rule["implementation_refs"],
                "current_route": current_route(source_rule),
                "formula": source_rule["formula"],
                "source_ids": source_rule["source_ids"],
                "published_support": source_rule["published_support"],
                "transfer_limit": source_rule["transfer_limit"],
                "reliability_tier": source_rule["reliability_tier"],
                "coherence": source_rule["coherence"],
                "blockers": source_rule["blockers"],
                "e1_3_findings": source_rule["e1_3_findings"],
                "e1_4_impact": source_rule["e1_4_impact"],
                "block_ids": block_ids,
                "blocks": [
                    {
                        "id": block_id,
                        "name": BLOCKS[block_id][0],
                        "priority": BLOCKS[block_id][1],
                    }
                    for block_id in block_ids
                ],
                "m1_decision": decision,
                "required_action": action,
                "target_role": target_role(source_rule, decision),
                "initial_action_phase": initial_action_phase(
                    source_rule,
                    replacement,
                ),
                "replacement_phase": replacement,
                "current_probability_action": current_probability_action(
                    source_rule
                ),
                "direct_probability_authorized": False,
                "production_modified_in_m1": False,
                "horizons": source_rule["horizons"],
                "pair_scope": source_rule["pair_scope"],
            }
        )

    by_block: dict[int, list[str]] = {block_id: [] for block_id in BLOCKS}
    for item in decisions:
        for block_id in item["block_ids"]:
            by_block[block_id].append(item["id"])
    block_coverage = [
        {
            "id": block_id,
            "name": BLOCKS[block_id][0],
            "priority": BLOCKS[block_id][1],
            "existing_element_ids": by_block[block_id],
            "existing_element_count": len(by_block[block_id]),
            "m1_status": (
                "existing_elements_decided"
                if by_block[block_id]
                else "no_current_element_explicitly_recorded"
            ),
            "next_phase": (
                "M3-M7"
                if BLOCKS[block_id][1] == "P0"
                else "M10"
            ),
        }
        for block_id in BLOCKS
    ]

    decision_counts = Counter(item["m1_decision"] for item in decisions)
    kind_counts = Counter(item["current_kind"] for item in decisions)
    action_phase_counts = Counter(
        item["initial_action_phase"] for item in decisions
    )
    replacement_phase_counts = Counter(
        item["replacement_phase"] for item in decisions
    )
    probability_action_counts = Counter(
        item["current_probability_action"] for item in decisions
    )
    payload = {
        "audit_version": AUDIT_VERSION,
        "status": "completed_owner_approved_2026_07_27",
        "purpose": (
            "Decidir los 82 elementos productivos actuales y reconciliar los "
            "4 calculos contractuales de la matriz E1.5 sin modificar el motor."
        ),
        "source": {
            "path": str(SOURCE_PATH.relative_to(ROOT)).replace("\\", "/"),
            "sha256": source_sha256(),
            "declared_matrix_sha256": source.get("matrix_sha256"),
        },
        "reconciliation": {
            "source_elements": len(source_rules),
            "current_production_elements": sum(
                item["origin"] == "current_production_engine"
                for item in decisions
            ),
            "contract_infrastructure_elements": sum(
                item["origin"] == "contract_infrastructure_only"
                for item in decisions
            ),
            "decided_elements": len(decisions),
            "unique_ids": len({item["id"] for item in decisions}),
            "analytic_blocks": len(block_coverage),
            "blocks_with_existing_elements": sum(
                bool(item["existing_element_ids"]) for item in block_coverage
            ),
            "blocks_without_existing_elements": sum(
                not item["existing_element_ids"] for item in block_coverage
            ),
        },
        "summary": {
            "decision_counts": dict(sorted(decision_counts.items())),
            "current_kind_counts": dict(sorted(kind_counts.items())),
            "initial_action_phase_counts": dict(
                sorted(action_phase_counts.items())
            ),
            "replacement_phase_counts": dict(
                sorted(replacement_phase_counts.items())
            ),
            "probability_action_counts": dict(
                sorted(probability_action_counts.items())
            ),
            "direct_probability_authorized": 0,
            "production_modified": False,
            "learning_engine_used": False,
            "next_phase_started": False,
        },
        "block_coverage": block_coverage,
        "decisions": decisions,
    }
    payload["decisions_sha256"] = sha256_value(decisions)
    return payload


def render_report(payload: dict) -> str:
    reconciliation = payload["reconciliation"]
    summary = payload["summary"]
    decisions = payload["decisions"]
    lines = [
        "# M1 - Decision sobre los elementos auditados del motor actual",
        "",
        "Fecha: 2026-07-27",
        "Estado: COMPLETADA Y APROBADA EL 2026-07-27",
        f"Version: `{payload['audit_version']}`",
        "",
        "## 1. Objetivo",
        "",
        "Decidir uno por uno los elementos de la matriz E1.5, distinguiendo el",
        "motor productivo actual de la infraestructura contractual aislada.",
        "M1 no modifica formulas, pesos, probabilidades ni produccion.",
        "",
        "## 2. Correccion del universo",
        "",
        "La cifra anterior de 86 elementos no equivalia a 86 elementos",
        "productivos actuales:",
        "",
        f"- Motor productivo actual: {reconciliation['current_production_elements']}.",
        f"- Infraestructura contractual aislada: {reconciliation['contract_infrastructure_elements']}.",
        f"- Total auditado y decidido: {reconciliation['decided_elements']}.",
        "",
        "Los cuatro elementos contractuales son las distancias logaritmicas TP y",
        "SL, la duracion logaritmica y la codificacion simetrica del lado. No",
        "intervienen en la aplicacion productiva.",
        "",
        "## 3. Reconciliacion",
        "",
        "| Control | Resultado |",
        "|---|---:|",
        f"| Elementos fuente | {reconciliation['source_elements']} |",
        f"| IDs unicos | {reconciliation['unique_ids']} |",
        f"| Elementos decididos | {reconciliation['decided_elements']} |",
        f"| Bloques analiticos | {reconciliation['analytic_blocks']} |",
        f"| Bloques con elementos actuales | {reconciliation['blocks_with_existing_elements']} |",
        f"| Bloques sin elemento actual, registrados expresamente | {reconciliation['blocks_without_existing_elements']} |",
        f"| Efectos predictivos autorizados | {summary['direct_probability_authorized']} |",
        f"| Produccion modificada | {'si' if summary['production_modified'] else 'no'} |",
        f"| Motor de aprendizaje utilizado | {'si' if summary['learning_engine_used'] else 'no'} |",
        "",
        "## 4. Dictamen operativo",
        "",
        "M1 no conserva ningun peso, umbral, gate o porcentaje por defecto.",
        "Los datos y calculos estandar pueden conservarse solo en su papel",
        "descriptivo o determinista. Las afirmaciones predictivas quedan sin",
        "autorizacion hasta las fases posteriores de la hoja de ruta.",
        "",
        "Deben salir de la ruta probabilistica actual:",
        "",
        f"- ajustes predictivos actuales: {summary['current_kind_counts'].get('active_predictive_adjustment', 0)};",
        f"- gates empiricos actuales: {summary['current_kind_counts'].get('internal_empirical_gate', 0)};",
        f"- transformaciones de probabilidad que deben reemplazarse: {summary['probability_action_counts'].get('debe_reemplazarse_en_la_ruta_probabilistica', 0)}.",
        "",
        "Esta es una decision de diseno para la revision interna futura. M1 no",
        "apaga todavia esos elementos en produccion.",
        "",
        "## 5. Decisiones por elemento",
        "",
        "| # | ID | Origen | Bloques | Decision M1 | Accion | Reemplazo |",
        "|---:|---|---|---|---|---|---|",
    ]
    for index, item in enumerate(decisions, start=1):
        origin = "productivo" if item["origin"] == "current_production_engine" else "contractual"
        blocks = ",".join(str(block_id) for block_id in item["block_ids"])
        lines.append(
            f"| {index} | `{item['id']}` | {origin} | {blocks} | "
            f"`{item['m1_decision']}` | {item['initial_action_phase']} | "
            f"{item['replacement_phase']} |"
        )

    lines.extend(
        [
            "",
            "## 6. Cobertura de los 34 bloques",
            "",
            "| Bloque | Prioridad | Elementos actuales | Estado M1 |",
            "|---:|---|---:|---|",
        ]
    )
    for block in payload["block_coverage"]:
        lines.append(
            f"| {block['id']} - {block['name']} | {block['priority']} | "
            f"{block['existing_element_count']} | `{block['m1_status']}` |"
        )

    lines.extend(
        [
            "",
            "## 7. Limites de M1",
            "",
            "- No se han investigado aun las formulas sustitutas.",
            "- No se han aprobado fuentes nuevas.",
            "- No se han programado reglas nuevas.",
            "- No se ha modificado el scoring visible.",
            "- No se ha iniciado M2.",
            "- Las decisiones de reformulacion indican trabajo futuro, no",
            "  validacion conseguida.",
            "",
            "## 8. Evidencia reproducible",
            "",
            f"- Fuente: `{payload['source']['path']}`.",
            f"- SHA-256 del archivo fuente: `{payload['source']['sha256']}`.",
            f"- SHA-256 canonico de decisiones: `{payload['decisions_sha256']}`.",
            "- Generador: `build_m1_rule_decisions.py`.",
            "- Matriz: `auditorias_motor/matriz_decisiones_m1_v0_1.json`.",
            "",
            "## 9. Criterio de cierre",
            "",
            "M1 solo puede cerrarse cuando:",
            "",
            "- la reconciliacion 82 + 4 = 86 sea verificada;",
            "- las 86 decisiones y los 34 bloques esten completos;",
            "- las pruebas del generador sean correctas;",
            "- se confirme que no hubo cambio funcional;",
            "- el propietario apruebe expresamente el resultado.",
            "",
            "M2 permanece bloqueada hasta esa aprobacion.",
            "",
            "## 10. Aprobacion y anexo posterior",
            "",
            "El propietario aprobo expresamente el cierre de M1 el 2026-07-27.",
            "",
            "El propietario aprobo el anexo documental M1-A el 2026-07-27.",
            "Contiene el catalogo exacto y legible",
            "86/86 en `auditorias_motor/2026-07-27_M1_A_catalogo_exacto_reglas_formulas.md`",
            "y su artefacto canonico en",
            "`auditorias_motor/catalogo_exacto_reglas_formulas_m1_v0_1.json`.",
            "El anexo no modifica las decisiones de M1 ni altera produccion.",
            "Con esta aprobacion, M1 y M1-A quedan completamente cerradas. M2",
            "es la siguiente fase pendiente y todavia no se ha iniciado.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera la matriz reproducible de decisiones M1."
    )
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_matrix()
    report = render_report(payload)
    matrix_text = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
    report_text = report + "\n"
    if args.check:
        if not args.matrix.exists() or not args.report.exists():
            raise SystemExit("Faltan artefactos M1 para comprobar.")
        if args.matrix.read_text(encoding="utf-8") != matrix_text:
            raise SystemExit("La matriz M1 no es reproducible.")
        if args.report.read_text(encoding="utf-8") != report_text:
            raise SystemExit("El informe M1 no es reproducible.")
        print("M1 artifacts are reproducible.")
        return
    args.matrix.write_text(matrix_text, encoding="utf-8")
    args.report.write_text(report_text, encoding="utf-8")
    print(
        "M1 generated: "
        f"{payload['reconciliation']['current_production_elements']} productive, "
        f"{payload['reconciliation']['contract_infrastructure_elements']} contractual, "
        f"{payload['reconciliation']['decided_elements']} decided."
    )


if __name__ == "__main__":
    main()
