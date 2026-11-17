"""The made-up world. It holds the products, the label scope, approved content, doctors, people and the inbox.

All of it comes from world/*.toml and policies/autonomy.toml. These files are the seed.
After setup, the content status lives in DynamoDB. So a withdrawal is a real write.
"""

import os
import tomllib
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env(root: Path = ROOT) -> None:
    """Read the repo's env file into this process only. It is never printed or run by a shell. A variable already set in the shell wins."""
    path = root / (chr(46) + "env")
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env()

# The demo clock. Content expiry is judged by this date, so the demo is the same each time.
TODAY = date.fromisoformat(os.environ.get("MI_TODAY", "2026-10-15"))

ROUTES = ("send", "review", "pv", "offlabel", "specialist", "decline")
TOPICS = (
    "dosing", "administration", "missed_dose", "storage", "renal_impairment",
    "hepatic_impairment", "pregnancy", "interactions", "inhaler_care", "safety_profile", "other",
)
POPULATIONS = ("adult", "adolescent", "child", "elderly", "pregnant", "unspecified")
INDICATIONS = ("plaque_psoriasis", "psoriatic_arthritis", "copd", "other", "unspecified")


def _load(rel: str) -> dict:
    return tomllib.loads((ROOT / rel).read_text())


@cache
def tenants() -> list[dict]:
    return _load("world/tenants.toml")["tenant"]


# The tenant that a request or job acts for. Each tenant has its own company, content, doctors and inbox.
# Quillon is in world/. Every other tenant is in world/tenants/<id>/. People and policy are shared files.
DEFAULT_TENANT = "quillon"
_tenant: ContextVar[str] = ContextVar("tenant", default=DEFAULT_TENANT)


def current_tenant() -> str:
    return _tenant.get()


@contextmanager
def as_tenant(tenant_id: str):
    """Code in this block reads and writes as this tenant."""
    token = _tenant.set(tenant_id)
    try:
        yield
    finally:
        _tenant.reset(token)


@cache
def _tenant_file(tenant: str, name: str) -> dict:
    if tenant not in {known["id"] for known in tenants()}:
        raise KeyError(f"Unknown tenant {tenant!r}")
    if tenant == DEFAULT_TENANT:
        return _load(f"world/{name}.toml")
    return _load(f"world/tenants/{tenant}/{name}.toml")


def products() -> dict:
    return _tenant_file(current_tenant(), "products")


def blocks() -> list[dict]:
    return _tenant_file(current_tenant(), "content")["block"]


def hcp_world() -> dict:
    return _tenant_file(current_tenant(), "hcps")


def inquiries() -> list[dict]:
    return _tenant_file(current_tenant(), "inquiries")["inquiry"]


def agents() -> list[dict]:
    """The agent roster. For each agent: its goal, what it sees, what it does alone, what it proposes, and what it never does."""
    return _load("world/agents.toml")["agent"]


@cache
def directory() -> list[dict]:
    """Everyone who can sign in, in all tenants. Only sign-in and setup read it."""
    return _load("world/people.toml")["user"]


def people() -> list[dict]:
    """The people of the current tenant."""
    return [user for user in directory() if user.get("tenant", DEFAULT_TENANT) == current_tenant()]


@cache
def autonomy_seed() -> dict:
    return _load("policies/autonomy.toml")


def product(code: str) -> dict | None:
    return next((item for item in products()["product"] if item["code"] == code), None)


def country(code: str) -> dict:
    return next(item for item in products()["country"] if item["code"] == code)


def scope(product_code: str, country_code: str) -> dict | None:
    return next(
        (item for item in products()["scope"] if item["product"] == product_code and item["country"] == country_code),
        None,
    )


def hcp(hcp_id: str | None) -> dict | None:
    return next((doctor for doctor in hcp_world()["hcp"] if doctor["id"] == hcp_id), None)


def person(user_id: str) -> dict | None:
    return next((user for user in directory() if user["id"] == user_id), None)


def inquiry(inquiry_id: str) -> dict | None:
    return next((i for i in inquiries() if i["id"] == inquiry_id), None)


def is_current(block: dict, today: date = TODAY) -> bool:
    """Approved, and today inside its approval window."""
    return (
        block["status"] == "approved"
        and date.fromisoformat(block["approved_on"]) <= today <= date.fromisoformat(block["expires_on"])
    )


def why_not_current(block: dict, today: date = TODAY) -> str | None:
    if block["status"] != "approved":
        return f"{block['id']} v{block['version']} is {block['status']}"
    if today > date.fromisoformat(block["expires_on"]):
        return f"{block['id']} v{block['version']} expired on {block['expires_on']}"
    if today < date.fromisoformat(block["approved_on"]):
        return f"{block['id']} v{block['version']} is not effective until {block['approved_on']}"
    return None
