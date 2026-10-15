"""Provision every AWS resource the platform uses, on Floci, idempotently, then seed the world.

    uv run python -m hcpagents.infra          provision and seed (safe to rerun)
    uv run python -m hcpagents.infra --reset  wipe state and reseed; the locked archive stays
"""

import hashlib
import json
import sys

from botocore.exceptions import ClientError

from hcpagents import graph, world
from hcpagents.aws import REGION, client

TABLES = {
    "mi-content": ("id", None),
    "mi-cases": ("id", None),
    "mi-hcp": ("id", None),
    "mi-touches": ("id", None),
    "mi-ledger": ("chain", "seq"),
}
ARCHIVE = "mi-ledger-archive"
BUS = "mi-events"
QUEUES = {"mi-pv-intake": "SafetySignal", "mi-medical-review": "ReviewNeeded", "mi-content-invalidation": "ContentWithdrawn"}
KEY_ALIAS = "alias/mi-ledger"
MACHINE = "mi-inquiry-graph"
LOG_GROUP = "/mi/agents"
POOL = "mi-users"
ACCOUNT = "000000000000"


def _exists(fn) -> bool:
    try:
        fn()
        return True
    except ClientError:
        return False


def tables():
    ddb = client("dynamodb")
    have = set(ddb.list_tables()["TableNames"])
    for name, (pk, sk) in TABLES.items():
        if name in have:
            continue
        keys = [{"AttributeName": pk, "KeyType": "HASH"}]
        attrs = [{"AttributeName": pk, "AttributeType": "S"}]
        if sk:
            keys.append({"AttributeName": sk, "KeyType": "RANGE"})
            attrs.append({"AttributeName": sk, "AttributeType": "N"})
        ddb.create_table(TableName=name, KeySchema=keys, AttributeDefinitions=attrs, BillingMode="PAY_PER_REQUEST")


def archive():
    s3 = client("s3")
    if _exists(lambda: s3.head_bucket(Bucket=ARCHIVE)):
        return
    s3.create_bucket(Bucket=ARCHIVE, ObjectLockEnabledForBucket=True,
                     CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object_lock_configuration(Bucket=ARCHIVE, ObjectLockConfiguration={
        "ObjectLockEnabled": "Enabled",
        "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Years": 10}},
    })


def signing_key() -> str:
    kms = client("kms")
    for a in kms.list_aliases()["Aliases"]:
        if a["AliasName"] == KEY_ALIAS and a.get("TargetKeyId"):
            return a["TargetKeyId"]
    key = kms.create_key(KeyUsage="SIGN_VERIFY", KeySpec="ECC_NIST_P256", Description="Ledger checkpoints")
    kid = key["KeyMetadata"]["KeyId"]
    kms.create_alias(AliasName=KEY_ALIAS, TargetKeyId=kid)
    return kid


def events():
    eb, sqs = client("events"), client("sqs")
    if not _exists(lambda: eb.describe_event_bus(Name=BUS)):
        eb.create_event_bus(Name=BUS)
    for q, detail_type in QUEUES.items():
        url = sqs.create_queue(QueueName=q)["QueueUrl"]
        arn = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        rule = f"to-{q}"
        eb.put_rule(Name=rule, EventBusName=BUS, EventPattern=json.dumps({"detail-type": [detail_type]}))
        eb.put_targets(Rule=rule, EventBusName=BUS, Targets=[{"Id": q, "Arn": arn}])


def autonomy(reset: bool = False):
    ssm = client("ssm")
    for code, topics in world.autonomy_seed()["auto_send"].items():
        name = f"/mi/autonomy/{code}"
        if reset or not _exists(lambda: ssm.get_parameter(Name=name)):
            value = json.dumps({"enabled": True, "topics": topics})
            ssm.put_parameter(Name=name, Value=value, Type="String", Overwrite=True)


def policy_store() -> str:
    """The Verified Permissions store holding policies/cedar as they are on disk. A changed .cedar file
    gets a new store, so an edited policy is the policy in force after the next provision."""
    ssm, avp = client("ssm"), client("verifiedpermissions")
    files = sorted((world.ROOT / "policies" / "cedar").glob("*.cedar"))
    digest = hashlib.sha256(b"".join(f.name.encode() + f.read_bytes() for f in files)).hexdigest()
    try:
        store, current = ssm.get_parameter(Name="/mi/avp/policy-store")["Parameter"]["Value"].split(":")
        if current == digest:
            return store
    except (ClientError, ValueError):
        pass
    store = avp.create_policy_store(validationSettings={"mode": "OFF"}, description="Medical information")["policyStoreId"]
    for f in files:
        for stmt in _statements(f.read_text()):
            avp.create_policy(policyStoreId=store, definition={"static": {"statement": stmt, "description": f.name}})
    ssm.put_parameter(Name="/mi/avp/policy-store", Value=f"{store}:{digest}", Type="String", Overwrite=True)
    return store


