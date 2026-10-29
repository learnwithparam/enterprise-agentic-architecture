"""The improver turns reviewer corrections into proposals and promotes nothing (ADR 0026).

A rejected AI draft is a correction. Corrections are kept as evidence, and a topic that reviewers keep
rejecting in a country becomes a proposal to stop answering it automatically there. A human accepts a
proposal; the release gate (releases.py) then shows whether the change helped.
"""

from hcpagents import ledger, store

MIN_CORRECTIONS = 2


def harvest() -> list[str]:
    """Record each rejected AI draft once, as a correction naming its country, product and topics (no text)."""
    new = []
    for row in ledger.entries():
        e = row["entry"]
        if e["type"] != "rejected" or store.get("mi-proposals", f"fix-{e['case']}"):
            continue
        doc = store.get("mi-cases", e["case"])
        if doc and doc.get("draft"):
            store.put("mi-proposals", {"id": f"fix-{e['case']}", "kind": "correction", "case": e["case"], "country": doc["country"],
                                       "product": doc["product"], "topics": sorted({q["topic"] for q in doc["questions"]})})
            new.append(e["case"])
    return new


def propose() -> list[dict]:
    """One proposal per country and topic that reviewers corrected at least MIN_CORRECTIONS times."""
    harvest()
    seen: dict[tuple, list[str]] = {}
    for d in store.scan("mi-proposals"):
        if d["kind"] == "correction":
            for t in d["topics"]:
                seen.setdefault((d["country"], t), []).append(d["case"])
    out = []
    for (country, topic), cases in sorted(seen.items()):
        if len(cases) >= MIN_CORRECTIONS:
            p = {"id": f"stop-{country}-{topic}", "kind": "stop_auto_send", "country": country, "topic": topic,
                 "cases": sorted(cases), "status": "proposed",
                 "change": f"Remove {topic} from the automatic topics for {country}"}
            if (old := store.get("mi-proposals", p["id"])):
                p["status"] = old["status"]
            store.put("mi-proposals", p)
            out.append(p)
    return out
