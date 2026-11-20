"""The human decisions on a case. Cedar allows each one and the ledger records it."""

import contextlib
from datetime import UTC, datetime

from hcpagents import approval, authz, cache, events, grounding, ledger, memory, store, world
from hcpagents.case_core import Case, autonomy_setting, restore, save_autonomy
from hcpagents.case_send import now, send

SIGNATURE_MAX_AGE_S = 300  # A signature older than this was not made for this approval.
OPEN_STATUSES = ("awaiting_review", "blocked_at_send")
WITHDRAWN = "invalidated_source_withdrawn"


class Denied(Exception):
    pass


def _load(case_id: str) -> Case:
    doc = store.get("mi-cases", case_id)
    if doc is None:
        raise KeyError(case_id)
    return restore(doc)


def _authorize(case: Case, user: dict, action: str) -> None:
    doc = case.doc
    allowed, why = authz.user_can(user, action, "Case", doc["id"], {"country": doc["country"], "route": doc["route"]})
    case.audit({"type": "authz", "user": user["id"], "action": action, "allowed": allowed, "reason": why})
    if not allowed:
        raise Denied(f"{user['name']} may not {action} on {doc['id']}. {why}")


def _signed_freshly(user: dict, signature: dict | None) -> bool:
    if not signature or signature["user"] != user["id"]:
        return False
    age = datetime.now(UTC) - datetime.fromisoformat(signature["at"])
    return age.total_seconds() <= SIGNATURE_MAX_AGE_S


def _check_signature(case: Case, user: dict, signature: dict | None) -> None:
    """Approval is an e-signature. It is the approver's own fresh sign in, kept with its meaning."""
    if not _signed_freshly(user, signature):
        raise Denied(f"{user['name']} must sign in again to approve {case.doc['id']}")
    case.audit({"type": "e_signature", "user": user["id"], "meaning": signature["meaning"], "method": signature["method"],
                "signed_at": signature["at"]})


def approve(case_id: str, user: dict, signature: dict | None) -> dict:
    case = _load(case_id)
    _authorize(case, user, "ApproveReply")
    _check_signature(case, user, signature)
    if case.doc["status"] not in OPEN_STATUSES:
        raise Denied(f"Case {case_id} is {case.doc['status']}, not awaiting review")
    if not case.doc.get("draft"):
        raise Denied("There is no AI draft to approve. Approved content does not cover this case; medical writes the reply.")
    case.doc["approval"] = approval.bind(case.doc, signature)
    case.audit({"type": "approved", "user": user["id"], "approval_digest": case.doc["approval"]["digest"],
                "release": case.doc["approval"]["release"], "draft_version": case.doc["approval"]["draft_version"]})
    send(case, approved_by=user["name"])
    store.put("mi-cases", case.doc)
    return case.doc


def reject(case_id: str, user: dict, note: str) -> dict:
    case = _load(case_id)
    _authorize(case, user, "RejectReply")
    case.doc["status"] = "rejected"
    case.doc["history"].append({"at": now(), "event": f"Rejected by {user['name']}", "detail": note})
    case.audit({"type": "rejected", "user": user["id"]}, private={"note": note})
    store.put("mi-cases", case.doc)
    return case.doc


def escalate(case_id: str, waited_s: float) -> dict:
    """No reviewer decided in time. Say so on the ledger and tell the queue. Nothing is sent or dropped."""
    case = _load(case_id)
    doc = case.doc
    if doc["status"] not in OPEN_STATUSES or doc.get("escalated_at"):
        return doc
    doc["escalated_at"] = now()
    doc["history"].append({"at": doc["escalated_at"], "event": "Escalated", "detail": f"No decision after {round(waited_s)} seconds"})
    case.audit({"type": "review_overdue", "waited_s": round(waited_s)})
    events.publish("ReviewOverdue", {"case": doc["id"], "country": doc["country"], "waited_s": round(waited_s)})
    store.put("mi-cases", doc)
    return doc


