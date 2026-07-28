from __future__ import annotations

import unittest

from m5_runtime import (
    RuleBlocked,
    RuleDeferred,
    RuleTrace,
    run_rule,
)


FIXED_TIME = "2026-07-27T12:00:00+00:00"


class M52RuntimeTests(unittest.TestCase):
    def execute(self, evaluator, dependencies=None, invariant_evaluator=None):
        return run_rule(
            analysis_id="analysis-1",
            rule_id="RULE-1",
            canonical_family="FAMILY-1",
            formula_ids=("FORMULA-1",),
            inputs={"x": 2.0},
            evaluator=evaluator,
            dependencies=dependencies,
            invariant_evaluator=invariant_evaluator,
            executed_at=FIXED_TIME,
        )

    def test_evaluated_trace_is_complete_and_hash_is_reproducible(self) -> None:
        trace = self.execute(lambda inputs, deps: {"y": inputs["x"] * 2})
        self.assertEqual(trace.status, "evaluated")
        self.assertEqual(trace.outputs, {"y": 4.0})
        self.assertEqual(trace.reason_codes, ())
        self.assertEqual(trace.production_effect, "none")
        self.assertEqual(trace.trace_sha256, trace.trace_sha256)

    def test_blocked_rule_never_emits_neutral_output(self) -> None:
        def evaluator(inputs, deps):
            raise RuleBlocked("missing_x", "x is unavailable")

        trace = self.execute(evaluator)
        self.assertEqual(trace.status, "blocked")
        self.assertEqual(trace.outputs, {})
        self.assertEqual(trace.reason_codes, ("missing_x",))

    def test_deferred_rule_is_distinct_from_blocked(self) -> None:
        def evaluator(inputs, deps):
            raise RuleDeferred("outside_scope", "branch deferred")

        trace = self.execute(evaluator)
        self.assertEqual(trace.status, "deferred")
        self.assertEqual(trace.outputs, {})

    def test_failed_dependency_blocks_child_before_evaluation(self) -> None:
        parent = self.execute(
            lambda inputs, deps: (_ for _ in ()).throw(
                RuleBlocked("missing", "missing")
            )
        )
        child = self.execute(
            lambda inputs, deps: {"should_not_run": True},
            dependencies={"PARENT": parent},
        )
        self.assertEqual(child.status, "blocked")
        self.assertEqual(child.reason_codes, ("dependency_not_evaluated",))
        self.assertEqual(child.outputs, {})

    def test_invariant_failure_blocks_output(self) -> None:
        trace = self.execute(
            lambda inputs, deps: {"y": 4.0},
            invariant_evaluator=lambda inputs, outputs: (
                {"id": "INV-1", "passed": False},
            ),
        )
        self.assertEqual(trace.status, "blocked")
        self.assertEqual(trace.outputs, {})
        self.assertEqual(trace.reason_codes, ("invariant_failed",))

    def test_non_finite_output_becomes_error_without_output(self) -> None:
        trace = self.execute(lambda inputs, deps: {"y": float("nan")})
        self.assertEqual(trace.status, "error")
        self.assertEqual(trace.outputs, {})
        self.assertEqual(
            trace.reason_codes,
            ("unexpected_ValueError",),
        )

    def test_dependency_record_contains_parent_trace_hash(self) -> None:
        parent = self.execute(lambda inputs, deps: {"y": 4.0})
        child = self.execute(
            lambda inputs, deps: {"z": deps["PARENT"].outputs["y"]},
            dependencies={"PARENT": parent},
        )
        self.assertEqual(child.status, "evaluated")
        self.assertEqual(child.dependencies[0]["rule_id"], "PARENT")
        self.assertEqual(
            child.dependencies[0]["trace_sha256"],
            parent.trace_sha256,
        )

    def test_rule_trace_is_immutable(self) -> None:
        trace = self.execute(lambda inputs, deps: {"y": 4.0})
        with self.assertRaises(AttributeError):
            trace.status = "blocked"
        self.assertIsInstance(trace, RuleTrace)


if __name__ == "__main__":
    unittest.main()
