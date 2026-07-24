from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


VALID_STATUSES = {
    "fundamentada",
    "heuristica",
    "empirica_provisional",
    "duplicada",
    "incoherente",
    "sin_respaldo",
    "retirada",
}

SOURCES = {
    "BINANCE_USDM_API": {
        "kind": "official_data_definition",
        "title": "Binance USD-M Futures REST API - Market Data",
        "url": "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data",
        "supports": "Campos y endpoints de precio, klines, profundidad, aggTrades, funding, OI y ratios.",
        "does_not_support": "No valida umbrales, pesos ni capacidad predictiva del motor.",
    },
    "COINGECKO_MARKETS_API": {
        "kind": "official_data_definition",
        "title": "CoinGecko API - Coins Markets",
        "url": "https://docs.coingecko.com/reference/coins-markets",
        "supports": "Campos de mercado y variaciones 1h/24h/7d de los activos consultados.",
        "does_not_support": "No valida el breadth 58/42 ni su ajuste de +/-2 puntos.",
    },
    "COINGECKO_GLOBAL_API": {
        "kind": "official_data_definition",
        "title": "CoinGecko API - Crypto Global Market Data",
        "url": "https://docs.coingecko.com/reference/crypto-global",
        "supports": "Capitalizacion, volumen y dominancia global.",
        "does_not_support": "No valida interpretaciones direccionales del motor.",
    },
    "ALTERNATIVE_FNG": {
        "kind": "provider_methodology",
        "title": "Alternative.me Crypto Fear & Greed Index",
        "url": "https://alternative.me/crypto/fear-and-greed-index/",
        "supports": "Definicion, escala 0-100, componentes y API del indice.",
        "does_not_support": "El proveedor declara que no es recomendacion; no valida 75/25 ni la penalizacion de 1.5 puntos.",
    },
    "WILDER_1978": {
        "kind": "recognized_manual",
        "title": "J. Welles Wilder, New Concepts in Technical Trading Systems (1978)",
        "url": "http://dspace.lib.uom.gr/handle/2159/29408",
        "supports": "Procedencia reconocida de RSI y ATR y sus construcciones originales.",
        "does_not_support": "No valida nuestros pesos predictivos. RSI/ATR del codigo usan media simple reciente, no todo el suavizado original de Wilder.",
    },
    "CFA_TECHNICAL_ANALYSIS": {
        "kind": "recognized_manual",
        "title": "CFA Institute - Technical Analysis refresher",
        "url": "https://www.cfainstitute.org/sites/default/files/-/media/documents/book/curriculum-update/2021-member-guide-refresher-readings.PDF",
        "supports": "Uso descriptivo de medias, cruces y osciladores como RSI.",
        "does_not_support": "No valida los periodos, umbrales ni pesos concretos del motor.",
    },
    "CONT_KUKANOV_STOIKOV": {
        "kind": "primary_empirical_research",
        "title": "Cont, Kukanov y Stoikov - The Price Impact of Order Book Events",
        "url": "https://arxiv.org/abs/1011.6402",
        "supports": "Relacion de corto plazo entre cambios de precio y order-flow imbalance en mejor bid/ask.",
        "does_not_support": "Nuestro desequilibrio estatico de notional top-20 no es el OFI dinamico del estudio ni hereda sus coeficientes.",
    },
    "OSLER_SUPPORT_RESISTANCE": {
        "kind": "primary_empirical_research",
        "title": "Osler - Support for Resistance: Technical Analysis and Intraday Exchange Rates",
        "url": "https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.html",
        "supports": "Evidencia de interrupciones intradia cerca de ciertos soportes/resistencias en FX.",
        "does_not_support": "No valida nuestro detector por media de cinco extremos ni penalizaciones 0.025/0.012.",
    },
    "BROCK_LAKONISHOK_LEBARON": {
        "kind": "primary_empirical_research",
        "title": "Brock, Lakonishok y LeBaron - Simple Technical Trading Rules",
        "url": "https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x",
        "supports": "Antecedente empirico para reglas simples de medias y rangos.",
        "does_not_support": "Resultados de otro activo y periodo; no valida los pesos del motor ni probabilidad TP.",
    },
    "LO_MAMAYSKY_WANG": {
        "kind": "primary_empirical_research",
        "title": "Lo, Mamaysky y Wang - Foundations of Technical Analysis",
        "url": "https://www.mit.edu/people/wangj/pap/LoMamayskyWang00.pdf",
        "supports": "Los patrones tecnicos pueden formalizarse y someterse a pruebas estadisticas.",
        "does_not_support": "No convierte una regla tecnica concreta en probabilidad calibrada sin validacion.",
    },
    "FIBONACCI_2022": {
        "kind": "primary_empirical_research",
        "title": "Tsinaslanidis, Guijarro y Voukelatos - Automatic identification and evaluation of Fibonacci retracements",
        "url": "https://doi.org/10.1016/j.eswa.2021.115893",
        "supports": "Evaluacion automatizada de zonas Fibonacci en tres mercados de renta variable.",
        "does_not_support": "No encontro diferencia estadistica frente a zonas no Fibonacci y la estrategia quedo por debajo de buy-and-hold.",
    },
    "BRIER_1950": {
        "kind": "primary_probability_research",
        "title": "Brier - Verification of Forecasts Expressed in Terms of Probability",
        "url": "https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2",
        "supports": "Evaluacion de previsiones probabilisticas contra resultados observados.",
        "does_not_support": "Un score heuristico no se convierte en probabilidad por estar acotado entre 0 y 1.",
    },
    "GNEITING_RAFTERY_2007": {
        "kind": "primary_probability_research",
        "title": "Gneiting y Raftery - Strictly Proper Scoring Rules, Prediction, and Estimation",
        "url": "https://doi.org/10.1198/016214506000001437",
        "supports": "Marco de scoring propio para evaluar distribuciones probabilisticas.",
        "does_not_support": "No valida la suma manual de biases usada por el motor actual.",
    },
    "CORP_CALIBRATION": {
        "kind": "primary_probability_research",
        "title": "Dimitriadis, Gneiting y Jordan - Reliability diagrams revisited",
        "url": "https://arxiv.org/abs/2008.03033",
        "supports": "Una probabilidad esta calibrada cuando coincide con frecuencias observadas; propone diagnostico reproducible.",
        "does_not_support": "No acredita la calibracion actual, que todavia no se ha demostrado.",
    },
    "INTERNAL_V09_AUDIT": {
        "kind": "internal_empirical_evidence",
        "title": "Auditoria profunda de 184 operaciones / 67 resueltas v0.9",
        "path": "auditorias_aprendizaje/2026-07-06_operaciones_cerradas_184_auditoria_profunda_motor_v0_9.md",
        "supports": "Origen interno de los frenos v0.10 y de varias hipotesis de riesgo.",
        "does_not_support": "No es validacion independiente; mezcla versiones y tiene muestras pequenas por subgrupo.",
    },
    "INTERNAL_ENGINE_HISTORY": {
        "kind": "internal_change_history",
        "title": "Historial de cambios del motor",
        "path": "HISTORIAL_CAMBIOS_MOTOR_ANALISIS.md",
        "supports": "Motivacion y version de incorporacion de reglas del proyecto.",
        "does_not_support": "Documentar una regla no demuestra su validez predictiva.",
    },
    "INTERNAL_ENGINE_SPEC": {
        "kind": "internal_specification",
        "title": "Especificacion del motor de analisis",
        "path": "ESPECIFICACION_MOTOR_ANALISIS.md",
        "supports": "Intencion funcional y semantica declarada del sistema.",
        "does_not_support": "No es una fuente externa ni una validacion estadistica.",
    },
}


