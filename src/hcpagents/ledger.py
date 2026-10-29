"""The audit ledger: an append-only hash chain that Compliance can check without trusting us.

Every entry carries the hash of the one before it. Each entry is also written to an S3 bucket
under Object Lock in COMPLIANCE mode, which nobody can delete for ten years, and the chain head is
signed with a KMS key at each checkpoint. Editing a row in DynamoDB breaks the chain at that row;
deleting the archived copy is refused by S3. Each tenant has its own chain, and personal data in an entry
is sealed under a per-person key (privacy.py), so erasing a person never touches the chain.
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


def _rows() -> list[dict]:
    ddb = client("dynamodb")
    rows, kw = [], {"TableName": TABLE, "KeyConditionExpression": "chain = :c",
                    "ExpressionAttributeValues": {":c": {"S": _chain()}}, "ConsistentRead": True}
    while True:
        page = ddb.query(**kw)
        rows += [{"seq": int(i["seq"]["N"]), "hash": i["hash"]["S"], "prev": i["prev"]["S"],
                  "entry": json.loads(i["entry"]["S"]), "signature": i.get("signature", {}).get("S")}
                 for i in page["Items"]]
        if "LastEvaluatedKey" not in page:
            return rows
        kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def entries(case_id: str | None = None, reveal: bool = False) -> list[dict]:
    """This tenant's rows. Sealed personal data stays sealed unless the caller is allowed to open it."""
    rows = [r for r in _rows() if case_id is None or r["entry"].get("case") == case_id]
    return [r | {"entry": privacy.reveal(r["entry"])} for r in rows] if reveal else rows


def append(entry: dict, subject: str | None = None, private: dict | None = None) -> dict:
    """Append with an optimistic lock on the sequence number, so two writers cannot fork the chain.

    `private` is personal data about `subject`; it is written sealed, never as text."""
    ddb, epoch = client("dynamodb"), _chain()
    entry = {"at": datetime.now(UTC).isoformat(timespec="milliseconds"), **entry}
    if private is not None:
        entry |= privacy.seal(subject, private)
    for _ in range(5):
        last = ddb.query(TableName=TABLE, KeyConditionExpression="chain = :c", ScanIndexForward=False, Limit=1,
                         ExpressionAttributeValues={":c": {"S": epoch}}, ConsistentRead=True)["Items"]
        seq = int(last[0]["seq"]["N"]) + 1 if last else 1
        prev = last[0]["hash"]["S"] if last else GENESIS
        h = digest(prev, entry)
        item = {"chain": {"S": epoch}, "seq": {"N": str(seq)}, "hash": {"S": h}, "prev": {"S": prev},
                "entry": {"S": json.dumps(entry, ensure_ascii=False)}}
        if seq % CHECKPOINT_EVERY == 0:
            item["signature"] = {"S": _sign(h)}
        try:
            ddb.put_item(TableName=TABLE, Item=item, ConditionExpression="attribute_not_exists(seq)")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                continue
            raise
        client("s3").put_object(Bucket=ARCHIVE, Key=_archive_key(epoch, seq),
                                Body=json.dumps({"seq": seq, "hash": h, "prev": prev, "entry": entry}).encode())
        return {"seq": seq, "hash": h}
    raise RuntimeError("ledger append lost the race five times")


def _sign(h: str) -> str:
    sig = client("kms").sign(KeyId=KEY_ALIAS, Message=h.encode(), SigningAlgorithm="ECDSA_SHA_256")["Signature"]
    return sig.hex()


def _signature_ok(h: str, sig_hex: str) -> bool:
    kms = client("kms")
    try:
        return kms.verify(KeyId=KEY_ALIAS, Message=h.encode(), Signature=bytes.fromhex(sig_hex),
                          SigningAlgorithm="ECDSA_SHA_256")["SignatureValid"]
    except kms.exceptions.KMSInvalidSignatureException:
        return False


def verify() -> dict:
    """Recompute every hash and check every signed checkpoint. Returns the first break, if any."""
    rows = _rows()
    prev, checkpoints = GENESIS, 0
    for r in rows:
        if r["prev"] != prev or digest(prev, r["entry"]) != r["hash"]:
            return {"ok": False, "entries": len(rows), "broken_at": r["seq"],
                    "reason": f"Entry {r['seq']} does not match its hash. It was changed after it was written."}
        if r["signature"]:
            if not _signature_ok(r["hash"], r["signature"]):
                return {"ok": False, "entries": len(rows), "broken_at": r["seq"], "reason": f"Checkpoint {r['seq']} signature is invalid."}
            checkpoints += 1
        prev = r["hash"]
    return {"ok": True, "entries": len(rows), "checkpoints": checkpoints, "head": prev}


def tamper(seq: int, field: str = "route", value: str = "send") -> dict:
    """Demo: rewrite one stored entry the way an insider with table access would."""
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
    """Undo a demo tamper from the locked archive copy, which is the record of truth."""
    epoch = _chain()
    body = json.loads(client("s3").get_object(Bucket=ARCHIVE, Key=_archive_key(epoch, seq))["Body"].read())
    client("dynamodb").update_item(
        TableName=TABLE, Key={"chain": {"S": epoch}, "seq": {"N": str(seq)}}, UpdateExpression="SET #e = :e",
        ExpressionAttributeNames={"#e": "entry"},
        ExpressionAttributeValues={":e": {"S": json.dumps(body["entry"], ensure_ascii=False)}})


def try_delete_archive(seq: int) -> dict:
    """Demo: try to destroy the archived copy of an entry. Object Lock refuses."""
    s3, key = client("s3"), _archive_key(_chain(), seq)
    version = s3.head_object(Bucket=ARCHIVE, Key=key)["VersionId"]
    try:
        s3.delete_object(Bucket=ARCHIVE, Key=key, VersionId=version)
        return {"deleted": True, "key": key}
    except ClientError as e:
        return {"deleted": False, "key": key, "error": e.response["Error"]["Code"], "message": e.response["Error"].get("Message", "")}


def erase_subject(subject: str, by: str) -> dict:
    """Erase one person: delete their key, then record that it happened (the record names no one)."""
    pid = privacy.pseudonym(subject)
    found = privacy.erase(subject)
    append({"type": "erased", "subject": pid, "by": by, "had_data": found})
    return {"subject": pid, "erased": found}
