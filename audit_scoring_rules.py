from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_MODULES = (
    "analysis_engine.py",
    "data_engine.py",
    "market_data.py",
    "liquidation_data.py",
    "learning_evidence.py",
    "economic_metrics.py",
    "versioning.py",
)
APP_RULE_FUNCTIONS = {
    "build_economic_audit_report",
    "build_fibonacci_audit_report",
    "build_learning_conclusion",
    "build_learning_pattern_text",
    "build_learning_signal",
    "build_liquidation_audit_report",
    "build_pending_zone_audit_report",
    "build_signal_diagnostics",
    "build_structured_learning_evaluation",
    "build_underweighted_risk_audit_report",
    "build_zone_learning_context",
    "classify_analysis_verdict",
    "classify_failure_type",
    "classify_user_decision_quality",
    "excursion_metrics",
    "group_signal_effectiveness",
    "group_signal_pairs",
    "plan_result_from_operation",
    "signal_learning_read",
    "validate_trade_plan",
    "validate_entry_order",
    "entry_order_type",
    "validate_recommendation_matches_operation",
    "analyze",
    "create_operation",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrae un inventario reproducible de reglas del motor.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Ruta JSON de salida. Sin ella, imprime por stdout.",
    )
    return parser.parse_args()


def source_segment(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node) or ""
    return " ".join(segment.strip().split())


def numeric_literals(node: ast.AST) -> list[dict]:
    values = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant):
            value = child.value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(
                    {
                        "value": value,
                        "line": getattr(child, "lineno", None),
                    }
                )
    return values


def called_functions(node: ast.AST) -> list[str]:
    calls = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            calls.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            parts = []
            current = child.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            calls.add(".".join(reversed(parts)))
    return sorted(calls)


def formula_fragments(source: str, function: ast.FunctionDef) -> list[dict]:
    fragments = []
    accepted = (
        ast.Assign,
        ast.AnnAssign,
        ast.AugAssign,
        ast.If,
        ast.IfExp,
        ast.Compare,
        ast.Return,
    )
    seen = set()
    for node in ast.walk(function):
        if not isinstance(node, accepted):
            continue
        segment = source_segment(source, node)
        if not segment:
            continue
        key = (getattr(node, "lineno", None), type(node).__name__, segment)
        if key in seen:
            continue
        seen.add(key)
        fragments.append(
            {
                "line": getattr(node, "lineno", None),
                "end_line": getattr(node, "end_lineno", None),
                "kind": type(node).__name__,
                "expression": segment,
                "numeric_literals": numeric_literals(node),
            }
        )
    return sorted(
        fragments,
        key=lambda item: (
            item["line"] or 0,
            item["end_line"] or 0,
            item["kind"],
        ),
    )


def function_record(source: str, node: ast.FunctionDef) -> dict:
    arguments = [argument.arg for argument in node.args.posonlyargs]
    arguments.extend(argument.arg for argument in node.args.args)
    arguments.extend(argument.arg for argument in node.args.kwonlyargs)
    return {
        "name": node.name,
        "line": node.lineno,
        "end_line": node.end_lineno,
        "arguments": arguments,
        "docstring": ast.get_docstring(node),
        "called_functions": called_functions(node),
        "numeric_literals": numeric_literals(node),
        "formula_fragments": formula_fragments(source, node),
    }


def module_constants(source: str, tree: ast.Module) -> list[dict]:
    records = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [
            target.id
            for target in targets
            if isinstance(target, ast.Name)
        ]
        if not names:
            continue
        records.append(
            {
                "names": names,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "expression": source_segment(source, node),
                "numeric_literals": numeric_literals(node),
            }
        )
    return records


def should_include_function(module: str, function_name: str) -> bool:
    if module != "app.py":
        return True
    return function_name in APP_RULE_FUNCTIONS


def inspect_module(path: Path) -> dict:
    source_bytes = path.read_bytes()
    source = source_bytes.decode("utf-8")
    tree = ast.parse(source, filename=str(path))
    functions = [
        function_record(source, node)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and should_include_function(path.name, node.name)
    ]
    return {
        "path": path.name,
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "line_count": len(source.splitlines()),
        "module_constants": module_constants(source, tree),
        "functions": functions,
        "summary": {
            "functions": len(functions),
            "module_constants": len(module_constants(source, tree)),
            "numeric_literals": sum(
                len(function["numeric_literals"])
                for function in functions
            ),
            "formula_fragments": sum(
                len(function["formula_fragments"])
                for function in functions
            ),
        },
    }


def build_inventory() -> dict:
    module_names = [
        *DEFAULT_MODULES,
        "app.py",
    ]
    modules = [
        inspect_module(ROOT / module_name)
        for module_name in module_names
        if (ROOT / module_name).exists()
    ]
    return {
        "inventory_schema": "scoring-rule-inventory-v0.1",
        "scope": {
            "purpose": (
                "Inventario mecanico de reglas, formulas, umbrales y "
                "dependencias que intervienen en datos, analisis y aprendizaje."
            ),
            "modules": [module["path"] for module in modules],
            "app_functions": sorted(APP_RULE_FUNCTIONS),
            "limitations": [
                "El inventario mecanico no demuestra validez financiera.",
                "La procedencia teorica se documenta en la fase E1.2.",
                "La coherencia matematica se evalua en la fase E1.3.",
            ],
        },
        "summary": {
            "modules": len(modules),
            "functions": sum(
                module["summary"]["functions"] for module in modules
            ),
            "module_constants": sum(
                module["summary"]["module_constants"] for module in modules
            ),
            "numeric_literals": sum(
                module["summary"]["numeric_literals"] for module in modules
            ),
            "formula_fragments": sum(
                module["summary"]["formula_fragments"] for module in modules
            ),
        },
        "modules": modules,
    }


def main() -> None:
    args = parse_args()
    rendered = json.dumps(
        build_inventory(),
        indent=2,
        ensure_ascii=True,
    )
    if args.output:
        output = args.output
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(output)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
