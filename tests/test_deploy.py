"""The CDK app synthesizes clean (cdk-nag, zero findings) and keeps the properties the design depends on (ADR 0029)."""

from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk import aws_s3 as s3
from aws_cdk.assertions import Template
from cdk_nag import AwsSolutionsChecks

from stack import TENANTS, Platform

ALLOWED = ("claude-haiku-5-5", "claude-sonnet-5-5")


@pytest.fixture(scope="module")
def stack():
    app = cdk.App()
    s = Platform(app, "T", env=cdk.Environment(account="123456789012", region="eu-central-1"))
    cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app))
    app.synth()  # raises ValidationFailed on any cdk-nag finding
    return s


def test_cdk_nag_finds_nothing_to_fix(stack):
    """The fixture synthesized, and synthesis refuses a stack with a finding."""
    assert stack.node.try_find_child("Postgres") is not None


def test_cdk_nag_refuses_a_stack_with_a_finding():
    app = cdk.App()
    bad = cdk.Stack(app, "Bad")
    s3.Bucket(bad, "Open")  # no TLS enforcement, no access logs
    cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app))
    with pytest.raises(RuntimeError, match="ValidationFailed"):
        app.synth()


def test_each_tenant_has_its_own_locked_encrypted_ledger_and_key(stack):
    t = Template.from_stack(stack)
    t.resource_count_is("AWS::KMS::Key", len(TENANTS))
    ledgers = [r for r in t.find_resources("AWS::S3::Bucket").values() if r["Properties"].get("ObjectLockEnabled")]
    assert len(ledgers) == len(TENANTS)
    for r in ledgers:
        p = r["Properties"]
        assert p["ObjectLockConfiguration"]["Rule"]["DefaultRetention"]["Mode"] == "COMPLIANCE"
        assert p["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "aws:kms"


def test_bedrock_is_granted_for_the_two_allowed_models_only(stack):
    t = Template.from_stack(stack)
    resources = []
    for pol in t.find_resources("AWS::IAM::Policy").values():
        for st in pol["Properties"]["PolicyDocument"]["Statement"]:
            actions = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
            if any(a.startswith("bedrock:") for a in actions):
                resources += st["Resource"] if isinstance(st["Resource"], list) else [st["Resource"]]
    assert resources
    for r in map(str, resources):
        assert any(f"anthropic.{m}" in r for m in ALLOWED), r


def test_every_cedar_file_is_a_verified_permissions_policy(stack):
    files = list((Path(__file__).resolve().parent.parent / "policies" / "cedar").glob("*.cedar"))
    Template.from_stack(stack).resource_count_is("AWS::VerifiedPermissions::Policy", len(files))


def test_the_database_is_private_encrypted_and_protected(stack):
    t = Template.from_stack(stack)
    t.has_resource_properties("AWS::RDS::DBCluster", {"StorageEncrypted": True, "DeletionProtection": True, "BackupRetentionPeriod": 14})
    assert not any(r["Properties"].get("PubliclyAccessible") for r in t.find_resources("AWS::RDS::DBInstance").values())


def test_a_user_cannot_write_their_own_role_or_tenant(stack):
    """Cedar reads custom:role and custom:tenant from the token, so the console client may write neither."""
    (client,) = Template.from_stack(stack).find_resources("AWS::Cognito::UserPoolClient").values()
    written = client["Properties"]["WriteAttributes"]
    assert written and not any(a.startswith("custom:") for a in written)