def _statements(text: str) -> list[str]:
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))
    return [s.strip() + ";" for s in body.split(";") if s.strip()]


def users():
    idp, ssm = client("cognito-idp"), client("ssm")
    try:
        pool = ssm.get_parameter(Name="/mi/cognito/pool")["Parameter"]["Value"]
    except ClientError:
        pool = idp.create_user_pool(PoolName=POOL, Schema=[
            {"Name": "role", "AttributeDataType": "String", "Mutable": True},
            {"Name": "country", "AttributeDataType": "String", "Mutable": True},
        ])["UserPool"]["Id"]
        ssm.put_parameter(Name="/mi/cognito/pool", Value=pool, Type="String", Overwrite=True)
    for u in world.people():
        if _exists(lambda: idp.admin_get_user(UserPoolId=pool, Username=u["id"])):
            continue
        idp.admin_create_user(UserPoolId=pool, Username=u["id"], MessageAction="SUPPRESS", UserAttributes=[
            {"Name": "name", "Value": u["name"]},
            {"Name": "custom:role", "Value": u["role"]},
            {"Name": "custom:country", "Value": u["country"]},
        ])


def machine() -> str:
    sfn = client("stepfunctions")
    definition = json.dumps(graph.asl())
    for m in sfn.list_state_machines()["stateMachines"]:
        if m["name"] == MACHINE:
            sfn.update_state_machine(stateMachineArn=m["stateMachineArn"], definition=definition)
            return m["stateMachineArn"]
    role = f"arn:aws:iam::{ACCOUNT}:role/mi-graph"
    return sfn.create_state_machine(name=MACHINE, definition=definition, roleArn=role)["stateMachineArn"]


def logs():
    cw = client("logs")
    if not cw.describe_log_groups(logGroupNamePrefix=LOG_GROUP)["logGroups"]:
        cw.create_log_group(logGroupName=LOG_GROUP)
    if not cw.describe_log_streams(logGroupName=LOG_GROUP, logStreamNamePrefix="cases")["logStreams"]:
        cw.create_log_stream(logGroupName=LOG_GROUP, logStreamName="cases")


def _put_all(table: str, items: list[dict]):
    ddb = client("dynamodb")
    for it in items:
        ddb.put_item(TableName=table, Item={"id": {"S": it["id"]}, "doc": {"S": json.dumps(it, ensure_ascii=False)}})


def _clear(table: str):
    ddb = client("dynamodb")
    pk, sk = TABLES[table]
    for page in ddb.get_paginator("scan").paginate(TableName=table):
        for it in page["Items"]:
            key = {pk: it[pk]} | ({sk: it[sk]} if sk else {})
            ddb.delete_item(TableName=table, Key=key)


def seed(reset: bool = False):
    if reset:
        for t in TABLES:
            _clear(t)
        from hcpagents import ledger
        ledger.new_epoch()
        sqs = client("sqs")
        for q in QUEUES:
            sqs.purge_queue(QueueUrl=sqs.get_queue_url(QueueName=q)["QueueUrl"])
    ddb = client("dynamodb")
    if reset or not ddb.scan(TableName="mi-content", Limit=1)["Items"]:
        _put_all("mi-content", world.blocks())
        _put_all("mi-hcp", world.hcp_world()["hcp"])
        touches = [{"id": f"touch-{i}", "status": "done", **t} for i, t in enumerate(world.hcp_world()["touch"])]
        planned = [{"status": "planned", **p} for p in world.hcp_world()["planned"]]
        _put_all("mi-touches", touches + planned)


def provision(reset: bool = False):
    tables()
    archive()
    signing_key()
    events()
    autonomy(reset)
    policy_store()
    users()
    machine()
    logs()
    seed(reset)


if __name__ == "__main__":
    provision(reset="--reset" in sys.argv)
    print("Provisioned on", client("dynamodb").meta.endpoint_url)
