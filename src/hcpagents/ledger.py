"""The audit ledger: a hash chain that you can only add to. Compliance can check it without trusting us.

Every entry holds the hash of the one before it. Each entry is also copied to an S3 bucket.
The bucket uses Object Lock in COMPLIANCE mode, so nobody can delete a copy for ten years.
At each checkpoint the head of the chain is signed with a KMS key.

Editing a row in DynamoDB breaks the chain at that row. S3 refuses to delete the archived copy.
Each tenant has its own chain. Personal data is sealed under a key for each person (privacy.py).
So erasing a person never touches the chain.
"""

import hashlib
import json
from datetime import UTC, datetime

from botocore.exceptions import ClientError

from hcpagents import privacy, world
from hcpagents.aws import client
from hcpagents.infra import ARCHIVE, KEY_ALIAS

TABLE = "mi-ledger"
GENESIS = "0" * 64
CHECKPOINT_EVERY = 10


def _epoch() -> str:
    try:
        return client("ssm").get_parameter(Name="/mi/ledger/epoch")["Parameter"]["Value"]
    except ClientError:
        return new_epoch()


def new_epoch() -> str:
    """A reset starts a new chain. Locked archive objects from older chains stay where they are."""
    epoch = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    client("ssm").put_parameter(Name="/mi/ledger/epoch", Value=epoch, Type="String", Overwrite=True)
    return epoch


def _chain() -> str:
    return f"{_epoch()}#{world.current_tenant()}"


def _archive_key(chain: str, seq: int) -> str:
    return f"ledger/{chain.replace('#', '/')}/{seq:08d}.json"