def withdraw(block_id: str, user: dict, reason: str) -> dict:
    """A content owner pulls a block. Each case and planned touch that uses it is checked again."""
    block = store.get("mi-content", block_id)
    if block is None:
        raise LookupError(f"No block {block_id}")
    allowed, why = authz.user_can(user, "WithdrawContent", "Content", block_id, {"product": block["product"], "country": block["country"]})
    ledger.append({"type": "authz", "user": user["id"], "action": "WithdrawContent", "allowed": allowed, "reason": why, "block": block_id})
    if not allowed:
        raise Denied(f"{user['name']} may not withdraw content. {why}")
    block["status"] = "withdrawn"
    block["withdrawn"] = {"by": user["name"], "reason": reason, "at": now()}
    store.put("mi-content", block)
    ledger.append({"type": "content_withdrawn", "block": block_id, "version": block["version"], "user": user["id"], "reason": reason})
    tenant = world.current_tenant()
    try:
        evicted = cache.evict_block(tenant, block_id)
    except cache.CacheDown as error:
        evicted = None
        ledger.append({"type": "cache_evict_failed", "block": block_id, "error": str(error)})
    events.publish("ContentWithdrawn", {"tenant": tenant, "block": block_id, "version": block["version"]})
    invalidated = _invalidate_drafts_of(block_id)
    return {"block": block_id, "queued": True, "cache_evicted": evicted, "invalidated": invalidated}


def process_invalidations() -> dict:
    """Read the content events for the content steward. Each one clears the cache and checks every open draft again.

    An event that keeps failing goes to the dead letters (ADR 0020).
    """
    affected = []

    def handle(event: dict) -> None:
        affected.extend(_invalidate(event))

    events.consume("mi-content-invalidation", handle)
    return {"cases": affected}


def _invalidate_case(doc: dict, block_id: str) -> None:
    """Take a draft out of the approvable states. The reviewer sees why, and the queue stops asking them to look at it."""
    doc["verification"] = grounding.verify(doc["draft"]["segments"], doc["product"], doc["country"], store.content())
    doc["status"] = WITHDRAWN
    doc["history"].append({"at": now(), "event": f"Draft invalidated: {block_id} was withdrawn"})
    store.put("mi-cases", doc)
    waiting = store.get("mi-reviewer-queue", f"review-{doc['id']}")
    if waiting:
        store.put("mi-reviewer-queue", waiting | {"status": "source_withdrawn"})
    ledger.append({"case": doc["id"], "type": "draft_invalidated", "block": block_id})


def _invalidate_drafts_of(block_id: str) -> list[str]:
    """Right after a withdrawal, close the drafts that use the block. The draft sources index finds them."""
    affected = []
    for source in store.scan_prefix("mi-draft-sources", f"{block_id}:"):
        doc = store.get("mi-cases", source["case"])
        if doc and doc.get("status") == "awaiting_review" and doc.get("draft"):
            _invalidate_case(doc, block_id)
            affected.append(doc["id"])
    return affected


def _invalidate(event: dict) -> list[str]:
    """The steward is the backstop. It reads every case, so it also catches drafts that have no sources note and events from outside."""
    with contextlib.suppress(cache.CacheDown):
        cache.evict_block(event["tenant"], event["block"])
    affected = []
    for doc in store.scan("mi-cases"):
        if doc.get("status") != "awaiting_review" or not doc.get("draft"):
            continue
        if event["block"] in {segment["block_id"] for segment in doc["draft"]["segments"]}:
            _invalidate_case(doc, event["block"])
            affected.append(doc["id"])
    return affected


def set_autonomy(country: str, enabled: bool, user: dict) -> dict:
    allowed, why = authz.user_can(user, "SetAutonomy", "Country", country, {"country": country})
    ledger.append({"type": "authz", "user": user["id"], "action": "SetAutonomy", "allowed": allowed, "reason": why})
    if not allowed:
        raise Denied(f"{user['name']} may not change automatic replies. {why}")
    setting = autonomy_setting(country) | {"enabled": enabled}
    save_autonomy(country, setting)
    ledger.append({"type": "autonomy_changed", "country": country, "enabled": enabled, "user": user["id"]})
    return setting


def erase_person(hcp_id: str, user: dict) -> dict:
    """Right to erasure (GDPR Article 17). The sealed ledger data of the doctor becomes unreadable. The chain stays whole."""
    allowed, why = authz.user_can(user, "ErasePerson", "Ledger", "main", {})
    ledger.append({"type": "authz", "user": user["id"], "action": "ErasePerson", "allowed": allowed, "reason": why})
    if not allowed:
        raise Denied(f"{user['name']} may not erase personal data. {why}")
    memory.forget(hcp_id)
    return ledger.erase_subject(hcp_id, user["id"])
