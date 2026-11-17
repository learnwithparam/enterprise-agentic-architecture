"""The red-team corpus holds attacks that the rule floor must catch, whatever a model says (ADR 0026)."""

import tomllib

from hcpagents import rules, world

CORPUS = world.ROOT / "evals" / "redteam.toml"


def attacks() -> list[dict]:
    return tomllib.loads(CORPUS.read_text())["attack"]


def caught(attack: dict) -> bool:
    screen = rules.safety_screen
    if attack["expect"] == "injection":
        screen = rules.injection_screen
    return bool(screen(attack["text"]))


def misses() -> list[str]:
    """The attacks that the floor lets through."""
    return [attack["text"] for attack in attacks() if not caught(attack)]
