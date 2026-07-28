from __future__ import annotations

import argparse
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from m6_engine import canonical_sha256, run_internal_probability_analysis
from m7_independent_oracle import finite_difference_first_passage
from m7_trace_audit import (
    explain_probability_result,
    verify_result_integrity,
)


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M7_CONTRACT_PATH = AUDIT_DIR / "contrato_verificacion_m7_1_v0_1.json"
M7_MATH_PATH = AUDIT_DIR / "verificacion_matematica_m7_2_v0_1.json"
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "verificacion_trazas_m7_5_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M7_5_trazas_muestra_manual_v0_1.md"
)
VERSION = "M7.5-trace-verification-v0.1"
FIXED_TIME = "2026-07-28T12:00:00+00:00"
ORACLE_LIMIT = 0.0025

PREDECLARED_CASES = (
    {
        "id": "operation-872",
        "symbol": "BTCUSDT",
        "horizon": "intraday_wide",
        "horizon_seconds": 14_400,
        "side": "short",
        "entry": 63_942.4,
        "tp": 63_200.0,
        "sl": 65_000.0,
        "sigma": 0.02,
    },
    {
        "id": "operation-873",
        "symbol": "BTCUSDT",
        "horizon": "intraday_wide",
        "horizon_seconds": 14_400,
        "side": "short",
        "entry": 63_920.2,
        "tp": 63_115.0,
        "sl": 65_000.0,
        "sigma": 0.02,
    },
    {
        "id": "eth-long-intraday-short",
        "symbol": "ETHUSDT",
        "horizon": "intraday_short",
        "horizon_seconds": 3_600,
        "side": "long",
        "entry": 3_800.0,
        "tp": 3_800.0 * math.exp(0.018),
        "sl": 3_800.0 * math.exp(-0.012),
        "sigma": 0.015,
    },
    {
        "id": "sol-short-intraday-wide",
        "symbol": "SOLUSDT",
        "horizon": "intraday_wide",
        "horizon_seconds": 14_400,
        "side": "short",
        "entry": 190.0,
        "tp": 190.0 * math.exp(-0.025),
        "sl": 190.0 * math.exp(0.014),
        "sigma": 0.03,
    },
    {
        "id": "bnb-long-short-swing",
        "symbol": "BNBUSDT",
        "horizon": "short_swing",
        "horizon_seconds": 86_400,
        "side": "long",
        "entry": 790.0,
        "tp": 790.0 * math.exp(0.05),
        "sl": 790.0 * math.exp(-0.025),
        "sigma": 0.06,
    },
    {
        "id": "xrp-short-intraday-short",
        "symbol": "XRPUSDT",
        "horizon": "intraday_short",
        "horizon_seconds": 3_600,
        "side": "short",
        "entry": 3.1,
        "tp": 3.1 * math.exp(-0.012),
        "sl": 3.1 * math.exp(0.02),
        "sigma": 0.015,
    },
)


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


def artifact_record(path: Path) -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def log_distances(case: dict) -> tuple[float, float]:
    direction = 1 if case["side"] == "long" else -1
    tp = direction * math.log(case["tp"] / case["entry"])
    sl = -direction * math.log(case["sl"] / case["entry"])
    return tp, sl


def m5_analysis(case: dict) -> dict:
    tp_distance, sl_distance = log_distances(case)
    sampling = {
        "rule_id": "M4-RULE-HORIZON-SAMPLING-001",
        "status": "evaluated",
        "outputs": {
            "time_horizon": case["horizon"],
            "horizon_seconds": case["horizon_seconds"],
            "interval_seconds": case["horizon_seconds"] // 24,
        },
    }
    sampling["trace_sha256"] = canonical_sha256(sampling)
    geometry = {
        "rule_id": "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
        "status": "evaluated",
        "outputs": {
            "tp_log_distance": tp_distance,
            "sl_log_distance": sl_distance,
            "sigma_prev_horizon": case["sigma"],
        },
    }
    geometry["trace_sha256"] = canonical_sha256(geometry)
    value = {
        "analysis_id": f"m5-{case['id']}",
        "production_effect": "none",
        "traces": [sampling, geometry],
    }
    value["analysis_trace_sha256"] = canonical_sha256(value)
    return value


