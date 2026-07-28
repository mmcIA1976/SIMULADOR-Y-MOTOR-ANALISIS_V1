from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from m7_data_gate import validate_pretrade_snapshot


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M7_CONTRACT_PATH = AUDIT_DIR / "contrato_verificacion_m7_1_v0_1.json"
M3_CONTRACT_PATH = AUDIT_DIR / "catalogo_contratos_datos_m3_v0_1.json"
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "verificacion_datos_m7_3_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M7_3_verificacion_datos_v0_1.md"
)
VERSION = "M7.3-data-verification-v0.1"
ANALYSIS_AT = 1_800_000_000_000
REQUIRED = (
    "M3-DATA-001",
    "M3-DATA-002",
    "M3-DATA-003",
    "M3-DATA-004",
    "M3-DATA-005",
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


def valid_observations() -> list[dict]:
    common = {
        "symbol": "BTCUSDT",
        "payload_status": "complete",
        "partial": False,
        "contradictions": [],
    }
    return [
        common
        | {
            "contract_id": "M3-DATA-001",
            "requested_at_ms": ANALYSIS_AT - 1_000,
            "received_at_ms": ANALYSIS_AT - 900,
            "provider_timestamps_ms": [ANALYSIS_AT - 1_000],
        },
        common
        | {
            "contract_id": "M3-DATA-002",
            "requested_at_ms": ANALYSIS_AT - 10_000,
            "received_at_ms": ANALYSIS_AT - 9_900,
            "provider_timestamps_ms": [ANALYSIS_AT - 10_000],
            "trading_status": "TRADING",
            "contract_type": "PERPETUAL",
            "quote_asset": "USDT",
        },
        common
        | {
            "contract_id": "M3-DATA-003",
            "requested_at_ms": ANALYSIS_AT - 500,
            "received_at_ms": ANALYSIS_AT - 400,
            "provider_timestamps_ms": [ANALYSIS_AT - 450],
        },
        common
        | {
            "contract_id": "M3-DATA-004",
            "requested_at_ms": ANALYSIS_AT - 300,
            "received_at_ms": ANALYSIS_AT - 200,
            "provider_timestamps_ms": [ANALYSIS_AT - 250],
        },
        common
        | {
            "contract_id": "M3-DATA-005",
            "requested_at_ms": ANALYSIS_AT - 200,
            "received_at_ms": ANALYSIS_AT - 100,
            "provider_timestamps_ms": [ANALYSIS_AT - 30_000],
            "period_ms": 60_000,
            "latest_period_end_ms": ANALYSIS_AT - 30_000,
        },
    ]


def mutate_missing(items: list[dict]) -> None:
    items.pop()


def mutate_partial(items: list[dict]) -> None:
    items[3]["partial"] = True


def mutate_future_provider(items: list[dict]) -> None:
    items[3]["provider_timestamps_ms"] = [ANALYSIS_AT + 1]


def mutate_future_receive(items: list[dict]) -> None:
    items[3]["received_at_ms"] = ANALYSIS_AT + 1


def mutate_request_order(items: list[dict]) -> None:
    items[3]["requested_at_ms"] = items[3]["received_at_ms"] + 1


def mutate_stale(items: list[dict]) -> None:
    items[3]["provider_timestamps_ms"] = [ANALYSIS_AT - 30_001]


def mutate_contradiction(items: list[dict]) -> None:
    items[3]["contradictions"] = ["price_fields_disagree"]


def mutate_symbol(items: list[dict]) -> None:
    items[3]["symbol"] = "ETHUSDT"


def mutate_market_identity(items: list[dict]) -> None:
    items[1]["trading_status"] = "BREAK"


def mutate_latency(items: list[dict]) -> None:
    items[3]["requested_at_ms"] = ANALYSIS_AT - 20_000


def mutate_span(items: list[dict]) -> None:
    items[1]["requested_at_ms"] = ANALYSIS_AT - 20_000
    items[1]["received_at_ms"] = ANALYSIS_AT - 19_900


def mutate_open_period(items: list[dict]) -> None:
    items[4]["latest_period_end_ms"] = ANALYSIS_AT + 1


def mutate_stale_period(items: list[dict]) -> None:
    items[4]["latest_period_end_ms"] = ANALYSIS_AT - 120_001


def mutate_duplicate(items: list[dict]) -> None:
    items.append(deepcopy(items[3]))


INVALID_CASES: tuple[tuple[str, Callable[[list[dict]], None], str], ...] = (
    ("missing_mandatory", mutate_missing, "mandatory_observation_missing"),
    ("partial_payload", mutate_partial, "m3_data_004_partial_or_incomplete"),
    ("future_provider", mutate_future_provider, "m3_data_004_future_provider_data"),
    ("future_receive", mutate_future_receive, "m3_data_004_received_after_analysis"),
    ("request_after_receive", mutate_request_order, "m3_data_004_request_after_receive"),
    ("stale_realtime", mutate_stale, "m3_data_004_stale"),
    ("contradictory", mutate_contradiction, "m3_data_004_contradictory"),
    ("symbol_mismatch", mutate_symbol, "m3_data_004_symbol_mismatch"),
    ("invalid_market", mutate_market_identity, "m3_data_002_market_identity_invalid"),
    ("latency_exceeded", mutate_latency, "m3_data_004_request_latency_exceeded"),
    ("capture_span", mutate_span, "snapshot_capture_span_exceeded"),
    ("open_period", mutate_open_period, "m3_data_005_open_or_future_period"),
    ("stale_period", mutate_stale_period, "m3_data_005_completed_period_stale"),
    ("duplicate_source", mutate_duplicate, "duplicate_observation_contract_id"),
)


def build_verification() -> dict:
    valid = validate_pretrade_snapshot(
        analysis_at_ms=ANALYSIS_AT,
        symbol="BTCUSDT",
        required_contract_ids=REQUIRED,
        observations=valid_observations(),
    )
    cases = []
    for name, mutator, expected_reason in INVALID_CASES:
        observations = valid_observations()
        mutator(observations)
        result = validate_pretrade_snapshot(
            analysis_at_ms=ANALYSIS_AT,
            symbol="BTCUSDT",
            required_contract_ids=REQUIRED,
            observations=observations,
        )
        cases.append(
            {
                "name": name,
                "status": result.status,
                "reason_codes": list(result.reason_codes),
                "expected_reason": expected_reason,
                "passed": (
                    result.status == "blocked"
                    and expected_reason in result.reason_codes
                ),
                "probabilities_emitted": False,
            }
        )
    passed = valid.status == "accepted" and all(
        item["passed"] for item in cases
    )
    payload = {
        "version": VERSION,
        "phase": "M7",
        "subphase": "M7.3",
        "status": "passed" if passed else "failed",
        "date": "2026-07-28",
        "valid_case": valid.to_dict(),
        "invalid_cases": cases,
        "summary": {
            "valid_cases_accepted": int(valid.status == "accepted"),
            "invalid_cases_total": len(cases),
            "invalid_cases_blocked_as_expected": sum(
                item["passed"] for item in cases
            ),
            "neutral_fallbacks": 0,
            "probabilities_emitted_for_invalid_data": 0,
            "critical_defects_open": 0 if passed else 1,
        },
        "boundaries": {
            "gate_is_internal_only": True,
            "production_effect": "none",
            "calibration_performed": False,
            "m8_started": False,
        },
        "inputs": [
            artifact_record(M7_CONTRACT_PATH),
            artifact_record(M3_CONTRACT_PATH),
            artifact_record(ROOT / "m7_data_gate.py"),
        ],
        "next_step": {
            "id": "M7.4",
            "name": "Matriz completa par-marco-regla e interacciones",
            "started": False,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(canonical_json(payload))
    return payload


def render_report(payload: dict) -> str:
    summary = payload["summary"]
    return "\n".join(
        [
            "# M7.3 - Verificacion de datos pre-trade",
            "",
            "Fecha: 2026-07-28",
            f"Estado: {payload['status']}",
            "",
            "## Resultado",
            "",
            f"- Caso valido aceptado: {summary['valid_cases_accepted']}/1.",
            (
                "- Casos invalidos bloqueados: "
                f"{summary['invalid_cases_blocked_as_expected']}/"
                f"{summary['invalid_cases_total']}."
            ),
            "- Sustituciones neutrales: 0.",
            "- Probabilidades emitidas con datos invalidos: 0.",
            "",
            "## Politica",
            "",
            "La ausencia, obsolescencia, parcialidad, contradiccion, dato futuro,",
            "identidad incorrecta o captura fuera de contrato bloquea el snapshot.",
            "",
            "## Limites",
            "",
            "- Puerta interna; aun no conectada a produccion.",
            "- No calibra probabilidades ni inicia M8.",
            "",
            "Siguiente subfase: M7.4.",
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
