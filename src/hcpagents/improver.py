"""The improver reads what reviewers fix. It suggests changes and never makes one (ADR 0026).

A rejected AI draft is a fix. We keep it as proof.
If reviewers keep rejecting a topic in a country, we suggest it. We suggest to stop auto replies on it there.
A human accepts a suggestion. Then the release gate shows if the change helped.
"""

from hcpagents import ledger, store

MIN_CORRECTIONS = 2


def harvest() -> list[str]:
    """Record each rejected AI draft once. The note names its country, product and topics, with no text."""
    new = []
    for row in ledger.entries():
        entry = row["entry"]
        if entry["type"] != "rejected" or store.get("mi-proposals", f"fix-{entry['case']}"):
            continue
        doc = store.get("mi-cases", entry["case"])
        if doc and doc.get("draft"):
            store.put("mi-proposals", {"id": f"fix-{entry['case']}", "kind": "correction", "case": entry["case"],
                                       "country": doc["country"], "product": doc["product"],
                                       "topics": sorted({question["topic"] for question in doc["questions"]})})
            new.append(entry["case"])
    return new


def propose() -> list[dict]:
    """Suggest one change for each country and topic. Reviewers fixed it MIN_CORRECTIONS times or more."""
    harvest()
    seen: dict[tuple, list[str]] = {}
    for doc in store.scan("mi-proposals"):
        if doc["kind"] == "correction":
            for topic in doc["topics"]:
                seen.setdefault((doc["country"], topic), []).append(doc["case"])
    proposals = []
    for (country, topic), case_ids in sorted(seen.items()):
        if len(case_ids) >= MIN_CORRECTIONS:
            proposal = {"id": f"stop-{country}-{topic}", "kind": "stop_auto_send", "country": country, "topic": topic,
                        "cases": sorted(case_ids), "status": "proposed",
                        "change": f"Remove {topic} from the automatic topics for {country}"}
            old = store.get("mi-proposals", proposal["id"])
            if old:
                proposal["status"] = old["status"]
            store.put("mi-proposals", proposal)
            proposals.append(proposal)
    return proposals
