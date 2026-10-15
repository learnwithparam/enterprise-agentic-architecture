"""The synthetic world is consistent: every reference resolves and every label has its required blocks."""

from hcpagents import grounding, world

FIELDS = {"id", "product", "country", "topic", "version", "status", "approved_on", "expires_on", "mlr_ref", "source", "text"}


def test_every_block_has_every_field():
    for b in world.blocks():
        assert FIELDS <= set(b), b["id"]


def test_every_label_scope_has_its_required_blocks_current():
    ids = {b["id"]: b for b in world.blocks()}
    for s in world.products()["scope"]:
        for rid in grounding.required_ids(s["product"], s["country"]):
            assert world.is_current(ids[rid]), rid


def test_every_reference_resolves():
    ids = {b["id"] for b in world.blocks()}
    hcps = {h["id"] for h in world.hcp_world()["hcp"]}
    for t in world.hcp_world()["touch"] + world.hcp_world()["planned"]:
        assert t["hcp"] in hcps
        assert t.get("content") in (None, *ids)
    for i in world.inquiries():
        assert i.get("hcp") in (None, *hcps)
        assert i["expect"] in world.ROUTES and set(i.get("also_safe", [])) <= set(world.ROUTES)
