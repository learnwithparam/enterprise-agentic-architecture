"""Every permission decision goes to Amazon Verified Permissions, evaluated by Cedar policies in
policies/cedar. The app holds no role checks of its own."""

from functools import cache

from hcpagents.aws import client


@cache
def _store() -> str:
    return client("ssm").get_parameter(Name="/mi/avp/policy-store")["Parameter"]["Value"].split(":")[0]


@cache
def _policy_file(policy_id: str) -> str:
    p = client("verifiedpermissions").get_policy(policyStoreId=_store(), policyId=policy_id)
    return p["definition"]["static"].get("description") or policy_id


def _attrs(d: dict) -> dict:
    return {k: {"string": str(v)} for k, v in d.items() if v is not None}


def allowed(principal_type: str, principal_id: str, principal_attrs: dict, action: str,
            resource_type: str, resource_id: str, resource_attrs: dict, context: dict | None = None) -> tuple[bool, str]:
    req = {
        "policyStoreId": _store(),
        "principal": {"entityType": principal_type, "entityId": principal_id},
        "action": {"actionType": "Action", "actionId": action},
        "resource": {"entityType": resource_type, "entityId": resource_id},
        "entities": {"entityList": [
            {"identifier": {"entityType": principal_type, "entityId": principal_id}, "attributes": _attrs(principal_attrs)},
            {"identifier": {"entityType": resource_type, "entityId": resource_id}, "attributes": _attrs(resource_attrs)},
        ]},
    }
    if context:
        req["context"] = {"contextMap": _attrs(context)}
    res = client("verifiedpermissions").is_authorized(**req)
    ok = res["decision"] == "ALLOW"
    policies = sorted({_policy_file(p["policyId"]) for p in res.get("determiningPolicies", [])})
    return ok, f"Verified Permissions: {res['decision']}" + (f" ({', '.join(policies)})" if policies else "")


def user_can(user: dict, action: str, resource_type: str, resource_id: str, resource_attrs: dict) -> tuple[bool, str]:
    return allowed("User", user["id"], {"role": user["role"], "country": user["country"], "name": user["name"]},
                   action, resource_type, resource_id, resource_attrs)


def agent_can_call(agent: str, tool: str, country: str, product: str, case: dict) -> tuple[bool, str]:
    return allowed("Agent", agent, {"kind": "agent"}, "CallTool", "Tool", tool,
                   {"country": country, "product": product},
                   {"case_country": case["country"], "case_product": case["product"]})