GROUPS = {
    "analysis_math": {
        "pct_from_entry",
        "pct_between",
        "clamp_float",
        "probability_range",
        "score_to_percent",
        "format_optional_pct",
        "format_optional_number",
        "format_liquidation_mass",
    },
    "analysis_empirical": {
        "build_risk_calibration_context",
        "side_signed_contra",
        "timeframe_contra_side",
        "rsi_extreme_against_entry",
        "stricter_grade_cap",
        "cap_grade",
        "build_risk_calibration_metric",
    },
    "analysis_data_context": {
        "time_horizon_profile",
        "timeframe_for",
        "derivatives_for_horizon",
        "nearest_named_price",
        "classify_trade_price_against_fibs",
        "fibonacci_level_confluence",
        "classify_entry_order_type",
        "nearest_liquidation_cluster",
        "liquidation_cluster_distance_pct",
        "liquidation_proximity",
        "dominant_cluster_before_stop",
    },
    "analysis_non_scoring": {
        "build_liquidation_observation",
        "build_liquidation_metric",
        "build_fibonacci_metric",
        "build_zone_analysis_metric",
        "build_plain_summary",
        "build_explained_metrics",
        "build_score_metrics",
        "build_invalidation_rules",
        "multi_tf_display_score",
    },
}


def sha256_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def analysis_classification(name: str) -> dict:
    if name in GROUPS["analysis_math"]:
        return classification(
            role="pure_math_or_presentation",
            status="fundamentada",
            statement="Transformacion aritmetica o de presentacion; no aporta evidencia predictiva por si sola.",
            sources=[],
            decision="mantener_y_probar_invariantes",
            rule_bearing=False,
        )
    if name in GROUPS["analysis_empirical"]:
        return classification(
            role="internal_empirical_risk_gate",
            status="empirica_provisional",
            statement="Regla nacida de auditorias internas; requiere muestra comparable nueva y validacion temporal.",
            sources=["INTERNAL_V09_AUDIT", "INTERNAL_ENGINE_HISTORY"],
            decision="aislar_y_revalidar",
        )
    if name in GROUPS["analysis_data_context"]:
        return classification(
            role="context_transform",
            status="heuristica",
            statement="Transforma contexto del plan; la convencion es interna y sus umbrales no tienen respaldo externo exacto.",
            sources=["INTERNAL_ENGINE_SPEC", "INTERNAL_ENGINE_HISTORY"],
            decision="documentar_y_validar",
        )
    if name in GROUPS["analysis_non_scoring"]:
        return classification(
            role="explanation_or_observation",
            status="heuristica",
            statement="Capa explicativa u observacional; no debe interpretarse como probabilidad validada.",
            sources=["INTERNAL_ENGINE_SPEC", "INTERNAL_ENGINE_HISTORY"],
            decision="mantener_fuera_del_scoring_hasta_validacion",
            rule_bearing=False,
        )
    source_ids = ["INTERNAL_ENGINE_SPEC", "INTERNAL_ENGINE_HISTORY"]
    if "fibonacci" in name:
        source_ids.append("FIBONACCI_2022")
    if name in {"technical_timeframe_score", "build_technical_rating", "trend_score", "classify_market_regime", "market_regime_direction_bias"}:
        source_ids.extend(["WILDER_1978", "CFA_TECHNICAL_ANALYSIS", "BROCK_LAKONISHOK_LEBARON", "LO_MAMAYSKY_WANG"])
    if name in {"level_risk_penalty", "build_target_path_quality"}:
        source_ids.append("OSLER_SUPPORT_RESISTANCE")
    if name in {"taker_flow_score", "cvd_flow_score", "combined_contradiction_penalty"}:
        source_ids.append("CONT_KUKANOV_STOIKOV")
    if name in {"calculate_expected_value", "build_probability_ranges", "range_probability_for_context"}:
        source_ids.extend(["BRIER_1950", "GNEITING_RAFTERY_2007", "CORP_CALIBRATION"])
    return classification(
        role="predictive_or_decision_rule",
        status="heuristica",
        statement="Regla ejecutable del champion actual. El concepto puede tener antecedentes, pero formula, umbral y peso exactos son internos y no estan calibrados.",
        sources=source_ids,
        decision="reformular_o_calibrar_en_challenger",
    )


