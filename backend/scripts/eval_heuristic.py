"""
eval_heuristic.py — backend/scripts/eval_heuristic.py

Evaluates the heuristic_score function against the labeled complexity_eval.jsonl
dataset. Acts as a deployment gate: changes to _heuristic_score() must pass
these thresholds before shipping.

Deployment thresholds (from NEXUS Definitive Architecture):
  tier_accuracy  > 85%   (tier misrouting is recoverable, unlike safety bypass)
  graph_accuracy > 90%   (missed graph = degraded quality; false graph = wasted LLM call)

Usage:
  python backend/scripts/eval_heuristic.py
  python backend/scripts/eval_heuristic.py --verbose
  python backend/scripts/eval_heuristic.py --data backend/data/complexity_eval.jsonl
"""

import sys
import json
import argparse
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.brain.reasoning.analysis_pass import run_heuristic_pass

# ── Deployment gate thresholds ────────────────────────────────────────────────
THRESHOLDS = {
    "tier_accuracy":  0.85,
    "graph_accuracy": 0.90,
}

DEFAULT_DATA = Path(__file__).parent.parent / "data" / "complexity_eval.jsonl"


def evaluate(data_path: Path, verbose: bool = False) -> dict:
    """Run evaluation and return results dict."""
    cases = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    if not cases:
        print("[ERROR] No test cases found.")
        sys.exit(1)

    tier_correct = 0
    graph_correct = 0
    tier_failures = []
    graph_failures = []

    for case in cases:
        text = case["text"]
        expected_tier = case["expected_tier"]
        expected_graph = case["expected_graph"]

        result = run_heuristic_pass(text)

        t_ok = result.model_tier == expected_tier
        g_ok = result.needs_task_graph == expected_graph

        if t_ok:
            tier_correct += 1
        else:
            tier_failures.append({
                "text": text,
                "expected": expected_tier,
                "got": result.model_tier,
                "score": result.complexity_score,
            })

        if g_ok:
            graph_correct += 1
        else:
            graph_failures.append({
                "text": text,
                "expected_graph": expected_graph,
                "got_graph": result.needs_task_graph,
                "score": result.complexity_score,
            })

        if verbose:
            t_sym = "PASS" if t_ok else "FAIL"
            g_sym = "PASS" if g_ok else "FAIL"
            print(
                f"  [t:{t_sym}] [g:{g_sym}] score={result.complexity_score:2d} "
                f"tier={result.model_tier:<10} graph={str(result.needs_task_graph):<5} "
                f"| {text[:55]}"
            )

    total = len(cases)
    tier_acc = tier_correct / total
    graph_acc = graph_correct / total

    return {
        "total": total,
        "tier_correct": tier_correct,
        "tier_accuracy": tier_acc,
        "tier_failures": tier_failures,
        "graph_correct": graph_correct,
        "graph_accuracy": graph_acc,
        "graph_failures": graph_failures,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate heuristic complexity scoring.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.data.exists():
        print(f"[ERROR] Data file not found: {args.data}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Heuristic Eval - {args.data.name}")
    print(f"{'='*60}")

    if args.verbose:
        print()

    results = evaluate(args.data, verbose=args.verbose)

    print()
    print(f"  Total cases     : {results['total']}")
    print(f"  Tier accuracy   : {results['tier_accuracy']*100:.1f}%  "
          f"(threshold: {THRESHOLDS['tier_accuracy']*100:.0f}%)")
    print(f"  Graph accuracy  : {results['graph_accuracy']*100:.1f}%  "
          f"(threshold: {THRESHOLDS['graph_accuracy']*100:.0f}%)")
    print()

    tier_pass  = results["tier_accuracy"]  >= THRESHOLDS["tier_accuracy"]
    graph_pass = results["graph_accuracy"] >= THRESHOLDS["graph_accuracy"]

    if results["tier_failures"] and not tier_pass:
        print("  Tier failures:")
        for f in results["tier_failures"]:
            print(f"    score={f['score']}  expected={f['expected']:<10} got={f['got']:<10} | {f['text'][:55]}")
        print()

    if results["graph_failures"] and not graph_pass:
        print("  Graph failures:")
        for f in results["graph_failures"]:
            print(f"    score={f['score']}  expected={str(f['expected_graph']):<5} got={str(f['got_graph']):<5} | {f['text'][:55]}")
        print()

    all_pass = tier_pass and graph_pass
    status = "[PASS] Deployment gate cleared." if all_pass else "[FAIL] Do NOT ship heuristic_score changes."
    print(f"  {status}")
    print(f"{'='*60}\n")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
