"""The guardian keeps the platform inside its limits, and only ever tightens them (ADR 0026).

It reads what reviewers did with AI drafts. When a country's reviewers reject more than the allowed share,
it switches that country's automatic replies off. It cannot switch anything on: a human does that with
cases.set_autonomy, and the count starts again from that moment.
"""

from datetime import datetime

from hcpagents import cases, ledger, store, world

DECISIONS = ("approved", "rejected")
CHANGES = ("autonomy_changed", "guardian_lowered")


def _at(entry: dict) -> datetime:
    return datetime.fromisoformat(entry["at"])


def override_rates(since: datetime | None = None) -> dict[str, dict]:
    """Per country: reviewed AI drafts, how many were rejected, and the share. Counted from the ledger, since
    the last time that country's autonomy changed (a human switching it back on starts a fresh count)."""
    rows = [r["entry"] for r in ledger.entries()]
    out = {}
    for country in world.autonomy_seed()["auto_send"]:
        changed = [_at(e) for e in rows if e["type"] in CHANGES and e.get("country") == country]
        start = max([*changed, *([since] if since else [])], default=None)
        counts = {k: 0 for k in DECISIONS}
        for e in rows:
            if e["type"] not in DECISIONS or (start and _at(e) <= start):
                continue
            doc = store.get("mi-cases", e["case"])
            if doc and doc["country"] == country and doc.get("draft"):
                counts[e["type"]] += 1
        n = sum(counts.values())
        out[country] = {**counts, "reviewed": n, "override_rate": round(counts["rejected"] / n, 4) if n else 0.0}
    return out


def patrol(since: datetime | None = None) -> list[dict]:
    """Lower every country whose reviewers reject too much. Returns what it lowered; running it again lowers nothing."""
    limits = world.autonomy_seed()["guardian"]
    lowered = []
    for country, r in override_rates(since).items():
        if r["reviewed"] < limits["min_decisions"] or r["override_rate"] <= limits["max_override_rate"]:
            continue
        s = cases.autonomy_setting(country)
        if not s["enabled"]:
            continue
        cases.save_autonomy(country, s | {"enabled": False})
        ledger.append({"type": "guardian_lowered", "country": country, "override_rate": r["override_rate"],
                       "reviewed": r["reviewed"], "limit": limits["max_override_rate"]})
        lowered.append({"country": country, **r})
    return lowered
