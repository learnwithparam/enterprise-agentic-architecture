"""Shared set up for the live_g tests. A real Case runs with the ledger, the store and the model call faked in memory.

No database, Floci or model is needed. The wiring under test is the real case code.
"""

from hcpagents import agents, case_core, ledger, store, world
from hcpagents.router import HAIKU

INQUIRY = {"id": "inq-g-1", "channel": "portal", "hcp": "hcp-kaya", "text": "Where should Veltrona be stored?"}


class Rig:
    """The fakes one test shares: ledger entries, the usage documents, and the prompts the model was sent."""

    def __init__(self):
        self.entries: list[dict] = []
        self.documents: dict[str, dict] = {}
        self.prompts: list[str] = []
        self.replies: list[dict] = []

    def ledger_types(self) -> list[str]:
        return [entry["type"] for entry in self.entries]


def install(monkeypatch, inquiry: dict | None = None, content: dict | None = None) -> tuple[case_core.Case, Rig]:
    rig = Rig()
    blocks = content or {block["id"]: dict(block) for block in world.blocks()}

    def append(entry, subject=None, private=None):
        rig.entries.append(entry)

    def get(table, doc_id):
        return rig.documents.get(f"{table}/{doc_id}")

    def put(table, doc):
        rig.documents[f"{table}/{doc['id']}"] = doc

    def add_to(table, doc_id, field, amount):
        document = rig.documents.setdefault(f"{table}/{doc_id}", {"id": doc_id})
        document[field] = document.get(field, 0) + amount
        return document[field]

    async def call(name, prompt, case_ref, store_content, authorize, audit):
        rig.prompts.append(prompt)
        reply = rig.replies.pop(0)
        return {"key": "stub", "mode": "replay", "usage": {}, "cost_usd": 0.0, "model": HAIKU,
                "routing": "stub", "attempts": 1, "tool_calls": reply.get("tool_calls", []), "output": reply["output"]}

    monkeypatch.setattr(ledger, "append", append)
    monkeypatch.setattr(store, "get", get)
    monkeypatch.setattr(store, "put", put)
    monkeypatch.setattr(store, "add_to", add_to)
    monkeypatch.setattr(store, "content", lambda: blocks)
    monkeypatch.setattr(agents, "call", call)
    case = case_core.Case(inquiry or INQUIRY)
    case.doc["product"] = "VEL"
    return case, rig
