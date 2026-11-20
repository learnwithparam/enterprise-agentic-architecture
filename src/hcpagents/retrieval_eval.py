"""Score search on world/retrieval.toml and check the limits in evals/gate.toml.

Run it with python -m hcpagents.retrieval_eval.

Four rankers are tried on the same questions. They are the old topic filter, text alone, vectors alone, and the hybrid.
The hybrid must find the answer as often as any single signal. Nothing outside the facet gate may ever show up.
"""

import sys
import tomllib

from hcpagents import infra, retrieval, store, world

TOP = 3
CASES = world.ROOT / "world" / "retrieval.toml"


def _topic_filter(case: dict) -> list[str]:
    """What the agents did before. The caller names the topic and gets an exact match. It is given the right topic."""
    gold = None
    if case["answer"]:
        gold = store.get("mi-content", case["answer"])
    topic = "interactions"
    if gold:
        topic = gold["topic"]
    return [block["id"] for block in store.content().values()
            if block["product"] == case["product"] and block["country"] == case["country"]
            and block["topic"] == topic and world.is_current(block)][:TOP]


def rank(case: dict, mode: str) -> list[str]:
    if mode == "topic":
        return _topic_filter(case)
    found = retrieval.search(case["query"], case["product"], case["country"], limit=TOP, mode=mode,
                             audience=case.get("audience", "doctor"))
    return [block["block_id"] for block in found]


def run() -> dict:
    cases = tomllib.loads(CASES.read_text())["case"]
    out = {}
    for mode in ("topic", "fts", "vector", "hybrid"):
        hit = leaks = answerable = 0
        for case in cases:
            ids = rank(case, mode)
            leaks += sum(block_id in case.get("forbidden", []) for block_id in ids)
            if case["answer"]:
                answerable += 1
                hit += case["answer"] in ids
        out[mode] = {"recall_at_k": round(hit / answerable, 4), "outside_gate": leaks}
    return out


def _failures(scores: dict, limits: dict) -> list[str]:
    hybrid = scores["hybrid"]
    fails = []
    if hybrid["recall_at_k"] < limits["hybrid_recall_at_k"]:
        fails.append(f"hybrid recall {hybrid['recall_at_k']} is below {limits['hybrid_recall_at_k']}")
    others = [score["recall_at_k"] for mode, score in scores.items() if mode != "hybrid"]
    if hybrid["recall_at_k"] < max(others):
        fails.append("hybrid finds the answer less often than a single signal")
    if any(score["outside_gate"] > limits["outside_gate"] for score in scores.values()):
        fails.append("a block outside the facet gate was returned")
    return fails


def main() -> int:
    infra.provision(reset=True)
    limits = tomllib.loads((world.ROOT / "evals" / "gate.toml").read_text())["retrieval"]
    scores = run()
    for mode, score in scores.items():
        print(f"{mode:7} recall@{TOP} {score['recall_at_k']:.2f}  outside the gate {score['outside_gate']}")
    fails = _failures(scores, limits)
    if fails:
        print("retrieval gate FAILED: " + "; ".join(fails))
        return 1
    print("retrieval gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
