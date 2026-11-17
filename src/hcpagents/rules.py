"""Checks that never use a model: the safety word screen, label scope and the rules for sending alone.
Each one returns its proof, so the case record shows why."""

import re

from hcpagents import world

# One word hit is enough to send a case to drug safety. The safety agent can add hits, never remove them.
# Reporting too much costs a specialist minutes. Reporting too little breaks the law.
AE_PATTERNS = {
    "adverse event": r"\b(rash|fever|swelling|swollen|itch\w*|palpitation\w*|hospitali[sz]\w*|died|death|seizure|anaphyla\w*|reaction|side effect\w*|adverse)\b",
    "special situation": r"\b(pregnan\w*|breast-?feed\w*|overdose|took too many|double dose|medication error|wrong dose)\b",
}
INJECTION = re.compile(
    r"(ignore (all )?(previous|prior) instructions|system administrator|</?\s*(inquiry|system)\s*>|^\s*system\s*:|approval (check|rules?) (is )?disabled|developer mode)",
    re.IGNORECASE | re.MULTILINE,
)


def safety_screen(text: str) -> list[dict]:
    hits = []
    for kind, pattern in AE_PATTERNS.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            hits.append({"kind": kind, "quote": match.group(0), "source": "rule"})
    return hits


def injection_screen(text: str) -> list[str]:
    return [match.group(0) for match in INJECTION.finditer(text)]


def scope_check(product: str, country: str, questions: list[dict]) -> dict:
    """Every question must fit the approved label of the country. One miss makes the case off label."""
    label = world.scope(product, country)
    if label is None:
        return {"in_scope": False, "reasons": [f"{product} has no approved label in {country}"]}
    reasons = []
    for question in questions:
        population = question.get("population", "unspecified")
        indication = question.get("indication", "unspecified")
        if population not in ("unspecified", *label["populations"]):
            reasons.append(f"Population '{population}' is outside the {country} label ({', '.join(label['populations'])})")
        if indication not in ("unspecified", *label["indications"]):
            reasons.append(f"Indication '{indication}' is outside the {country} label ({', '.join(label['indications'])})")
    return {"in_scope": not reasons, "reasons": list(dict.fromkeys(reasons))}


def autonomy_check(country: str, questions: list[dict], enabled: bool, topics: list[str]) -> dict:
    """Send alone only when the switch is on for the country, each topic is cleared, and each patient is an adult.
    Anything else waits for a person."""
    reasons = []
    if not enabled:
        reasons.append(f"Automatic replies are switched off for {country}")
    for question in questions:
        if question["topic"] not in topics:
            reasons.append(f"Topic '{question['topic']}' is not cleared for automatic replies in {country}")
        if question.get("population", "unspecified") not in ("adult", "unspecified"):
            reasons.append(f"Questions about '{question['population']}' patients always need a reviewer")
    return {"auto_allowed": not reasons, "reasons": list(dict.fromkeys(reasons))}
