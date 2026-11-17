"""The last step of a case: hand it to the right team, or send the reply after one more check."""

import hashlib
from datetime import UTC, datetime

from hcpagents import events, grounding, store
from hcpagents.case_core import Case

STATUS = {
    "send": "sent",
    "review": "awaiting_review",
    "pv": "with_pharmacovigilance",
    "offlabel": "with_medical",
    "specialist": "with_specialist",
    "decline": "declined",
}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def handoff(case: Case) -> None:
    doc = case.doc
    doc["status"] = STATUS[doc["route"]]
    if doc["route"] == "send":
        send(case, approved_by=None)
    elif doc["route"] == "review":
        events.publish("ReviewNeeded", {"case": doc["id"], "country": doc["country"], "why": doc["decision"]["why"]})
    elif doc["route"] == "pv":
        events.publish("SafetySignal", {"case": doc["id"], "country": doc["country"], "product": doc["product"],
                                        "signals": doc["signals"], "reporter": doc["hcp"] and doc["hcp"]["name"],
                                        "received": doc["inquiry"]["received"]})


def _record_touch(case: Case) -> None:
    doc = case.doc
    store.put("mi-touches", {"id": f"touch-{doc['id']}", "hcp": doc["hcp"]["id"], "on": doc["sent_at"][:10],
                             "channel": doc["inquiry"]["channel"], "kind": "mi_reply", "product": doc["product"],
                             "promotional": False, "status": "done", "case": doc["id"],
                             "summary": f"Medical information reply sent for case {doc['id']}."})


def send(case: Case, approved_by: str | None) -> bool:
    """Check the draft again against the content store as it is now, then send. If the check fails, nothing goes out."""
    doc = case.doc
    check = grounding.verify(doc["draft"]["segments"], doc["product"], doc["country"], store.content())
    doc["send_check"] = check
    if not check["grounded"]:
        doc["status"] = "blocked_at_send"
        doc["history"].append({"at": now(), "event": "Send blocked", "detail": check["problems"]})
        case.audit({"type": "send_blocked", "problems": check["problems"]})
        return False
    doc["status"] = "sent"
    doc["sent_at"] = now()
    event = "Sent"
    if approved_by:
        event = f"Approved and sent by {approved_by}"
    doc["history"].append({"at": doc["sent_at"], "event": event})
    case.audit({"type": "reply_sent", "approved_by": approved_by,
                "blocks": [(segment["block_id"], segment["version"]) for segment in doc["draft"]["segments"]],
                "reply_sha256": sha(doc["draft"]["text"])})
    if doc["hcp"]:
        _record_touch(case)
    return True
