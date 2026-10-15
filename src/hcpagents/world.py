"""The synthetic world: products, label scope, approved content, HCPs, people and the inbox.

Everything here is read from world/*.toml and policies/autonomy.toml. The TOML files are the
seed; once provisioned, content status lives in DynamoDB so a withdrawal is a real write.
"""

import os
import tomllib
from datetime import date
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The demo clock. Content expiry is judged against this date so the demo is repeatable.
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
def products() -> dict:
    return _load("world/products.toml")


@cache
def blocks() -> list[dict]:
    return _load("world/content.toml")["block"]


@cache
def hcp_world() -> dict:
    return _load("world/hcps.toml")


@cache
def inquiries() -> list[dict]:
    return _load("world/inquiries.toml")["inquiry"]


@cache
def people() -> list[dict]:
    return _load("world/people.toml")["user"]


@cache
def autonomy_seed() -> dict:
    return _load("policies/autonomy.toml")


def product(code: str) -> dict | None:
    return next((p for p in products()["product"] if p["code"] == code), None)


def country(code: str) -> dict:
    return next(c for c in products()["country"] if c["code"] == code)


def scope(product_code: str, country_code: str) -> dict | None:
    return next(
        (s for s in products()["scope"] if s["product"] == product_code and s["country"] == country_code),
        None,
    )


def hcp(hcp_id: str | None) -> dict | None:
    return next((h for h in hcp_world()["hcp"] if h["id"] == hcp_id), None)


def person(user_id: str) -> dict | None:
    return next((u for u in people() if u["id"] == user_id), None)


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
