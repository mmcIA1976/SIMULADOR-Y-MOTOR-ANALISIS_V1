from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from m6_first_passage import double_barrier_first_passage


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "verificacion_m6_5_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M6_5_verificacion_propiedades_v0_1.md"
)
VERSION = "M6.5-property-verification-v0.1"

HISTORICAL_CASES = (
    {
        "recommendation_id": 872,
        "symbol": "BTCUSDT",
        "side": "short",
        "time_horizon": "intraday_wide",
        "entry": 63942.4,
        "take_profit": 63200.0,
        "stop_loss": 65000.0,
        "legacy_p_tp": 0.5389,
        "legacy_price_vs_entry_bias": -0.02,
    },
    {
        "recommendation_id": 873,
        "symbol": "BTCUSDT",
        "side": "short",
        "time_horizon": "intraday_wide",
        "entry": 63920.2,
        "take_profit": 63115.0,
        "stop_loss": 65000.0,
        "legacy_p_tp": 0.5889,
        "legacy_price_vs_entry_bias": 0.03,
    },
)
SIGMA_GRID = (0.005, 0.01, 0.02, 0.04, 0.08, 0.16)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry(case: dict) -> dict:
    return {
        "tp_log_distance": math.log(
            case["entry"] / case["take_profit"]
        ),
        "sl_log_distance": math.log(
            case["stop_loss"] / case["entry"]
        ),
    }


def build_verification() -> dict:
    case_rows = []
    geometries = {
        case["recommendation_id"]: geometry(case)
        for case in HISTORICAL_CASES
    }
    for sigma in SIGMA_GRID:
        probabilities = {}
        for case in HISTORICAL_CASES:
            result = double_barrier_first_passage(
                **geometries[case["recommendation_id"]],
                sigma_horizon=sigma,
            )
            probabilities[str(case["recommendation_id"])] = {
                "p_tp": result.p_tp,
                "p_sl": result.p_sl,
                "p_expiry": result.p_expiry,
            }
        case_rows.append(
            {
                "sigma_horizon_scenario": sigma,
                "probabilities": probabilities,
                "ordering": (
                    "872_gt_873"
                    if probabilities["872"]["p_tp"]
                    > probabilities["873"]["p_tp"]
                    else "ordering_failure"
                ),
            }
        )
    if any(row["ordering"] != "872_gt_873" for row in case_rows):
        raise ValueError("historical_872_873_ordering_not_corrected")

    grid_results = []
    max_mass_error = 0.0
    for tp_distance in (0.005, 0.01, 0.02, 0.04, 0.08):
        for sl_distance in (0.005, 0.01, 0.02, 0.04, 0.08):
            for sigma in (0.005, 0.01, 0.02, 0.04, 0.08):
                result = double_barrier_first_passage(
                    tp_log_distance=tp_distance,
                    sl_log_distance=sl_distance,
                    sigma_horizon=sigma,
                )
                mass_error = abs(
                    result.p_tp + result.p_sl + result.p_expiry - 1
                )
                max_mass_error = max(max_mass_error, mass_error)
                grid_results.append(
                    {
                        "tp_log_distance": tp_distance,
                        "sl_log_distance": sl_distance,
                        "sigma_horizon": sigma,
                        "mass_error": mass_error,
                        "probabilities_in_unit_interval": all(
                            0 <= value <= 1
                            for value in (
                                result.p_tp,
                                result.p_sl,
                                result.p_expiry,
                            )
                        ),
                    }
                )
    if max_mass_error > 1e-12:
        raise ValueError("probability_mass_grid_failure")
    if not all(
        item["probabilities_in_unit_interval"]
        for item in grid_results
    ):
        raise ValueError("probability_bounds_grid_failure")

    monotonic_rows = []
    previous = None
    for tp_distance in (0.005, 0.01, 0.02, 0.04, 0.08):
        result = double_barrier_first_passage(
            tp_log_distance=tp_distance,
            sl_log_distance=0.04,
            sigma_horizon=0.03,
        )
        monotonic_rows.append(
            {
                "tp_log_distance": tp_distance,
                "p_tp": result.p_tp,
            }
        )
        if previous is not None and result.p_tp > previous + 1e-12:
            raise ValueError("farther_tp_increased_probability")
        previous = result.p_tp

    epsilon = 1e-8
    left = double_barrier_first_passage(
        tp_log_distance=0.03 - epsilon,
        sl_log_distance=0.04,
        sigma_horizon=0.03,
    )
    right = double_barrier_first_passage(
        tp_log_distance=0.03 + epsilon,
        sl_log_distance=0.04,
        sigma_horizon=0.03,
    )
    continuity_delta = max(
        abs(left.p_tp - right.p_tp),
        abs(left.p_sl - right.p_sl),
        abs(left.p_expiry - right.p_expiry),
    )
    if continuity_delta >= 1e-5:
        raise ValueError("continuity_check_failed")

    payload = {
        "version": VERSION,
        "phase": "M6",
        "subphase": "M6.5",
        "status": "completed_internal_verification_m7_still_required",
        "date": "2026-07-28",
        "historical_case_872_873": {
            "source": (
                "recommendations 872 and 873 read from the project database "
                "on 2026-07-28"
            ),
            "cases": [
                case | geometry(case)
                for case in HISTORICAL_CASES
            ],
            "legacy_ordering": "P_TP_872_lt_P_TP_873",
            "legacy_jump": 0.05,
            "legacy_cause": "binary_price_vs_entry_bias_-0.02_to_+0.03",
            "m6_sigma_scenarios": list(SIGMA_GRID),
            "m6_results": case_rows,
            "m6_ordering": "P_TP_872_gt_P_TP_873_for_every_sigma_scenario",
            "interpretation": (
                "The test verifies geometry ordering only. The sigma grid is "
                "a sensitivity grid, not reconstructed M5 volatility and not "
                "a historical probability claim."
            ),
        },
        "property_results": {
            "mass_grid_cases": len(grid_results),
            "max_mass_error": max_mass_error,
            "all_probabilities_in_unit_interval": True,
            "farther_tp_monotonic_rows": monotonic_rows,
            "farther_tp_never_increases_p_tp": True,
            "continuity_epsilon": epsilon,
            "continuity_max_probability_delta": continuity_delta,
            "continuity_passed": True,
            "long_short_symmetry": "covered_by_tests.test_m6_first_passage",
            "scale_invariance": "covered_by_tests.test_m6_first_passage",
            "horizon_monotonicity": "covered_by_tests.test_m6_first_passage",
            "uncertainty_labeling": "covered_by_tests.test_m6_engine",
        },
        "claims": {
            "software_and_basic_mathematical_properties_verified": True,
            "brownian_model_empirically_validated": False,
            "probabilities_calibrated": False,
            "profitability_established": False,
            "m7_replaced": False,
            "m8_replaced": False,
            "production_authorized": False,
        },
        "source_files": [
            {
                "path": path,
                "sha256": file_sha256(ROOT / path),
            }
            for path in (
                "m6_first_passage.py",
                "m6_competing_risks.py",
                "m6_engine.py",
                "tests/test_m6_first_passage.py",
                "tests/test_m6_competing_risks.py",
                "tests/test_m6_engine.py",
                "tests/test_m6_verification.py",
                "build_m6_verification.py",
            )
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                key: value
                for key, value in payload.items()
                if key != "canonical_payload_sha256"
            }
        )
    )
    return payload


