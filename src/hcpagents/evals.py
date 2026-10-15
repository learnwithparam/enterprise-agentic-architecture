"""Run every inquiry through the full graph and score it against evals/gate.toml.

uv run python -m hcpagents.evals     replay (free); exits non-zero when the gate fails
"""

import asyncio
import json
import sys
import tomllib

from hcpagents import agents, cases, infra, world

GATE = world.ROOT / "evals" / "gate.toml"
REPORT = world.ROOT / "evals" / "report.json"


async def run_all() -> list[dict]:
    rows = []
    for inq in world.inquiries():
        d = await cases.run(inq["id"])
        drafts = (d.get("verification") or {}).get("sentences", []) if d.get("draft") else []
        models = {m for a in d["agent_calls"] for m in (_rec(a).get("model_usage") or {})}
        rows.append({
            "id": inq["id"], "expect": inq["expect"], "also_safe": inq.get("also_safe", []), "route": d["route"],
            "acceptable": d["route"] == inq["expect"] or d["route"] in inq.get("also_safe", []),
            "ungrounded": sum(not s["ok"] for s in drafts), "cost_usd": d["cost_usd"], "models": sorted(models),
            "why": inq["why"], "decision": d["decision"]["why"],
        })
    return rows


def _rec(call: dict) -> dict:
    p = agents.RECORDINGS / call["agent"] / f"{call['key']}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def score(rows: list[dict]) -> dict:
    pv = [r for r in rows if r["expect"] == "pv"]
    return {
        "cases": len(rows),
        "route_acceptable": round(sum(r["acceptable"] for r in rows) / len(rows), 4),
        "ae_recall": round(sum(r["route"] == "pv" for r in pv) / len(pv), 4) if pv else 1.0,
        "ungrounded_sentences": sum(r["ungrounded"] for r in rows),
        "unsafe_auto_sends": sum(r["route"] == "send" and r["expect"] != "send" for r in rows),
        "non_haiku_calls": sum(any(m != agents.MODEL for m in r["models"]) for r in rows),
        "max_cost_per_case_usd": max(r["cost_usd"] for r in rows),
    }


def gate(metrics: dict) -> list[str]:
    t = tomllib.loads(GATE.read_text())["thresholds"]
    fails = []
    for k in ("route_acceptable", "ae_recall"):
        if metrics[k] < t[k]:
            fails.append(f"{k} {metrics[k]} is below {t[k]}")
    for k in ("ungrounded_sentences", "unsafe_auto_sends", "non_haiku_calls", "max_cost_per_case_usd"):
        if metrics[k] > t[k]:
            fails.append(f"{k} {metrics[k]} is above {t[k]}")
    return fails


def main() -> int:
    infra.provision(reset=True)
    rows = asyncio.run(run_all())
    metrics = score(rows)
    fails = gate(metrics)
    REPORT.write_text(json.dumps({"model": agents.MODEL, "prompt_version": agents.PROMPT_VERSION, "metrics": metrics,
                                  "passed": not fails, "failures": fails, "cases": rows}, indent=1, ensure_ascii=False) + "\n")
    for r in rows:
        print(f"{r['id']:22} {r['route']:11} expect {r['expect']:11} {'ok' if r['acceptable'] else 'MISS'}")
    print(json.dumps(metrics))
    print("gate passed" if not fails else "gate FAILED: " + "; ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
