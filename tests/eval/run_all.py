"""
run_all.py — runs all evals and writes results.md

Usage:
  python tests/eval/run_all.py              # full run
  python tests/eval/run_all.py --retriever  # retriever only
  python tests/eval/run_all.py --semantic   # semantic only
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

RESULTS_PATH = Path(__file__).parent / "results.md"


def _md_retriever(r: dict) -> str:
    lines = [
        "## Retriever Eval\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total cases | {r['total_cases']} ({r['verified_cases']} verified) |",
        f"| Hit rate | **{r['hit_rate']}%** ({r['hits']}/{r['total_cases']}) |",
        f"| Value accuracy | **{r['value_accuracy']}%** ({r['value_matches']}/{r['hits']} hits) |",
        f"| Overall accuracy | **{r['overall_accuracy']}%** ({r['value_matches']}/{r['total_cases']}) |",
        f"| Confidence=manual | {r['confidence_rate']}% |",
    ]
    if r.get("misses"):
        lines += ["\n**Misses:**"]
        for m in r["misses"]:
            lines.append(f"- `{m['id']}` {m['make']} {m['model']} {m['engine']} / {m['spec']}")
    if r.get("wrong_values"):
        lines += ["\n**Wrong values:**"]
        for w in r["wrong_values"]:
            flag = " ⚠️ needs_verification" if w["needs_verification"] else ""
            lines.append(f"- `{w['id']}` `{w['spec']}`: got `{w['actual']}`, expected `{w['expected']}`{flag}")
    return "\n".join(lines)


def _md_semantic(r: dict) -> str:
    lines = [
        "## Semantic Search Eval\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total cases | {r['total_cases']} |",
    ]
    if r.get("ollama_unavailable_count"):
        lines.append(f"| Ollama unavailable | ⚠️ {r['ollama_unavailable_count']} cases skipped |")
    for key, val in r.items():
        if key.startswith("recall@"):
            lines.append(f"| {key.replace('recall@', 'Recall@')} | **{val}%** |")
    if r.get("errors"):
        lines += ["\n**Failed cases:**"]
        for e in r["errors"]:
            lines.append(f"- `{e['id']}` {e['question']} → {e['reason']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retriever", action="store_true")
    parser.add_argument("--semantic",  action="store_true")
    args = parser.parse_args()
    run_all = not args.retriever and not args.semantic

    sections = [
        f"# Jack RAG Eval Results\n",
        f"**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"**Vehicles:** Toyota Yaris Hybrid 2019–2020, Kia Rio 2017–2024 (1.0T + 1.4)\n",
        f"**Manuals:** 2 PDFs\n",
    ]

    if run_all or args.retriever:
        from tests.eval import eval_retriever
        print("\n" + "═" * 55)
        print("  RETRIEVER EVAL")
        print("═" * 55)
        ret_results = eval_retriever.run(verbose=True)
        sections.append("\n---\n")
        sections.append(_md_retriever(ret_results))

    if run_all or args.semantic:
        from tests.eval import eval_semantic
        print("\n" + "═" * 55)
        print("  SEMANTIC SEARCH EVAL")
        print("═" * 55)
        sem_results = eval_semantic.run(verbose=True)
        sections.append("\n---\n")
        sections.append(_md_semantic(sem_results))

    md = "\n".join(sections)
    RESULTS_PATH.write_text(md, encoding="utf-8")
    print(f"\n✅ Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
