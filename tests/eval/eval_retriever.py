"""
eval_retriever.py — measures accuracy of rag/retriever.py against golden specs.

Metrics:
  hit_rate          — % of queries that returned found:true
  value_accuracy    — % of hits where the value matched (exact or within tolerance)
  overall_accuracy  — hit AND correct / total
  confidence_rate   — % of hits that returned confidence=manual
"""
import json
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rag import cache
from rag.retriever import _detect_relevant_specs


GOLDEN_PATH = Path(__file__).parent / "data" / "retriever_golden.json"


def _extract_number(value: str) -> float | None:
    nums = re.findall(r"[\d.]+", value)
    return float(nums[0]) if nums else None


def _values_match(actual: str, expected: str, tolerance) -> bool:
    if tolerance is None:
        return actual.strip().lower() == expected.strip().lower()
    a = _extract_number(actual)
    e = _extract_number(expected)
    if a is None or e is None:
        return actual.strip().lower() == expected.strip().lower()
    return abs(a - e) <= tolerance


def run(verbose: bool = True) -> dict:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    total = len(golden)
    verified_total = sum(1 for c in golden if not c.get("needs_verification"))

    hits = 0
    value_matches = 0
    correct_confidence = 0
    misses = []
    wrong_values = []

    for case in golden:
        vehicle = {
            "manufacturer": case["make"],
            "model":        case["model"],
            "year":         case["year"],
            "engine":       case.get("engine", ""),
        }
        spec_type = case["expected_spec_type"]
        result = cache.get_spec(vehicle, spec_type)
        time.sleep(0.05)

        found = result is not None
        if found:
            hits += 1
            actual_value = result.get("value", "")
            if _values_match(actual_value, case["expected_value"], case.get("tolerance")):
                value_matches += 1
            else:
                wrong_values.append({
                    "id": case["id"],
                    "spec": spec_type,
                    "expected": case["expected_value"],
                    "actual": actual_value,
                    "needs_verification": case.get("needs_verification", False),
                })
            if result.get("confidence") == "manual":
                correct_confidence += 1
        else:
            misses.append({"id": case["id"], "spec": spec_type,
                           "make": case["make"], "model": case["model"],
                           "engine": case.get("engine", "")})

        if verbose:
            status = "✅" if (found and _values_match(
                result.get("value", "") if result else "",
                case["expected_value"], case.get("tolerance"))) else ("⚠️ " if found else "❌")
            value_str = result.get("value", "—") if result else "—"
            flag = " [needs_verification]" if case.get("needs_verification") else ""
            print(f"  {status} [{case['id']}] {case['make']} {case['model']} "
                  f"{case.get('engine','')} | {spec_type}: "
                  f"{value_str} (expected: {case['expected_value']}){flag}")

    hit_rate       = hits / total * 100
    value_accuracy = value_matches / hits * 100 if hits else 0
    overall        = value_matches / total * 100
    conf_rate      = correct_confidence / hits * 100 if hits else 0

    results = {
        "total_cases":       total,
        "verified_cases":    verified_total,
        "hits":              hits,
        "value_matches":     value_matches,
        "hit_rate":          round(hit_rate, 1),
        "value_accuracy":    round(value_accuracy, 1),
        "overall_accuracy":  round(overall, 1),
        "confidence_rate":   round(conf_rate, 1),
        "misses":            misses,
        "wrong_values":      wrong_values,
    }

    if verbose:
        print(f"\n{'─'*50}")
        print(f"  Total cases:       {total} ({verified_total} verified, {total - verified_total} needs_verification)")
        print(f"  Hit rate:          {hit_rate:.1f}%  ({hits}/{total})")
        print(f"  Value accuracy:    {value_accuracy:.1f}%  ({value_matches}/{hits} hits correct)")
        print(f"  Overall accuracy:  {overall:.1f}%  ({value_matches}/{total} correct)")
        print(f"  Confidence=manual: {conf_rate:.1f}%  ({correct_confidence}/{hits} hits)")
        if misses:
            print(f"\n  Misses ({len(misses)}):")
            for m in misses:
                print(f"    - [{m['id']}] {m['make']} {m['model']} {m['engine']} / {m['spec']}")
        if wrong_values:
            print(f"\n  Wrong values ({len(wrong_values)}):")
            for w in wrong_values:
                flag = " [needs_verification]" if w["needs_verification"] else ""
                print(f"    - [{w['id']}] {w['spec']}: got '{w['actual']}', expected '{w['expected']}'{flag}")

    return results


if __name__ == "__main__":
    print("\nRetriever Eval\n" + "-" * 50)
    run(verbose=True)
