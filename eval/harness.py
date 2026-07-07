"""Evaluation harness (design Section 21.5). Owner: Divya.

Runs the pipeline over a golden set and computes metrics used by the promotion gate:
- step_coverage: generated steps / expected steps
- grounding_rate: steps with a valid screenshot reference / total steps
- intent_match: predicted process intent == expected
- mean_confidence + ECE-style calibration proxy

CLI:  python -m eval.harness
Gate: python -m eval.harness --gate   (exit 1 if below thresholds)
"""
from __future__ import annotations

import argparse
import json
import sys

from apps.orchestrator.graph import run_pipeline
from processiq_shared.models import ScreenPerception
from processiq_shared.state import AgentState, JobContext

GOLDEN = [
    {
        "name": "create_new_order",
        "screens": 5,
        "expected_intent": "Create New Order",
        "expected_steps": 5,
    }
]

THRESHOLDS = {"step_coverage": 0.9, "grounding_rate": 0.95, "intent_match": 1.0}


def _run_case(case: dict) -> dict:
    state = AgentState(
        job=JobContext(id="eval", tenant_id="eval", process_id="p"),
        screens=[ScreenPerception(artifact_id=f"art_{i}", order=i)
                 for i in range(1, case["screens"] + 1)],
    )
    state = run_pipeline(state)
    sop = state.sop
    grounded = sum(1 for s in sop.steps if s.screenshot_ref) / max(1, len(sop.steps))
    coverage = len(sop.steps) / max(1, case["expected_steps"])
    intent_match = 1.0 if sop.title == case["expected_intent"] else 0.0
    confs = [s.confidence for s in sop.steps] or [0.0]
    return {
        "name": case["name"],
        "step_coverage": round(min(1.0, coverage), 3),
        "grounding_rate": round(grounded, 3),
        "intent_match": intent_match,
        "mean_confidence": round(sum(confs) / len(confs), 3),
    }


def run() -> list[dict]:
    return [_run_case(c) for c in GOLDEN]


def aggregate(results: list[dict]) -> dict:
    keys = ["step_coverage", "grounding_rate", "intent_match", "mean_confidence"]
    return {k: round(sum(r[k] for r in results) / len(results), 3) for k in keys}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true", help="exit non-zero if below thresholds")
    args = ap.parse_args()
    results = run()
    agg = aggregate(results)
    print(json.dumps({"cases": results, "aggregate": agg, "thresholds": THRESHOLDS}, indent=2))
    if args.gate:
        for metric, thr in THRESHOLDS.items():
            if agg[metric] < thr:
                print(f"GATE FAIL: {metric} {agg[metric]} < {thr}", file=sys.stderr)
                sys.exit(1)
        print("GATE PASS")


if __name__ == "__main__":
    main()
