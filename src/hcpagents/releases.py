"""Releases: what shipped, how it scored, and if it beat the last one (ADR 0025).

A release is a hash of all that sets how the system acts. That is each agent prompt, the router,
the policy kernel, the model list and the embedder. Change one and the id changes.
Each run is checked against the baseline. A metric that slips past its limit in evals/gate.toml blocks the release.
"""

import hashlib
import json
import tomllib
from functools import cache

from psycopg.types.json import Jsonb

from hcpagents import agents, db, embeddings, gateway, graph, router, store, world

GATE = world.ROOT / "evals" / "gate.toml"
HIGHER_IS_BETTER = ("route_acceptable", "ae_recall")  # a drop larger than the tolerance is a regression
RELATIVE_RISE = ("avg_cost_per_case_usd", "max_cost_per_case_usd")  # a rise larger than this share of the baseline is one
ABSOLUTE_RISE = ("sonnet_case_rate",)  # a rise larger than this many points is one


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:12]


def manifest() -> dict:
    return {
        "prompt_version": agents.PROMPT_VERSION,
        "prompts": {name: _hash([spec["system"], spec["schema"]]) for name, spec in agents.AGENTS.items()},
        "router": _hash([router.HAIKU, router.SONNET, sorted(router.HAIKU_TASKS), sorted(router.SONNET_TASKS),
                         router.SONNET_CALL_ESTIMATE_USD]),
        "kernel": _hash(graph.ROUTING),
        "models": sorted(agents.ALLOWED_MODELS),
        "embeddings": embeddings.embedder().model_id,
    }


def release_id(manifest_data: dict | None = None) -> str:
    return "r-" + _hash(manifest_data or manifest())[:8]


@cache
def current() -> str:
    """The release id of this process, worked out once."""
    return release_id()


def regressions(metrics: dict, base: dict) -> list[str]:
    """Each metric that is worse than the baseline by more than its limit."""
    tolerance = tomllib.loads(GATE.read_text())["regression"]
    found = []
    for name in HIGHER_IS_BETTER:
        if base[name] - metrics[name] > tolerance[name]:
            found.append(f"{name} fell from {base[name]} to {metrics[name]}")
    for name in RELATIVE_RISE:
        if base[name] and (metrics[name] - base[name]) / base[name] > tolerance[name]:
            found.append(f"{name} rose from {base[name]} to {metrics[name]}, more than {tolerance[name]:.0%}")
    for name in ABSOLUTE_RISE:
        if metrics[name] - base[name] > tolerance[name]:
            found.append(f"{name} rose from {base[name]} to {metrics[name]}")
    return found


def record(release: str, manifest_data: dict, metrics: dict, passed: bool, regs: list[str]) -> int:
    with db.session() as conn:
        return conn.execute(
            "INSERT INTO eval_runs (tenant_id, release, manifest, metrics, passed, regressions) "
            "VALUES (current_setting('app.tenant_id'), %s, %s, %s, %s, %s) RETURNING id",
            (release, Jsonb(manifest_data), Jsonb(metrics), passed, Jsonb(regs))).fetchone()["id"]


def latest(release: str) -> dict | None:
    with db.session() as conn:
        return conn.execute("SELECT * FROM eval_runs WHERE release = %s ORDER BY id DESC LIMIT 1", (release,)).fetchone()


def baseline() -> dict | None:
    with db.session() as conn:
        return conn.execute("SELECT * FROM eval_runs WHERE baseline ORDER BY id DESC LIMIT 1").fetchone()


def promote(release: str) -> None:
    """Make a release the baseline. Only a release whose latest run passed cleanly can be."""
    run = latest(release)
    if run is None:
        raise LookupError(f"No eval run for {release}")
    if not run["passed"] or run["regressions"]:
        raise ValueError(f"{release} did not pass its gate and cannot become the baseline")
    with db.session() as conn:
        conn.execute("UPDATE eval_runs SET baseline = false WHERE baseline")
        conn.execute("UPDATE eval_runs SET baseline = true WHERE id = %s", (run["id"],))


def _flatten(manifest_data: dict) -> dict:
    flat = {name: value for name, value in manifest_data.items() if name != "prompts"}
    for agent, digest in manifest_data["prompts"].items():
        flat[f"prompts.{agent}"] = digest
    return flat


def diff(first: str, second: str) -> dict:
    """What changed between two releases: the scores and the parts."""
    first_run, second_run = latest(first), latest(second)
    if first_run is None or second_run is None:
        raise LookupError(f"Both releases need an eval run: {first}, {second}")
    metrics = {name: {"a": first_run["metrics"][name], "b": second_run["metrics"][name],
                      "delta": round(second_run["metrics"][name] - first_run["metrics"][name], 6)}
               for name in second_run["metrics"] if name in first_run["metrics"]}
    first_flat, second_flat = _flatten(first_run["manifest"]), _flatten(second_run["manifest"])
    changed = sorted(name for name in first_flat.keys() | second_flat.keys()
                     if first_flat.get(name) != second_flat.get(name))
    return {"metrics": metrics, "changed": changed}


def _live_cost(run: dict, cost: dict) -> dict:
    spent = cost.get(run["release"])
    if spent is None:
        return run | {"live_calls": 0, "live_cost_usd": 0.0}
    return run | {"live_calls": int(spent["calls"]), "live_cost_usd": float(spent["cost_usd"])}


def _newest(run: dict):
    return run["at"]


def trend(tenant: str) -> list[dict]:
    """Each release, newest first, with its scores and live cost."""
    with world.as_tenant(tenant), db.session() as conn:
        runs = conn.execute("SELECT DISTINCT ON (release) release, metrics, passed, regressions, baseline, at "
                            "FROM eval_runs ORDER BY release, id DESC").fetchall()
    cost = {row["release"]: row for row in gateway.spend_by(tenant, "release")}
    return sorted([_live_cost(run, cost) for run in runs], key=_newest, reverse=True)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def _summarise(release: str, docs: list[dict]) -> dict:
    rejected = sum(doc["status"] == "rejected" for doc in docs)
    approved = 0
    for doc in docs:
        if any(step["event"].startswith("Approved and sent") for step in doc["history"]):
            approved += 1
    routes: dict[str, int] = {}
    for doc in docs:
        routes[doc["route"]] = routes.get(doc["route"], 0) + 1
    override_rate = None
    if rejected + approved:
        override_rate = round(rejected / (rejected + approved), 4)
    latencies = [doc["latency_ms"] for doc in docs]
    return {"release": release, "cases": len(docs), "routes": routes,
            "override_rate": override_rate,
            "avg_cost_usd": round(sum(doc["cost_usd"] for doc in docs) / len(docs), 6),
            "p50_ms": _percentile(latencies, 0.5),
            "p95_ms": _percentile(latencies, 0.95)}


def online(tenant: str) -> list[dict]:
    """What live cases did under each release: the route, the cost and the time."""
    with world.as_tenant(tenant):
        docs = store.scan("mi-cases")
    by_release: dict[str, list[dict]] = {}
    for doc in docs:
        if "latency_ms" in doc:
            by_release.setdefault(doc.get("release", "unknown"), []).append(doc)
    return [_summarise(release, release_docs) for release, release_docs in sorted(by_release.items())]