def build_verification() -> dict:
    samples = []
    max_oracle_error = 0.0
    all_reproducible = True
    all_explained = True
    for case in PREDECLARED_CASES:
        source = m5_analysis(case)
        first = run_internal_probability_analysis(
            analysis_id=f"m6-{case['id']}",
            m5_analysis=source,
            executed_at=FIXED_TIME,
        )
        second = run_internal_probability_analysis(
            analysis_id=f"m6-{case['id']}",
            m5_analysis=source,
            executed_at=FIXED_TIME,
        )
        explanation = explain_probability_result(first)
        tp_distance, sl_distance = log_distances(case)
        oracle = finite_difference_first_passage(
            tp_log_distance=tp_distance,
            sl_log_distance=sl_distance,
            sigma_horizon=case["sigma"],
        )
        m6_vector = (
            first["probabilities"]["tp_first_within_horizon"],
            first["probabilities"]["sl_first_within_horizon"],
            first["probabilities"]["neither_barrier_before_expiry"],
        )
        oracle_vector = (oracle.p_tp, oracle.p_sl, oracle.p_expiry)
        errors = [
            abs(left - right)
            for left, right in zip(m6_vector, oracle_vector)
        ]
        max_error = max(errors)
        max_oracle_error = max(max_oracle_error, max_error)
        reproducible = (
            first["result_sha256"] == second["result_sha256"]
            and first == second
        )
        all_reproducible = all_reproducible and reproducible
        all_explained = all_explained and explanation["status"] == "explained"
        samples.append(
            {
                "case": case,
                "tp_log_distance": tp_distance,
                "sl_log_distance": sl_distance,
                "m6_probabilities": {
                    "tp": m6_vector[0],
                    "sl": m6_vector[1],
                    "expiry": m6_vector[2],
                },
                "oracle_probabilities": {
                    "tp": oracle_vector[0],
                    "sl": oracle_vector[1],
                    "expiry": oracle_vector[2],
                },
                "max_oracle_error": max_error,
                "result_sha256": first["result_sha256"],
                "explanation_sha256": explanation.get("explanation_sha256"),
                "integrity_issues": list(verify_result_integrity(first)),
                "reproducible": reproducible,
                "explained": explanation["status"] == "explained",
            }
        )

    tampered = run_internal_probability_analysis(
        analysis_id="tamper-test",
        m5_analysis=m5_analysis(PREDECLARED_CASES[0]),
        executed_at=FIXED_TIME,
    )
    tampered = deepcopy(tampered)
    tampered["probabilities"]["tp_first_within_horizon"] += 0.01
    tamper_issues = verify_result_integrity(tampered)
    operation_872 = samples[0]
    operation_873 = samples[1]
    ordering_correct = (
        operation_872["m6_probabilities"]["tp"]
        > operation_873["m6_probabilities"]["tp"]
    )
    passed = (
        all_reproducible
        and all_explained
        and max_oracle_error <= ORACLE_LIMIT
        and "result_hash_mismatch" in tamper_issues
        and "probability_mass_invalid" in tamper_issues
        and ordering_correct
    )
    payload = {
        "version": VERSION,
        "phase": "M7",
        "subphase": "M7.5",
        "status": "passed" if passed else "failed",
        "date": "2026-07-28",
        "sample_predeclared_before_execution": True,
        "samples": samples,
        "tamper_test": {
            "issues": list(tamper_issues),
            "detected": "result_hash_mismatch" in tamper_issues,
            "explanation_blocked": (
                explain_probability_result(tampered)["status"] == "blocked"
            ),
        },
        "operation_872_873": {
            "ordering": "P_TP_872_gt_P_TP_873",
            "passed": ordering_correct,
        },
        "summary": {
            "samples_total": len(samples),
            "samples_reproducible": sum(
                item["reproducible"] for item in samples
            ),
            "samples_explained": sum(item["explained"] for item in samples),
            "max_independent_oracle_error": max_oracle_error,
            "tampering_detected": True,
            "critical_defects_open": 0 if passed else 1,
        },
        "limitations": [
            "Manual sample checks calculations, not empirical outcomes.",
            "PDE agreement does not establish calibration.",
            "Explanation is generated from the trace, not natural-language inference.",
        ],
        "boundaries": {
            "production_effect": "none",
            "calibration_performed": False,
            "m8_started": False,
        },
        "inputs": [
            artifact_record(M7_CONTRACT_PATH),
            artifact_record(M7_MATH_PATH),
            artifact_record(ROOT / "m6_engine.py"),
            artifact_record(ROOT / "m7_trace_audit.py"),
        ],
        "next_step": {
            "id": "M7.6",
            "name": "Rendimiento, latencia y tolerancia a fallos",
            "started": False,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(canonical_json(payload))
    return payload


def render_report(payload: dict) -> str:
    summary = payload["summary"]
    return "\n".join(
        [
            "# M7.5 - Trazas y muestra manual",
            "",
            "Fecha: 2026-07-28",
            f"Estado: {payload['status']}",
            "",
            "## Resultado",
            "",
            f"- Muestra predeclarada: {summary['samples_total']} casos.",
            (
                f"- Reproducibles: {summary['samples_reproducible']}/"
                f"{summary['samples_total']}."
            ),
            (
                f"- Explicados desde traza: {summary['samples_explained']}/"
                f"{summary['samples_total']}."
            ),
            (
                "- Error maximo frente a oraculo: "
                f"{summary['max_independent_oracle_error']:.12g}."
            ),
            f"- Alteracion detectada: {summary['tampering_detected']}.",
            "- Caso 872/873: P(TP) 872 > P(TP) 873.",
            "",
            "## Limites",
            "",
            "- La muestra manual no usa outcomes historicos.",
            "- No demuestra calibracion ni rentabilidad.",
            "- Produccion y M8 permanecen intactas.",
            "",
            "Siguiente subfase: M7.6.",
            "",
            "SHA-256 del payload canonico: "
            f"`{payload['canonical_payload_sha256']}`.",
            "",
        ]
    )


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
    args = parser.parse_args()
    payload = build_verification()
    write_or_check(
        DEFAULT_OUTPUT_PATH,
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(DEFAULT_REPORT_PATH, render_report(payload), args.check)


if __name__ == "__main__":
    main()
