"""The CDK app synthesizes clean (cdk-nag, zero findings) and keeps the properties the design depends on (ADR 0029)."""

from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk import aws_s3 as s3
from aws_cdk.assertions import Template
from cdk_nag import AwsSolutionsChecks

import migrate_handler
from stack import REPLICA_REGION, TENANTS, Platform, SecondRegion, replica_bucket

ALLOWED = ("claude-haiku-5-5", "claude-sonnet-5-5")


ACCOUNT = "123456789012"


@pytest.fixture(scope="module")
def built():
    app = cdk.App()
    primary = Platform(app, "T", env=cdk.Environment(account=ACCOUNT, region="eu-central-1"))
    second = SecondRegion(app, "S", env=cdk.Environment(account=ACCOUNT, region=REPLICA_REGION))
    cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app))
    app.synth()  # raises ValidationFailed on any cdk-nag finding, in either region
    return primary, second


@pytest.fixture(scope="module")
def stack(built):
    return built[0]


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


def _services(t):
    return {k: v for k, v in t.find_resources("AWS::ECS::Service").items()}


def test_migration_runs_before_service(stack):
    """The migration task is a custom resource, and every service waits for it (ADR 0029)."""
    t = Template.from_stack(stack)
    (migrate_id,) = [k for k, v in t.find_resources("AWS::CloudFormation::CustomResource").items() if "Migrate" in k]
    services = _services(t)
    assert len(services) == 2  # the API and the worker
    for name, svc in services.items():
        assert migrate_id in svc["DependsOn"], f"{name} can start before the migration"
    (task,) = [v for k, v in t.find_resources("AWS::ECS::TaskDefinition").items() if "MigrationTask" in k]
    assert task["Properties"]["ContainerDefinitions"][0]["Command"] == ["python", "-m", "hcpagents.db"]


def test_blue_green_group(stack):
    t = Template.from_stack(stack)
    (api,) = [v for k, v in _services(t).items() if k.startswith("ApiService")]
    assert api["Properties"]["DeploymentController"] == {"Type": "CODE_DEPLOY"}
    (group,) = t.find_resources("AWS::CodeDeploy::DeploymentGroup").values()
    p = group["Properties"]
    assert p["DeploymentConfigName"] == "CodeDeployDefault.ECSCanary10Percent5Minutes"
    assert p["AutoRollbackConfiguration"]["Events"] == ["DEPLOYMENT_FAILURE"]
    assert p["BlueGreenDeploymentConfiguration"]["TerminateBlueInstancesOnDeploymentSuccess"]["Action"] == "TERMINATE"
    assert len(p["LoadBalancerInfo"]["TargetGroupPairInfoList"][0]["TargetGroups"]) == 2
    t.resource_count_is("AWS::ElasticLoadBalancingV2::Listener", 2)  # live and test


def test_second_region_replication(built):
    primary, second = built
    ledgers = [r for r in Template.from_stack(primary).find_resources("AWS::S3::Bucket").values() if r["Properties"].get("ObjectLockEnabled")]
    rules = {r["Properties"]["ReplicationConfiguration"]["Rules"][0]["Destination"]["Bucket"] for r in ledgers}
    assert rules == {f"arn:aws:s3:::{replica_bucket(t, ACCOUNT)}" for t in TENANTS}
    for r in ledgers:
        rule = r["Properties"]["ReplicationConfiguration"]["Rules"][0]
        assert rule["Status"] == "Enabled" and rule["Destination"]["EncryptionConfiguration"]["ReplicaKmsKeyID"].startswith(f"arn:aws:kms:{REPLICA_REGION}:")
    replicas = [r for r in Template.from_stack(second).find_resources("AWS::S3::Bucket").values() if r["Properties"].get("ObjectLockEnabled")]
    assert {r["Properties"]["BucketName"] for r in replicas} == {replica_bucket(t, ACCOUNT) for t in TENANTS}
    for r in replicas:  # the copy is as locked as the original, and in a different region so its name differs
        assert r["Properties"]["ObjectLockConfiguration"]["Rule"]["DefaultRetention"]["Mode"] == "COMPLIANCE"
        assert r["Properties"]["VersioningConfiguration"]["Status"] == "Enabled"
    assert second.region != primary.region


def test_cdk_nag_clean(built):
    """Both stacks synthesized with cdk-nag attached, and every suppression carries a reason."""
    for stack in built:
        assert stack.node.try_find_child("AccessLogs") is not None


class FakeEcs:
    def __init__(self, status="STOPPED", code=0, failures=()):
        self.status, self.code, self.failures = status, code, list(failures)
        self.ran = None

    def run_task(self, **kw):
        self.ran = kw
        return {"failures": self.failures, "tasks": [{"taskArn": "arn:task/1"}]}

    def describe_tasks(self, cluster, tasks):
        return {"tasks": [{"lastStatus": self.status, "containers": [{"exitCode": self.code}], "stoppedReason": "Essential container exited"}]}


EVENT = {"RequestType": "Update", "PhysicalResourceId": "arn:task/1", "ResourceProperties": {
    "Cluster": "c", "TaskDefinition": "td", "Subnets": ["s-1"], "SecurityGroups": ["sg-1"]}}


def test_migration_handler_runs_the_task_and_waits_for_it(monkeypatch):
    fake = FakeEcs(status="RUNNING")
    monkeypatch.setattr(migrate_handler, "ecs", fake)
    assert migrate_handler.on_event(EVENT) == {"PhysicalResourceId": "arn:task/1"}
    assert fake.ran["networkConfiguration"]["awsvpcConfiguration"]["assignPublicIp"] == "DISABLED"
    assert migrate_handler.is_complete(EVENT) == {"IsComplete": False}
    fake.status = "STOPPED"
    assert migrate_handler.is_complete(EVENT) == {"IsComplete": True}


def test_a_failed_migration_fails_the_deploy(monkeypatch):
    monkeypatch.setattr(migrate_handler, "ecs", FakeEcs(code=1))
    with pytest.raises(RuntimeError, match="exited with 1"):
        migrate_handler.is_complete(EVENT)
    monkeypatch.setattr(migrate_handler, "ecs", FakeEcs(failures=[{"reason": "RESOURCE:CPU"}]))
    with pytest.raises(RuntimeError, match="did not start"):
        migrate_handler.on_event(EVENT)
