"""Make every AWS resource the platform needs, on Floci, then seed the world.

Run it with python -m hcpagents.infra, and it is safe to rerun. Add --reset to wipe state and reseed.
The locked archive stays.
"""

import contextlib
import hashlib
import json
import sys

from botocore.exceptions import ClientError

from hcpagents import auth, cache, db, graph, ingest, retrieval, store, world
from hcpagents.aws import REGION, client

TABLES = {"mi-ledger": ("chain", "seq")}  # everything else lives in Postgres (db.py)
ARCHIVE = "mi-ledger-archive"
BUS = "mi-events"
QUEUES = {"mi-pv-intake": "SafetySignal", "mi-medical-review": "ReviewNeeded", "mi-content-invalidation": "ContentWithdrawn",
          "mi-interactions": "InteractionReceived"}
KEY_ALIAS = "alias/mi-ledger"
MACHINE = "mi-inquiry-graph"
LOG_GROUP = "/mi/agents"
POOL = "mi-users"
ACCOUNT = "000000000000"


def _exists(call, **arguments) -> bool:
    try:
        call(**arguments)
        return True
    except ClientError:
        return False


def tables():
    ddb = client("dynamodb")
    have = set(ddb.list_tables()["TableNames"])
    for name, (hash_key, range_key) in TABLES.items():
        if name in have:
            continue
        keys = [{"AttributeName": hash_key, "KeyType": "HASH"}]
        attrs = [{"AttributeName": hash_key, "AttributeType": "S"}]
        if range_key:
            keys.append({"AttributeName": range_key, "KeyType": "RANGE"})
            attrs.append({"AttributeName": range_key, "AttributeType": "N"})
        ddb.create_table(TableName=name, KeySchema=keys, AttributeDefinitions=attrs, BillingMode="PAY_PER_REQUEST")


def archive():
    s3 = client("s3")
    if _exists(s3.head_bucket, Bucket=ARCHIVE):
        return
    s3.create_bucket(Bucket=ARCHIVE, ObjectLockEnabledForBucket=True,
                     CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object_lock_configuration(Bucket=ARCHIVE, ObjectLockConfiguration={
        "ObjectLockEnabled": "Enabled",
        "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Years": 10}},
    })


def signing_key() -> str:
    kms = client("kms")
    for alias in kms.list_aliases()["Aliases"]:
        if alias["AliasName"] == KEY_ALIAS and alias.get("TargetKeyId"):
            return alias["TargetKeyId"]
    key = kms.create_key(KeyUsage="SIGN_VERIFY", KeySpec="ECC_NIST_P256", Description="Ledger checkpoints")
    key_id = key["KeyMetadata"]["KeyId"]
    kms.create_alias(AliasName=KEY_ALIAS, TargetKeyId=key_id)
    return key_id


def events():
    bus, sqs = client("events"), client("sqs")
    if not _exists(bus.describe_event_bus, Name=BUS):
        bus.create_event_bus(Name=BUS)
    for queue, detail_type in QUEUES.items():
        url = sqs.create_queue(QueueName=queue)["QueueUrl"]
        arn = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        rule = f"to-{queue}"
        bus.put_rule(Name=rule, EventBusName=BUS, EventPattern=json.dumps({"detail-type": [detail_type]}))
        bus.put_targets(Rule=rule, EventBusName=BUS, Targets=[{"Id": queue, "Arn": arn}])


def autonomy(reset: bool = False):
    """Each tenant starts with the seeded countries on. A switch you changed stays as it is."""
    from hcpagents import cases
    for tenant in world.tenants():
        with world.as_tenant(tenant["id"]):
            for code, topics in world.autonomy_seed()["auto_send"].items():
                try:
                    present = bool(cases.autonomy_setting(code))
                except KeyError:
                    present = False
                if reset or not present:
                    cases.save_autonomy(code, {"enabled": True, "topics": topics})


def policy_store() -> str:
    """The policy store that holds policies/cedar as they are on disk. A changed file gets a new store."""
    ssm, avp = client("ssm"), client("verifiedpermissions")
    files = sorted((world.ROOT / "policies" / "cedar").glob("*.cedar"))
    digest = hashlib.sha256(b"".join(file.name.encode() + file.read_bytes() for file in files)).hexdigest()
    try:
        store, current = ssm.get_parameter(Name="/mi/avp/policy-store")["Parameter"]["Value"].split(":")
        if current == digest:
            return store
    except (ClientError, ValueError):
        pass
    store = avp.create_policy_store(validationSettings={"mode": "OFF"}, description="Medical information")["policyStoreId"]
    for file in files:
        for statement in _statements(file.read_text()):
            avp.create_policy(policyStoreId=store, definition={
                "static": {"statement": statement, "description": file.name}})
    ssm.put_parameter(Name="/mi/avp/policy-store", Value=f"{store}:{digest}", Type="String", Overwrite=True)
    return store


def _statements(text: str) -> list[str]:
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))
    return [piece.strip() + ";" for piece in body.split(";") if piece.strip()]