def data_engine_classification(name: str) -> dict:
    if name in {"parse_klines", "pct", "distance_pct", "fmean", "future_value", "availability", "fib_key"}:
        return classification(
            role="data_or_math_utility",
            status="fundamentada",
            statement="Parseo, disponibilidad o aritmetica determinista sin tesis predictiva propia.",
            sources=["BINANCE_USDM_API"],
            decision="mantener_y_verificar",
            rule_bearing=False,
        )
    if name == "ema":
        return classification(
            role="technical_indicator",
            status="fundamentada",
            statement="EMA estandar con alpha=2/(periodo+1), inicializada con el primer valor de la ventana.",
            sources=["CFA_TECHNICAL_ANALYSIS"],
            decision="mantener_definicion_y_auditar_inicializacion",
        )
    if name in {"rsi", "atr"}:
        return classification(
            role="technical_indicator_variant",
            status="heuristica",
            statement="Indicador de origen Wilder, pero esta implementacion usa media simple de la ventana reciente y no reproduce todo el suavizado original.",
            sources=["WILDER_1978", "CFA_TECHNICAL_ANALYSIS"],
            decision="renombrar_variante_o_implementar_wilder",
        )
    if name in {
        "summarize_fibonacci",
        "empty_fibonacci_context",
        "detect_price_pivots",
        "select_recent_fibonacci_swing",
        "nearest_fibonacci_level",
        "classify_fibonacci_price_zone",
    }:
        return classification(
            role="fibonacci_transform",
            status="heuristica",
            statement="Construccion interna de swings y zonas Fibonacci; evidencia externa mixta y sin respaldo para los parametros exactos.",
            sources=["FIBONACCI_2022", "INTERNAL_ENGINE_HISTORY"],
            decision="contexto_secundario_y_prueba_ablation",
        )
    if name in {"detect_levels", "cluster_level"}:
        return classification(
            role="support_resistance_detector",
            status="heuristica",
            statement="Soporte/resistencia tiene antecedentes empiricos, pero el promedio de cinco extremos entre doce candidatos es una convencion propia.",
            sources=["OSLER_SUPPORT_RESISTANCE"],
            decision="comparar_detectores_y_validar",
        )
    if name in {"summarize_order_book", "summarize_trade_flow"}:
        return classification(
            role="microstructure_transform",
            status="empirica_provisional",
            statement="La microestructura respalda estudiar desequilibrio y flujo, pero las proxies actuales no equivalen al OFI academico y necesitan validacion propia.",
            sources=["BINANCE_USDM_API", "CONT_KUKANOV_STOIKOV"],
            decision="mantener_peso_bajo_y_validar",
        )
    return classification(
        role="market_snapshot_transform",
        status="heuristica",
        statement="Agregacion interna de datos de mercado; campos oficiales, ventanas y resumenes elegidos por el proyecto.",
        sources=["BINANCE_USDM_API", "COINGECKO_MARKETS_API", "COINGECKO_GLOBAL_API", "ALTERNATIVE_FNG"],
        decision="documentar_frescura_unidades_y_validar",
    )


