"""Demo routes, limits, the stack's guards and an unknown block. Only the last test needs Floci."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template
from fastapi.testclient import TestClient
from stack import Platform

from hcpagents import api, api_proof, auth, ratelimit

ROOT = Path(__file__).resolve().parents[1]
DEMO_PATHS = {"/api/proof/tamper", "/api/proof/restore", "/api/proof/delete-archive", "/api/reset"}


def _paths(routers) -> set[str]:
    return {route.path for router in routers for route in router.routes}


def test_the_demo_routes_exist_only_when_the_run_is_local(monkeypatch):
    monkeypatch.setenv("MI_ENV", "production")
    assert not DEMO_PATHS & _paths(api_proof.routers())
    monkeypatch.delenv("MI_ENV")  # no value means production
    assert not DEMO_PATHS & _paths(api_proof.routers())
    monkeypatch.setenv("MI_ENV", "local")
    assert DEMO_PATHS <= _paths(api_proof.routers())


def test_this_test_run_serves_the_demo_routes_because_it_is_local():
    assert DEMO_PATHS <= {getattr(route, "path", None) for route in api.app.routes}


def test_production_names_no_aws_endpoint_so_it_talks_to_real_aws():
    env = {key: value for key, value in os.environ.items() if key != "MI_AWS_ENDPOINT"}
    shown = subprocess.run([sys.executable, "-c", "from hcpagents import aws; print(repr(aws.ENDPOINT))"], env=env, capture_output=True, text=True, check=True)
    assert shown.stdout.strip() == "''"


def test_the_window_allows_the_limit_then_says_how_long_to_wait():
    now = [0.0]
    window = ratelimit.SlidingWindow(2, 60, clock=lambda: now[0])
    assert window.hit("a") is None and window.hit("a") is None
    assert window.hit("a") == 60
    assert window.hit("b") is None  # another caller has its own window
    now[0] = 59
    assert window.hit("a") == 1
    now[0] = 61
    assert window.hit("a") is None  # the first call has left the window


def test_a_caller_over_the_limit_gets_429_on_sign_in_and_on_the_webhook(monkeypatch):
    client = TestClient(api.app)
    for route, path in ((ratelimit.LOGIN, "/api/login"), (ratelimit.HOOKS, "/hooks/quillon/crm")):
        monkeypatch.setattr(route.window, "limit", 0)
        r = client.post(path, json={"user": "u-brandt", "password": "x"})
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0, path


def test_the_caller_is_the_address_the_load_balancer_saw():
    class Request:
        headers = {"x-forwarded-for": "6.6.6.6, 203.0.113.9"}
        client = None
    assert ratelimit.caller_address(Request()) == "203.0.113.9"  # an earlier entry can be forged


@pytest.fixture(scope="module")
def synthesized(tmp_path_factory):
    out = tmp_path_factory.mktemp("cdk-out")  # pytest removes this, so a run leaves no copy of the project behind
    app = cdk.App(outdir=str(out))
    stack = Platform(app, "T", env=cdk.Environment(account="123456789012", region="eu-central-1"))
    return out, app.synth(), stack


@pytest.fixture(scope="module")
def template(synthesized):
    return Template.from_stack(synthesized[2])


def test_the_image_asset_holds_only_what_the_dockerfile_copies(synthesized):
    """Found 19 Nov 2026: with no .dockerignore, each run copied 1.4 GB of .venv and node_modules and filled the disk."""
    out = synthesized[0]
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    assert size < 50_000_000, f"the CDK asset is {size // 1_000_000} MB; check .dockerignore"


def test_the_stack_validates_cedar_strictly_against_a_schema_that_names_every_action(template):
    (store,) = template.find_resources("AWS::VerifiedPermissions::PolicyStore").values()
    assert store["Properties"]["ValidationSettings"] == {"Mode": "STRICT"}
    actions = set(json.loads(store["Properties"]["Schema"]["CedarJson"])[""]["actions"])
    named = set(re.findall(r'Action::"(\w+)"', "".join(f.read_text() for f in (ROOT / "policies" / "cedar").glob("*.cedar"))))
    assert named <= actions, named - actions


def test_the_stack_alarms_on_5xx_and_parked_events_and_a_deploy_rolls_back_on_them(template):
    alarms = template.find_resources("AWS::CloudWatch::Alarm").values()
    metrics = {a["Properties"]["MetricName"] for a in alarms}
    assert {"HTTPCode_ELB_5XX_Count", "HTTPCode_Target_5XX_Count", "ApproximateNumberOfMessagesVisible"} <= metrics
    (group,) = template.find_resources("AWS::CodeDeploy::DeploymentGroup").values()
    assert len(group["Properties"]["AlarmConfiguration"]["Alarms"]) == len(list(alarms))
    assert "DEPLOYMENT_STOP_ON_ALARM" in group["Properties"]["AutoRollbackConfiguration"]["Events"]


def test_the_load_balancer_sits_behind_a_firewall_with_common_rules_and_a_rate_cap(template):
    (acl,) = template.find_resources("AWS::WAFv2::WebACL").values()
    rules = {r["Name"]: r["Statement"] for r in acl["Properties"]["Rules"]}
    assert rules["CommonRules"]["ManagedRuleGroupStatement"]["Name"] == "AWSManagedRulesCommonRuleSet"
    assert rules["PerAddressCap"]["RateBasedStatement"]["AggregateKeyType"] == "IP"
    (link,) = template.find_resources("AWS::WAFv2::WebACLAssociation").values()
    assert "LB" in json.dumps(link["Properties"]["ResourceArn"])


def test_a_big_body_is_blocked_everywhere_except_the_signed_webhooks(template):
    (acl,) = template.find_resources("AWS::WAFv2::WebACL").values()
    rule = next(r for r in acl["Properties"]["Rules"] if r["Name"] == "BigBodyOutsideHooks")
    assert "Block" in rule["Action"]
    first, second = rule["Statement"]["AndStatement"]["Statements"]
    assert first["SizeConstraintStatement"]["Size"] == 8192
    hook = second["NotStatement"]["Statement"]["ByteMatchStatement"]
    assert hook["SearchString"] == "/hooks/" and hook["PositionalConstraint"] == "STARTS_WITH"


@pytest.mark.floci
def test_withdrawing_an_unknown_block_is_a_404_not_a_crash():
    client = TestClient(api.app)
    token = client.post("/api/login", json={"user": "u-weber", "password": auth.local_password("u-weber")}).json()["token"]
    r = client.post("/api/content/NO-SUCH-BLOCK/withdraw", headers={"Authorization": f"Bearer {token}"}, json={"note": "x"})
    assert r.status_code == 404