def render_report(verification: dict) -> str:
    case = verification["historical_case_872_873"]
    properties = verification["property_results"]
    lines = [
        "# M6.5 - Verificacion de propiedades",
        "",
        "Fecha: 2026-07-28",
        "Estado: VERIFICACION INTERNA COMPLETADA; M7 SIGUE PENDIENTE",
        "",
        "## Caso historico 872/873",
        "",
        "| Analisis | Entrada | TP | SL | Distancia TP log | Legacy P(TP) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in case["cases"]:
        lines.append(
            f"| {item['recommendation_id']} | {item['entry']:.1f} | "
            f"{item['take_profit']:.1f} | {item['stop_loss']:.1f} | "
            f"{item['tp_log_distance']:.8f} | "
            f"{item['legacy_p_tp']:.4f} |"
        )
    lines.extend(
        [
            "",
            "El 872 tenia el TP mas cercano, pero el score antiguo le asigno",
            "cinco puntos menos por cruzar la condicion binaria precio/entrada.",
            "",
            "El baseline M6 asigna `P_TP(872) > P_TP(873)` en todos los",
            "escenarios sigma de la malla. La malla es una prueba de",
            "sensibilidad geometrica, no una reconstruccion de volatilidad",
            "M5 ni una afirmacion probabilistica retrospectiva.",
            "",
            "## Propiedades",
            "",
            f"- Casos de masa y limites: "
            f"{properties['mass_grid_cases']}.",
            f"- Error maximo de masa: "
            f"{properties['max_mass_error']:.3e}.",
            "- TP mas lejano nunca aumenta P(TP): SI.",
            f"- Delta maximo con perturbacion continua: "
            f"{properties['continuity_max_probability_delta']:.3e}.",
            "- Simetria, escala y monotonia temporal: cubiertas por pruebas.",
            "",
            "## Limites",
            "",
            "- Calibracion empirica: NO.",
            "- Rentabilidad demostrada: NO.",
            "- M7 o M8 sustituidas: NO.",
            "- Produccion autorizada: NO.",
            "",
            "SHA-256 del payload canonico: "
            f"`{verification['canonical_payload_sha256']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            raise SystemExit(f"Generated artifact is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    verification = build_verification()
    write_or_check(
        args.output,
        json.dumps(verification, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(verification), args.check)


if __name__ == "__main__":
    main()