def classification(
    *,
    role: str,
    status: str,
    statement: str,
    sources: list[str],
    decision: str,
    rule_bearing: bool = True,
) -> dict:
    if status not in VALID_STATUSES:
        raise ValueError(f"Estado invalido: {status}")
    return {
        "role": role,
        "status": status,
        "provenance_statement": statement,
        "source_ids": list(dict.fromkeys(sources)),
        "proposed_decision": decision,
        "rule_bearing": rule_bearing,
    }


def classify_function(module: str, name: str) -> dict:
    if module == "analysis_engine.py":
        return analysis_classification(name)
    if module == "data_engine.py":
        return data_engine_classification(name)
    if module == "market_data.py":
        return classification(
            role="official_data_transport",
            status="fundamentada",
            statement="Cliente y transporte de datos; la fuente oficial define campos, no su uso predictivo posterior.",
            sources=["BINANCE_USDM_API", "COINGECKO_MARKETS_API", "COINGECKO_GLOBAL_API", "ALTERNATIVE_FNG"],
            decision="mantener_con_controles_de_frescura",
            rule_bearing=False,
        )
    if module == "liquidation_data.py":
        return classification(
            role="third_party_liquidation_normalization",
            status="heuristica",
            statement="Normaliza un proveedor gratuito no oficial de Binance y limitado a posiciones publicas Hyperliquid; no hay contrato externo versionado que valide clusters o masa.",
            sources=["INTERNAL_ENGINE_HISTORY", "INTERNAL_ENGINE_SPEC"],
            decision="mantener_observacional_y_validar_con_mapas_visibles",
        )
    if module == "learning_evidence.py":
        status = "heuristica" if name in {"resolve_touch_with_trades", "first_plan_touch", "recorded_result_consistency", "reconstructed_plan_result"} else "fundamentada"
        return classification(
            role="post_trade_evidence_reconstruction",
            status=status,
            statement="Reconstruccion post-trade determinista con velas/trades oficiales; las reglas de ambiguedad y desempate son convenciones operativas auditables.",
            sources=["BINANCE_USDM_API", "INTERNAL_ENGINE_HISTORY"],
            decision="mantener_separado_de_features_predictivas",
            rule_bearing=status == "heuristica",
        )
    if module == "economic_metrics.py":
        return classification(
            role="post_trade_economic_normalization",
            status="fundamentada",
            statement="Normalizacion contable post-trade; no debe entrar como variable predictiva retrospectiva.",
            sources=["INTERNAL_ENGINE_HISTORY"],
            decision="mantener_como_outcome",
            rule_bearing=False,
        )
    if module == "versioning.py":
        return classification(
            role="governance_and_data_contract",
            status="fundamentada",
            statement="Versionado y separacion pre-trade/post-trade para trazabilidad y prevencion de leakage.",
            sources=["INTERNAL_ENGINE_SPEC", "INTERNAL_ENGINE_HISTORY"],
            decision="mantener",
            rule_bearing=False,
        )
    if module == "app.py":
        status = "empirica_provisional" if name in {
            "build_signal_diagnostics",
            "classify_analysis_verdict",
            "build_learning_signal",
            "build_zone_learning_context",
            "classify_failure_type",
        } else "heuristica"
        return classification(
            role="retrospective_learning_label_or_audit",
            status=status,
            statement="Taxonomia retrospectiva del aprendizaje. Describe resultados y candidatos; no es una variable pre-trade ni una autorizacion automatica para cambiar produccion.",
            sources=["INTERNAL_V09_AUDIT", "INTERNAL_ENGINE_HISTORY", "BRIER_1950", "CORP_CALIBRATION"],
            decision="mantener_append_only_y_validar_antes_de_promocion",
        )
    return classification(
        role="unclassified",
        status="sin_respaldo",
        statement="Funcion dentro del alcance sin procedencia especifica localizada.",
        sources=[],
        decision="investigar_antes_de_mantener",
    )


