"""Releases: what shipped, how it scored, and whether it improved on the one before (ADR 0025).

A release is the hash of everything that decides behaviour: each agent's prompt and schema, the router,
the policy kernel, the model allowlist and the embedding model. Change any of them and the release id
changes, so every eval run and every spend row names the exact thing it measured. A run is compared with
the baseline, the run a human last promoted, and a quality or cost metric that slips past its tolerance in
evals/gate.toml blocks the release.
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


def release_id(m: dict | None = None) -> str:
    return "r-" + _hash(m or manifest())[:8]


@cache
def current() -> str:
    """The release id of this process, worked out once."""
    return release_id()


def regressions(metrics: dict, base: dict) -> list[str]:
    """Every quality or cost metric that is worse than the baseline by more than its tolerance."""
    tol = tomllib.loads(GATE.read_text())["regression"]
    out = []
    for k in HIGHER_IS_BETTER:
        if base[k] - metrics[k] > tol[k]:
            out.append(f"{k} fell from {base[k]} to {metrics[k]}")
    for k in RELATIVE_RISE:
        if base[k] and (metrics[k] - base[k]) / base[k] > tol[k]:
            out.append(f"{k} rose from {base[k]} to {metrics[k]}, more than {tol[k]:.0%}")
    for k in ABSOLUTE_RISE:
        if metrics[k] - base[k] > tol[k]:
            out.append(f"{k} rose from {base[k]} to {metrics[k]}")
    return out


def record(release: str, m: dict, metrics: dict, passed: bool, regs: list[str]) -> int:
    with db.session() as conn:
        return conn.execute(
            "INSERT INTO eval_runs (tenant_id, release, manifest, metrics, passed, regressions) "
            "VALUES (current_setting('app.tenant_id'), %s, %s, %s, %s, %s) RETURNING id",
            (release, Jsonb(m), Jsonb(metrics), passed, Jsonb(regs))).fetchone()["id"]


def latest(release: str) -> dict | None:
    with db.session() as conn:
        return conn.execute("SELECT * FROM eval_runs WHERE release = %s ORDER BY id DESC LIMIT 1", (release,)).fetchone()


def baseline() -> dict | None:
    with db.session() as conn:
        return conn.execute("SELECT * FROM eval_runs WHERE baseline ORDER BY id DESC LIMIT 1").fetchone()


def promote(release: str) -> None:
    """Make a release the baseline. Only a release whose latest run passed with no regression can be."""
    run = latest(release)
    if run is None:
        raise LookupError(f"No eval run for {release}")
    if not run["passed"] or run["regressions"]:
        raise ValueError(f"{release} did not pass its gate and cannot become the baseline")
    with db.session() as conn:
        conn.execute("UPDATE eval_runs SET baseline = false WHERE baseline")
        conn.execute("UPDATE eval_runs SET baseline = true WHERE id = %s", (run["id"],))


def diff(a: str, b: str) -> dict:
    """What moved between two releases: each metric's change, and which parts of the manifest differ."""
    ra, rb = latest(a), latest(b)
    if ra is None or rb is None:
        raise LookupError(f"Both releases need an eval run: {a}, {b}")
    metrics = {k: {"a": ra["metrics"][k], "b": rb["metrics"][k], "delta": round(rb["metrics"][k] - ra["metrics"][k], 6)}
               for k in rb["metrics"] if k in ra["metrics"]}
    flat = lambda m: {**{k: v for k, v in m.items() if k != "prompts"}, **{f"prompts.{n}": h for n, h in m["prompts"].items()}}  # noqa: E731
    fa, fb = flat(ra["manifest"]), flat(rb["manifest"])
    return {"metrics": metrics, "changed": sorted(k for k in fa.keys() | fb.keys() if fa.get(k) != fb.get(k))}


def trend(tenant: str) -> list[dict]:
    """Every release newest first: its latest eval metrics and what its live calls cost."""
    with world.as_tenant(tenant), db.session() as conn:
        runs = conn.execute("SELECT DISTINCT ON (release) release, metrics, passed, regressions, baseline, at "
                            "FROM eval_runs ORDER BY release, id DESC").fetchall()
    cost = {r["release"]: r for r in gateway.spend_by(tenant, "release")}
    out = [r | {"live_calls": int(cost[r["release"]]["calls"]) if r["release"] in cost else 0,
                "live_cost_usd": float(cost[r["release"]]["cost_usd"]) if r["release"] in cost else 0.0} for r in runs]
    return sorted(out, key=lambda r: r["at"], reverse=True)


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def online(tenant: str) -> list[dict]:
    """What live cases did under each release: route mix, how often reviewers overrode the draft, cost and latency."""
    with world.as_tenant(tenant):
        docs = store.scan("mi-cases")
    by_release: dict[str, list[dict]] = {}
    for d in docs:
        if "latency_ms" in d:
            by_release.setdefault(d.get("release", "unknown"), []).append(d)
    out = []
    for release, ds in sorted(by_release.items()):
        rejected = sum(d["status"] == "rejected" for d in ds)
        approved = sum(any(h["event"].startswith("Approved and sent") for h in d["history"]) for d in ds)
        routes: dict[str, int] = {}
        for d in ds:
            routes[d["route"]] = routes.get(d["route"], 0) + 1
        out.append({"release": release, "cases": len(ds), "routes": routes,
                    "override_rate": round(rejected / (rejected + approved), 4) if rejected + approved else None,
                    "avg_cost_usd": round(sum(d["cost_usd"] for d in ds) / len(ds), 6),
                    "p50_ms": _percentile([d["latency_ms"] for d in ds], 0.5),
                    "p95_ms": _percentile([d["latency_ms"] for d in ds], 0.95)})
    return out
