"""The red-team corpus: attacks the rule floor must catch whatever a model says (ADR 0026)."""

import tomllib

from hcpagents import rules, world

CORPUS = world.ROOT / "evals" / "redteam.toml"


def attacks() -> list[dict]:
    return tomllib.loads(CORPUS.read_text())["attack"]


def caught(attack: dict) -> bool:
    screen = rules.injection_screen if attack["expect"] == "injection" else rules.safety_screen
    return bool(screen(attack["text"]))


def misses() -> list[str]:
    """The attacks the floor lets through."""
    return [a["text"] for a in attacks() if not caught(a)]
