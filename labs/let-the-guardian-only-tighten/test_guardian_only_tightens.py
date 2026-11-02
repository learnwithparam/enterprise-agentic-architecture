"""Let the guardian only tighten: it can switch a country off, never on, and the improver only proposes."""

import json
from datetime import UTC, datetime

import pytest

from hcpagents import cases, guardian, infra, ledger, store

pytestmark = pytest.mark.floci


def review(country: str, approved: int, rejected: int) -> None:
    """Seed reviewed AI drafts the way approve and reject leave them: a case with a draft, and a ledger entry."""
    for kind, n in (("approved", approved), ("rejected", rejected)):
        for i in range(n):
            cid = f"lab-{country}-{kind}-{i}-{datetime.now(UTC).timestamp()}"
            store.put("mi-cases", {"id": cid, "country": country, "product": "p", "draft": {"segments": []},
                                   "questions": [{"topic": "dosing"}]})
            ledger.append({"case": cid, "type": kind})


@pytest.fixture(autouse=True)
def fresh():
    infra.provision(reset=True)


def test_reviewers_who_reject_too_much_switch_a_country_off():
    start = datetime.now(UTC)
    review("DE", approved=2, rejected=4)
    assert [c["country"] for c in guardian.patrol(start)] == ["DE"]
    assert not cases.autonomy_setting("DE")["enabled"] and cases.autonomy_setting("US")["enabled"]


def test_a_spotless_record_never_switches_a_country_back_on():
    start = datetime.now(UTC)
    cases.client("ssm").put_parameter(Name="/mi/autonomy/DE", Type="String", Overwrite=True,
                                      Value=json.dumps(cases.autonomy_setting("DE") | {"enabled": False}))
    review("DE", approved=9, rejected=0)
    assert guardian.patrol(start) == [] and not cases.autonomy_setting("DE")["enabled"]


def test_too_few_decisions_change_nothing():
    review("US", approved=0, rejected=3)
    assert guardian.patrol(datetime.now(UTC).replace(year=2000)) == [] and cases.autonomy_setting("US")["enabled"]