def users():
    idp, ssm = client("cognito-idp"), client("ssm")
    try:
        pool = ssm.get_parameter(Name="/mi/cognito/pool")["Parameter"]["Value"]
    except ClientError:
        pool = idp.create_user_pool(PoolName=POOL, Schema=[
            {"Name": "role", "AttributeDataType": "String", "Mutable": True},
            {"Name": "country", "AttributeDataType": "String", "Mutable": True},
            {"Name": "tenant", "AttributeDataType": "String", "Mutable": True},
        ])["UserPool"]["Id"]
        ssm.put_parameter(Name="/mi/cognito/pool", Value=pool, Type="String", Overwrite=True)
    try:
        client_id = ssm.get_parameter(Name="/mi/cognito/client")["Parameter"]["Value"]
    except ClientError:
        client_id = idp.create_user_pool_client(UserPoolId=pool, ClientName="mi-console", GenerateSecret=False,
            ExplicitAuthFlows=["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"])["UserPoolClient"]["ClientId"]
        ssm.put_parameter(Name="/mi/cognito/client", Value=client_id, Type="String", Overwrite=True)
    try:
        client_id_cli = ssm.get_parameter(Name="/mi/cognito/cli-client")["Parameter"]["Value"]
    except ClientError:
        client_id_cli = idp.create_user_pool_client(
            UserPoolId=pool, ClientName="mi-cli", GenerateSecret=False, ExplicitAuthFlows=["ALLOW_REFRESH_TOKEN_AUTH"],
            AllowedOAuthFlows=["code"], AllowedOAuthFlowsUserPoolClient=True, AllowedOAuthScopes=["openid"],
            CallbackURLs=[auth.CLI_REDIRECT], SupportedIdentityProviders=["COGNITO"])["UserPoolClient"]["ClientId"]
        ssm.put_parameter(Name="/mi/cognito/cli-client", Value=client_id_cli, Type="String", Overwrite=True)
    with contextlib.suppress(ClientError):  # an old pool gets the tenant attribute once
        idp.add_custom_attributes(UserPoolId=pool, CustomAttributes=[{"Name": "tenant", "AttributeDataType": "String", "Mutable": True}])
    for user in world.directory():
        if not _exists(idp.admin_get_user, UserPoolId=pool, Username=user["id"]):
            _create_user(idp, pool, user)
        idp.admin_update_user_attributes(UserPoolId=pool, Username=user["id"], UserAttributes=[
            {"Name": "custom:tenant", "Value": user.get("tenant", world.DEFAULT_TENANT)}])
        idp.admin_set_user_password(UserPoolId=pool, Username=user["id"], Password=auth.DEMO_PASSWORD, Permanent=True)


def _create_user(idp, pool: str, user: dict):
    idp.admin_create_user(UserPoolId=pool, Username=user["id"], MessageAction="SUPPRESS", UserAttributes=[
        {"Name": "name", "Value": user["name"]},
        {"Name": "custom:role", "Value": user["role"]},
        {"Name": "custom:country", "Value": user["country"]},
        {"Name": "custom:tenant", "Value": user.get("tenant", world.DEFAULT_TENANT)},
    ])


def machine() -> str:
    sfn = client("stepfunctions")
    definition = json.dumps(graph.asl())
    for existing in sfn.list_state_machines()["stateMachines"]:
        if existing["name"] == MACHINE:
            sfn.update_state_machine(stateMachineArn=existing["stateMachineArn"], definition=definition)
            return existing["stateMachineArn"]
    role = f"arn:aws:iam::{ACCOUNT}:role/mi-graph"
    return sfn.create_state_machine(name=MACHINE, definition=definition, roleArn=role)["stateMachineArn"]


def logs():
    watch = client("logs")
    if not watch.describe_log_groups(logGroupNamePrefix=LOG_GROUP)["logGroups"]:
        watch.create_log_group(logGroupName=LOG_GROUP)
    if not watch.describe_log_streams(logGroupName=LOG_GROUP, logStreamNamePrefix="cases")["logStreams"]:
        watch.create_log_stream(logGroupName=LOG_GROUP, logStreamName="cases")


def _clear(table: str):
    ddb = client("dynamodb")
    hash_key, range_key = TABLES[table]
    for page in ddb.get_paginator("scan").paginate(TableName=table):
        for item in page["Items"]:
            key = {hash_key: item[hash_key]}
            if range_key:
                key = key | {range_key: item[range_key]}
            ddb.delete_item(TableName=table, Key=key)


def seed(reset: bool = False):
    if reset:
        for table in TABLES:
            _clear(table)
        db.wipe()
        from hcpagents import ledger
        ledger.new_epoch()
        sqs = client("sqs")
        for queue in QUEUES:
            sqs.purge_queue(QueueUrl=sqs.get_queue_url(QueueName=queue)["QueueUrl"])
    for tenant in world.tenants():
        with world.as_tenant(tenant["id"]):
            _seed_tenant(reset)


def _seed_tenant(reset: bool):
    if reset or not store.scan("mi-content"):
        for table, docs in (("mi-content", world.blocks()), ("mi-hcp", world.hcp_world()["hcp"])):
            for doc in docs:
                store.put(table, doc)
        touches = [{"id": f"touch-{i}", "status": "done", **touch}
                   for i, touch in enumerate(world.hcp_world().get("touch", []))]
        planned = [{"status": "planned", **plan} for plan in world.hcp_world().get("planned", [])]
        for touch in touches + planned:
            store.put("mi-touches", touch)
        retrieval.index()


def provision(reset: bool = False):
    db.migrate()
    tables()
    archive()
    ingest.landing()
    signing_key()
    events()
    autonomy(reset)
    policy_store()
    users()
    machine()
    logs()
    seed(reset)
    if reset:
        cache.flush_tenant("*")  # a reset reseeds each tenant, so old answers are stale


if __name__ == "__main__":
    provision(reset="--reset" in sys.argv)
    print("Provisioned on", client("dynamodb").meta.endpoint_url)
