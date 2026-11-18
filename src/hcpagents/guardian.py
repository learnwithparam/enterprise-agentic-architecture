"""The guardian keeps the platform inside its limits (ADR 0026). It only ever makes them tighter.

It reads what reviewers did with AI drafts. When a country's reviewers reject more than the allowed share,
it turns that country's auto replies off. It cannot turn anything on.
A human does that with cases.set_autonomy, and the count starts again then.
"""

from datetime import datetime

from hcpagents import cases, ledger, store, world

DECISIONS = ("approved", "rejected")
CHANGES = ("autonomy_changed", "guardian_lowered")


def _at(entry: dict) -> datetime:
    return datetime.fromisoformat(entry["at"])


def _count_start(rows: list[dict], country: str, since: datetime | None) -> datetime | None:
    changed = [_at(entry) for entry in rows if entry["type"] in CHANGES and entry.get("country") == country]
    if since:
        changed.append(since)
    return max(changed, default=None)


def _country_rate(rows: list[dict], country: str, since: datetime | None) -> dict:
    start = _count_start(rows, country, since)
    counts = {decision: 0 for decision in DECISIONS}
    for entry in rows:
        if entry["type"] not in DECISIONS or (start and _at(entry) <= start):
            continue
        doc = store.get("mi-cases", entry["case"])
        if doc and doc["country"] == country and doc.get("draft"):
            counts[entry["type"]] += 1
    total = sum(counts.values())
    override_rate = 0.0
    if total:
        override_rate = round(counts["rejected"] / total, 4)
    return {**counts, "reviewed": total, "override_rate": override_rate}


def override_rates(since: datetime | None = None) -> dict[str, dict]:
    """For each country: the AI drafts reviewed, how many were rejected, and the share. It counts from the ledger since that country's last change."""
    rows = [row["entry"] for row in ledger.entries()]
    return {country: _country_rate(rows, country, since) for country in world.autonomy_seed()["auto_send"]}


def patrol(since: datetime | None = None) -> list[dict]:
    """Lower each country whose reviewers reject too much. Gives back what it lowered. Run it again and it lowers nothing."""
    # Step 1: Read the limits.
    limits = world.autonomy_seed()["guardian"]
    lowered = []
    # Step 2: Look at each country's override rate.
    for country, rate in override_rates(since).items():
        # Step 3: Skip a country with too few decisions or a low rate.
        if rate["reviewed"] < limits["min_decisions"] or rate["override_rate"] <= limits["max_override_rate"]:
            continue
        setting = cases.autonomy_setting(country)
        if not setting["enabled"]:
            continue
        # Step 4: Turn its auto replies off.
        cases.save_autonomy(country, setting | {"enabled": False})
        # Step 5: Write what was lowered to the ledger.
        ledger.append({"type": "guardian_lowered", "country": country, "override_rate": rate["override_rate"],
                       "reviewed": rate["reviewed"], "limit": limits["max_override_rate"]})
        lowered.append({"country": country, **rate})
    return lowered
