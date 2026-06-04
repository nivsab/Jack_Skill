"""
eval_semantic.py -- measures Recall@k for rag/semantic_search.py.

Metric: Recall@k -- for each question, does at least one of the top-k
        chunks contain a required keyword?

Reports Recall@1, Recall@3, Recall@5 and flags ollama availability.
"""
import json
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

GOLDEN_PATH  = Path(__file__).parent / "data" / "semantic_golden.json"
SEMANTIC_CMD = [sys.executable, "-m", "rag.semantic_search"]


def _run_semantic(question: str) -> dict:
    try:
        result = subprocess.run(
            SEMANTIC_CMD + [question],
            capture_output=True, timeout=25,
            cwd=str(Path(__file__).parent.parent.parent),
        )
        return json.loads(result.stdout.decode("utf-8", errors="replace").strip())
    except Exception as e:
        return {"found": False, "error": str(e)}


def _chunk_contains(chunk: str, keywords: list) -> bool:
    chunk_lower = chunk.lower()
    return any(kw.lower() in chunk_lower for kw in keywords)


def run(k_values: list = None, verbose: bool = True) -> dict:
    if k_values is None:
        k_values = [1, 3, 5]

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    total  = len(golden)

    recall_counts = {k: 0 for k in k_values}
    ollama_unavailable_count = 0
    errors = []

    for case in golden:
        response = _run_semantic(case["question"])

        if not response.get("found"):
            if response.get("ollama_unavailable"):
                ollama_unavailable_count += 1
            errors.append({
                "id":       case["id"],
                "question": case["question"][:60],
                "reason":   response.get("reason", response.get("error", "unknown")),
            })
            if verbose:
                print(f"  MISS [{case['id']}] {case['question'][:60]}")
                print(f"       reason: {response.get('reason', response.get('error', 'unknown'))}")
            continue

        results = response.get("results", [])
        chunks  = [r.get("chunk", "") for r in results]
        keywords = case["must_contain_any"]

        for k in k_values:
            top_k = chunks[:k]
            if any(_chunk_contains(c, keywords) for c in top_k):
                recall_counts[k] += 1

        hit_k5 = any(_chunk_contains(c, keywords) for c in chunks[:5])
        if verbose:
            status = "OK  " if hit_k5 else "WARN"
            top_chunk_preview = chunks[0][:80].replace("\n", " ") if chunks else "-"
            print(f"  [{status}] [{case['id']}] {case['question'][:55]}")
            print(f"       top chunk: {top_chunk_preview}...")

    recall_at = {f"recall@{k}": round(recall_counts[k] / total * 100, 1) for k in k_values}

    results_summary = {
        "total_cases":              total,
        "ollama_unavailable_count": ollama_unavailable_count,
        **recall_at,
        "errors":                   errors,
    }

    if verbose:
        print(f"\n{'-'*50}")
        print(f"  Total cases:          {total}")
        if ollama_unavailable_count:
            print(f"  Ollama unavailable:   {ollama_unavailable_count} cases skipped")
        for k in k_values:
            count = recall_counts[k]
            print(f"  Recall@{k}:             {recall_at[f'recall@{k}']:.1f}%  ({count}/{total})")
        if errors:
            print(f"\n  Failed cases ({len(errors)}):")
            for e in errors:
                print(f"    - [{e['id']}] {e['question']} -> {e['reason']}")

    return results_summary


if __name__ == "__main__":
    print("\nSemantic Search Eval\n" + "-" * 50)
    run(verbose=True)
