"""Score retrieval on world/retrieval.toml and apply the [retrieval] thresholds in evals/gate.toml.

uv run python -m hcpagents.retrieval_eval

Four rankers are compared on the same questions: the exact topic filter the agents used before, full-text
alone, vectors alone, and the hybrid. The hybrid must find the answer at least as often as any single signal,
and nothing outside the facet gate may ever appear.
"""

import sys
import tomllib

from hcpagents import infra, retrieval, store, world

K = 3
CASES = world.ROOT / "world" / "retrieval.toml"


def _topic_filter(case: dict) -> list[str]:
    """What the agents did before: the caller names the topic and gets an exact match. It is given the right topic."""
    gold = store.get("mi-content", case["answer"]) if case["answer"] else None
    topic = gold["topic"] if gold else "interactions"
    return [b["id"] for b in store.content().values() if b["product"] == case["product"] and b["country"] == case["country"]
            and b["topic"] == topic and world.is_current(b)][:K]


def rank(case: dict, mode: str) -> list[str]:
    if mode == "topic":
        return _topic_filter(case)
    return [b["block_id"] for b in retrieval.search(case["query"], case["product"], case["country"], k=K, mode=mode)]


def run() -> dict:
    cases = tomllib.loads(CASES.read_text())["case"]
    out = {}
    for mode in ("topic", "fts", "vector", "hybrid"):
        hit = leaks = answerable = 0
        for c in cases:
            ids = rank(c, mode)
            leaks += sum(i in c.get("forbidden", []) for i in ids)
            if c["answer"]:
                answerable += 1
                hit += c["answer"] in ids
        out[mode] = {"recall_at_k": round(hit / answerable, 4), "outside_gate": leaks}
    return out


def main() -> int:
    infra.provision(reset=True)
    t = tomllib.loads((world.ROOT / "evals" / "gate.toml").read_text())["retrieval"]
    scores = run()
    for mode, s in scores.items():
        print(f"{mode:7} recall@{K} {s['recall_at_k']:.2f}  outside the gate {s['outside_gate']}")
    h = scores["hybrid"]
    fails = []
    if h["recall_at_k"] < t["hybrid_recall_at_k"]:
        fails.append(f"hybrid recall {h['recall_at_k']} is below {t['hybrid_recall_at_k']}")
    if h["recall_at_k"] < max(s["recall_at_k"] for m, s in scores.items() if m != "hybrid"):
        fails.append("hybrid finds the answer less often than a single signal")
    if any(s["outside_gate"] > t["outside_gate"] for s in scores.values()):
        fails.append("a block outside the facet gate was returned")
    print("retrieval gate passed" if not fails else "retrieval gate FAILED: " + "; ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
