"""Personal data in the ledger: sealed at rest, erasable without breaking the chain, and never shared across tenants."""

import asyncio
import json

import pytest

from hcpagents import cases, infra, ledger, privacy, world
from hcpagents.aws import client

pytestmark = pytest.mark.floci

RAMAN, BRANDT = world.person("u-raman"), world.person("u-brandt")
CASE = "inq-105"


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def run_case():
    d = asyncio.run(cases.run(CASE))
    return d["hcp"]["id"] if d["hcp"] else f"inquiry:{CASE}"


def sealed_rows():
    return [r for r in ledger.entries(CASE) if "sealed" in r["entry"]]


def raw_storage() -> str:
    """Everything the ledger puts in DynamoDB and S3, as one string."""
    ddb, s3 = client("dynamodb"), client("s3")
    rows = ddb.scan(TableName=ledger.TABLE)["Items"]
    objs = s3.list_objects_v2(Bucket=ledger.ARCHIVE).get("Contents", [])
    bodies = [s3.get_object(Bucket=ledger.ARCHIVE, Key=o["Key"])["Body"].read().decode() for o in objs]
    return json.dumps(rows) + "".join(bodies)


def test_agent_output_is_sealed_in_dynamodb_and_in_the_locked_archive():
    run_case()
    rows = sealed_rows()
    assert rows and all("output" not in r["entry"] for r in rows)
    opened = [privacy.reveal(r["entry"])["private"]["output"] for r in rows]
    texts = [json.dumps(o, ensure_ascii=False) for o in opened]
    assert any(len(t) > 20 for t in texts)
    stored = raw_storage()
    assert not any(t in stored for t in texts)


def test_entries_stay_sealed_unless_the_caller_asks_to_reveal():
    run_case()
    assert all("private" not in r["entry"] for r in ledger.entries(CASE))
    assert all("private" in r["entry"] for r in ledger.entries(CASE, reveal=True) if "subject" in r["entry"] and r["entry"]["type"] == "agent_call")


def test_erasing_a_person_makes_their_data_unreadable_and_the_chain_still_verifies():
    hcp = run_case()
    assert ledger.verify()["ok"]
    out = cases.erase_person(hcp, RAMAN)
    assert out["erased"] is True
    revealed = [r["entry"] for r in ledger.entries(CASE, reveal=True) if r["entry"].get("type") == "agent_call"]
    assert revealed and all(e["private"] == {"erased": True} for e in revealed)
    assert ledger.verify()["ok"]
    assert any(r["entry"]["type"] == "erased" and r["entry"]["subject"] == out["subject"] for r in ledger.entries())


def test_erasure_is_for_compliance_only_and_the_refusal_is_recorded():
    hcp = run_case()
    with pytest.raises(cases.Denied):
        cases.erase_person(hcp, BRANDT)
    assert privacy.reveal(sealed_rows()[0]["entry"])["private"] != {"erased": True}
    assert any(r["entry"].get("action") == "ErasePerson" and r["entry"]["allowed"] is False for r in ledger.entries())


def test_a_pseudonym_is_stable_within_a_tenant_and_differs_between_people_and_tenants():
    here = privacy.pseudonym("hcp-kaya")
    assert here == privacy.pseudonym("hcp-kaya")
    assert here != privacy.pseudonym("hcp-brenner")
    with world.as_tenant("marlowe"):
        assert privacy.pseudonym("hcp-kaya") != here


def test_each_tenant_has_its_own_chain():
    run_case()
    mine = len(ledger.entries())
    with world.as_tenant("marlowe"):
        assert ledger.entries() == []
        ledger.append({"type": "authz", "user": "x", "action": "SetAutonomy", "allowed": True})
        assert len(ledger.entries()) == 1 and ledger.verify()["ok"]
    assert len(ledger.entries()) == mine and ledger.verify()["ok"]
