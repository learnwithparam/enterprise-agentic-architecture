"""Each permission check goes to AWS. It runs our Cedar rules.

The Cedar policy files decide. The app has no role checks of its own.
"""

from functools import cache

from hcpagents import world
from hcpagents.aws import client


@cache
def _store() -> str:
    return client("ssm").get_parameter(Name="/mi/avp/policy-store")["Parameter"]["Value"].split(":")[0]


@cache
def _policy_file(policy_id: str) -> str:
    policy = client("verifiedpermissions").get_policy(policyStoreId=_store(), policyId=policy_id)
    return policy["definition"]["static"].get("description") or policy_id


def _attrs(values: dict) -> dict:
    return {key: {"string": str(value)} for key, value in values.items() if value is not None}


def allowed(principal_type: str, principal_id: str, principal_attrs: dict, action: str,
            resource_type: str, resource_id: str, resource_attrs: dict, context: dict | None = None,
            principal_tenant: str | None = None) -> tuple[bool, str]:
    """Ask Verified Permissions. Both sides carry a tenant. This lets tenants.cedar refuse any mix up.

    The resource has the tenant we serve. The principal has the tenant it signed in under.
    """
    served = world.current_tenant()
    principal_attrs = principal_attrs | {"tenant": principal_tenant or served}
    resource_attrs = resource_attrs | {"tenant": served}
    request = {
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
        request["context"] = {"contextMap": _attrs(context)}
    result = client("verifiedpermissions").is_authorized(**request)
    ok = result["decision"] == "ALLOW"
    policies = sorted({_policy_file(found["policyId"]) for found in result.get("determiningPolicies", [])})
    reason = f"Verified Permissions: {result['decision']}"
    if policies:
        reason += f" ({', '.join(policies)})"
    return ok, reason


def user_can(user: dict, action: str, resource_type: str, resource_id: str, resource_attrs: dict) -> tuple[bool, str]:
    return allowed("User", user["id"], {"role": user["role"], "country": user["country"], "name": user["name"]},
                   action, resource_type, resource_id, resource_attrs, principal_tenant=user.get("tenant", world.DEFAULT_TENANT))


def agent_can_call(agent: str, tool: str, country: str, product: str, case: dict) -> tuple[bool, str]:
    return allowed("Agent", agent, {"kind": "agent"}, "CallTool", "Tool", tool,
                   {"country": country, "product": product},
                   {"case_country": case["country"], "case_product": case["product"]})