def digest(prev: str, entry: dict) -> str:
    return hashlib.sha256((prev + json.dumps(entry, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()


def _row_from(item: dict) -> dict:
    return {"seq": int(item["seq"]["N"]), "hash": item["hash"]["S"], "prev": item["prev"]["S"],
            "entry": json.loads(item["entry"]["S"]), "signature": item.get("signature", {}).get("S")}


def _rows() -> list[dict]:
    ddb = client("dynamodb")
    rows, query = [], {"TableName": TABLE, "KeyConditionExpression": "chain = :c",
                       "ExpressionAttributeValues": {":c": {"S": _chain()}}, "ConsistentRead": True}
    while True:
        page = ddb.query(**query)
        rows += [_row_from(item) for item in page["Items"]]
        if "LastEvaluatedKey" not in page:
            return rows
        query["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def entries(case_id: str | None = None, reveal: bool = False) -> list[dict]:
    """This tenant's rows. Sealed data stays sealed unless the caller may open it."""
    rows = [row for row in _rows() if case_id is None or row["entry"].get("case") == case_id]
    if not reveal:
        return rows
    return [row | {"entry": privacy.reveal(row["entry"])} for row in rows]


def _last_row(ddb, chain: str) -> tuple[int, str]:
    last = ddb.query(TableName=TABLE, KeyConditionExpression="chain = :c", ScanIndexForward=False, Limit=1,
                     ExpressionAttributeValues={":c": {"S": chain}}, ConsistentRead=True)["Items"]
    if not last:
        return 1, GENESIS
    return int(last[0]["seq"]["N"]) + 1, last[0]["hash"]["S"]


def append(entry: dict, subject: str | None = None, private: dict | None = None) -> dict:
    """Add an entry. A lock on the sequence number stops two writers from forking the chain.

    The private data is about the subject. It is written sealed, never as text.
    """
    ddb, epoch = client("dynamodb"), _chain()
    entry = {"at": datetime.now(UTC).isoformat(timespec="milliseconds"), **entry}
    if private is not None:
        entry |= privacy.seal(subject, private)
    for _ in range(5):
        seq, prev = _last_row(ddb, epoch)
        entry_hash = digest(prev, entry)
        item = {"chain": {"S": epoch}, "seq": {"N": str(seq)}, "hash": {"S": entry_hash}, "prev": {"S": prev},
                "entry": {"S": json.dumps(entry, ensure_ascii=False)}}
        if seq % CHECKPOINT_EVERY == 0:
            item["signature"] = {"S": _sign(entry_hash)}
        try:
            ddb.put_item(TableName=TABLE, Item=item, ConditionExpression="attribute_not_exists(seq)")
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                continue
            raise
        client("s3").put_object(Bucket=ARCHIVE, Key=_archive_key(epoch, seq),
                                Body=json.dumps({"seq": seq, "hash": entry_hash, "prev": prev, "entry": entry}).encode())
        return {"seq": seq, "hash": entry_hash}
    raise RuntimeError("ledger append lost the race five times")


def _sign(entry_hash: str) -> str:
    signed = client("kms").sign(KeyId=KEY_ALIAS, Message=entry_hash.encode(), SigningAlgorithm="ECDSA_SHA_256")
    return signed["Signature"].hex()


def _signature_ok(entry_hash: str, signature_hex: str) -> bool:
    kms = client("kms")
    try:
        return kms.verify(KeyId=KEY_ALIAS, Message=entry_hash.encode(), Signature=bytes.fromhex(signature_hex),
                          SigningAlgorithm="ECDSA_SHA_256")["SignatureValid"]
    except kms.exceptions.KMSInvalidSignatureException:
        return False


def verify() -> dict:
    """Redo each hash and check each signed checkpoint. Gives back the first break, if any."""
    rows = _rows()
    prev, checkpoints = GENESIS, 0
    for row in rows:
        if row["prev"] != prev or digest(prev, row["entry"]) != row["hash"]:
            return {"ok": False, "entries": len(rows), "broken_at": row["seq"],
                    "reason": f"Entry {row['seq']} does not match its hash. It was changed after it was written."}
        if row["signature"]:
            if not _signature_ok(row["hash"], row["signature"]):
                return {"ok": False, "entries": len(rows), "broken_at": row["seq"],
                        "reason": f"Checkpoint {row['seq']} signature is invalid."}
            checkpoints += 1
        prev = row["hash"]
    return {"ok": True, "entries": len(rows), "checkpoints": checkpoints, "head": prev}


def tamper(seq: int, field: str = "route", value: str = "send") -> dict:
    """Demo: change one stored entry, as someone with table access could."""
    ddb, epoch = client("dynamodb"), _chain()
    key = {"chain": {"S": epoch}, "seq": {"N": str(seq)}}
    item = ddb.get_item(TableName=TABLE, Key=key)["Item"]
    entry = json.loads(item["entry"]["S"])
    before = entry.get(field)
    entry[field] = value
    ddb.update_item(TableName=TABLE, Key=key, UpdateExpression="SET #e = :e",
                    ExpressionAttributeNames={"#e": "entry"}, ExpressionAttributeValues={":e": {"S": json.dumps(entry)}})
    return {"seq": seq, "field": field, "before": before, "after": value}


def restore(seq: int) -> None:
    """Undo the demo change by using the locked archive copy. It is the true record."""
    epoch = _chain()
    body = json.loads(client("s3").get_object(Bucket=ARCHIVE, Key=_archive_key(epoch, seq))["Body"].read())
    client("dynamodb").update_item(
        TableName=TABLE, Key={"chain": {"S": epoch}, "seq": {"N": str(seq)}}, UpdateExpression="SET #e = :e",
        ExpressionAttributeNames={"#e": "entry"},
        ExpressionAttributeValues={":e": {"S": json.dumps(body["entry"], ensure_ascii=False)}})


def try_delete_archive(seq: int) -> dict:
    """Demo: try to destroy the archived copy of an entry. Object Lock says no."""
    s3, key = client("s3"), _archive_key(_chain(), seq)
    version = s3.head_object(Bucket=ARCHIVE, Key=key)["VersionId"]
    try:
        s3.delete_object(Bucket=ARCHIVE, Key=key, VersionId=version)
        return {"deleted": True, "key": key}
    except ClientError as error:
        return {"deleted": False, "key": key, "error": error.response["Error"]["Code"],
                "message": error.response["Error"].get("Message", "")}


def erase_subject(subject: str, author: str) -> dict:
    """Erase one person: delete their key, then record that it happened. The record names no one."""
    pseudonym = privacy.pseudonym(subject)
    found = privacy.erase(subject)
    append({"type": "erased", "subject": pseudonym, "by": author, "had_data": found})
    return {"subject": pseudonym, "erased": found}
