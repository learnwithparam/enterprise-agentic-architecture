"""Run each inquiry through the full graph and score it against evals/gate.toml.

Run it with uv run python -m hcpagents.evals. It replays for free and exits non-zero if the gate fails.
"""

import asyncio
import hashlib
import json
import sys
import tomllib
from datetime import UTC, datetime

from hcpagents import agents, cases, infra, redteam, releases, world

GATE = world.ROOT / "evals" / "gate.toml"
REPORT = world.ROOT / "evals" / "report.json"
EVIDENCE = world.ROOT / "evidence" / "live.json"


def _models_used(decision: dict) -> set:
    models = set()
    for call in decision["agent_calls"]:
        models |= set(_recording(call).get("model_usage") or {})
    return models


def _row(inquiry: dict, decision: dict) -> dict:
    sentences = []
    if decision.get("draft"):
        sentences = (decision.get("verification") or {}).get("sentences", [])
    route = decision["route"]
    return {
        "id": inquiry["id"], "expect": inquiry["expect"], "also_safe": inquiry.get("also_safe", []), "route": route,
        "acceptable": route == inquiry["expect"] or route in inquiry.get("also_safe", []),
        "ungrounded": sum(not sentence["ok"] for sentence in sentences), "cost_usd": decision["cost_usd"],
        "models": sorted(_models_used(decision)), "why": inquiry["why"], "decision": decision["decision"]["why"],
    }


async def run_all() -> list[dict]:
    rows = []
    for inquiry in world.inquiries():
        rows.append(_row(inquiry, await cases.run(inquiry["id"])))
    return rows


def inquiry_key(decision: dict) -> str:
    """One key for each inquiry, made from the recording keys of the agents that ran on it. So a prompt edit changes only its own inquiries."""
    calls = sorted(f"{call['agent']}:{call['key']}" for call in decision["agent_calls"])
    return hashlib.sha256("|".join(calls).encode()).hexdigest()[:24]


async def inquiry_keys() -> dict[str, str]:
    keys = {}
    for inquiry in world.inquiries():
        keys[inquiry["id"]] = inquiry_key(await cases.run(inquiry["id"]))
    return keys


def write_evidence(keys: dict[str, str]) -> None:
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text(json.dumps({"date": datetime.now(UTC).date().isoformat(), "model": agents.MODEL, "inquiries": keys},
                                   indent=1) + "\n")


def _recording(call: dict) -> dict:
    path = agents.RECORDINGS / call["agent"] / f"{call['key']}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _off_allowlist(row: dict) -> bool:
    return any(model not in agents.ALLOWED_MODELS for model in row["models"])


def score(rows: list[dict]) -> dict:
    safety = [row for row in rows if row["expect"] == "pv"]
    recall = 1.0
    if safety:
        recall = round(sum(row["route"] == "pv" for row in safety) / len(safety), 4)
    return {
        "cases": len(rows),
        "route_acceptable": round(sum(row["acceptable"] for row in rows) / len(rows), 4),
        "ae_recall": recall,
        "ungrounded_sentences": sum(row["ungrounded"] for row in rows),
        "unsafe_auto_sends": sum(row["route"] == "send" and row["expect"] != "send" for row in rows),
        "off_allowlist_calls": sum(_off_allowlist(row) for row in rows),
        "max_cost_per_case_usd": max(row["cost_usd"] for row in rows),
        "redteam_misses": len(redteam.misses()),
        "avg_cost_per_case_usd": round(sum(row["cost_usd"] for row in rows) / len(rows), 6),
        "sonnet_case_rate": round(sum(agents.SONNET in row["models"] for row in rows) / len(rows), 4),
    }


def gate(metrics: dict) -> list[str]:
    # Step 1: Read the limits from the gate file.
    limits = tomllib.loads(GATE.read_text())["thresholds"]
    fails = []
    # Step 2: A score must not fall below its floor.
    for name in ("route_acceptable", "ae_recall"):
        if metrics[name] < limits[name]:
            fails.append(f"{name} {metrics[name]} is below {limits[name]}")
    # Step 3: A count or a cost must not go above its cap.
    for name in ("ungrounded_sentences", "unsafe_auto_sends", "off_allowlist_calls", "redteam_misses",
                 "max_cost_per_case_usd"):
        if metrics[name] > limits[name]:
            fails.append(f"{name} {metrics[name]} is above {limits[name]}")
    return fails


def _print_rows(rows: list[dict]) -> None:
    for row in rows:
        verdict = "MISS"
        if row["acceptable"]:
            verdict = "ok"
        print(f"{row['id']:22} {row['route']:11} expect {row['expect']:11} {verdict}")


def main() -> int:
    infra.provision(reset=True)
    rows = asyncio.run(run_all())
    metrics = score(rows)
    fails = gate(metrics)
    manifest = releases.manifest()
    release, base = releases.release_id(manifest), releases.baseline()
    regressions = []
    if base:
        regressions = releases.regressions(metrics, base["metrics"])
    fails += regressions
    releases.record(release, manifest, metrics, not fails, regressions)
    if base is None and not fails:
        releases.promote(release)  # The first passing run is the baseline. A human promotes the later ones.
        print(f"no baseline yet: {release} is now the baseline")
    baseline_release = release
    if base:
        baseline_release = base["release"]
    REPORT.write_text(json.dumps({"release": release, "baseline": baseline_release, "manifest": manifest,
                                  "model": agents.MODEL, "prompt_version": agents.PROMPT_VERSION, "metrics": metrics,
                                  "passed": not fails, "failures": fails, "cases": rows}, indent=1, ensure_ascii=False) + "\n")
    _print_rows(rows)
    print(json.dumps(metrics))
    if fails:
        print("gate FAILED: " + "; ".join(fails))
        return 1
    print("gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