def build_matrix(inventory: dict) -> dict:
    functions = []
    for module in inventory["modules"]:
        module_path = module["path"]
        for function in module["functions"]:
            provenance = classify_function(module_path, function["name"])
            entry = {
                "stable_id": f"{module_path}:{function['name']}",
                "module": module_path,
                "function": function["name"],
                "line": function["line"],
                "end_line": function["end_line"],
                "function_inventory_sha256": sha256_json(function),
                **provenance,
                "numeric_literals": function["numeric_literals"],
                "formula_fragments": function["formula_fragments"],
                "called_functions": function["called_functions"],
            }
            functions.append(entry)

    statuses = Counter(item["status"] for item in functions)
    roles = Counter(item["role"] for item in functions)
    output = {
        "provenance_schema": "motor-provenance-v0.1",
        "inventory_sha256": sha256_json(inventory),
        "sources": SOURCES,
        "summary": {
            "functions": len(functions),
            "rule_bearing_functions": sum(1 for item in functions if item["rule_bearing"]),
            "explicitly_classified_functions": sum(1 for item in functions if item["provenance_statement"]),
            "status_counts": dict(sorted(statuses.items())),
            "role_counts": dict(sorted(roles.items())),
            "numeric_literal_occurrences": sum(len(item["numeric_literals"]) for item in functions),
            "formula_fragments": sum(len(item["formula_fragments"]) for item in functions),
        },
        "functions": functions,
    }
    output["matrix_sha256"] = sha256_json(output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera la matriz de procedencia de todas las funciones auditadas.")
    parser.add_argument(
        "--inventory",
        default="auditorias_motor/inventario_reglas_motor_v0_1.json",
        help="Inventario ejecutable E1.1.",
    )
    parser.add_argument(
        "--output",
        default="auditorias_motor/matriz_procedencia_funciones_v0_1.json",
        help="Ruta de salida.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory_path = Path(args.inventory)
    output_path = Path(args.output)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    matrix = build_matrix(inventory)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(matrix, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(matrix["summary"], indent=2, ensure_ascii=True))
    print(f"matrix_sha256={matrix['matrix_sha256']}")


if __name__ == "__main__":
    main()
