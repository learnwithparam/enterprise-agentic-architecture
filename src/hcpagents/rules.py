"""Deterministic checks that never depend on a model: the safety keyword screen, label scope,
and the autonomy policy. Each returns its evidence so the case record shows why."""

import re

from hcpagents import world

# A keyword hit is enough to send a case to pharmacovigilance; the safety agent can add hits,
# never remove them. Over-reporting costs a PV specialist minutes; under-reporting is a breach.
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
        for m in re.finditer(pattern, text, re.IGNORECASE):
            hits.append({"kind": kind, "quote": m.group(0), "source": "rule"})
    return hits


def injection_screen(text: str) -> list[str]:
    return [m.group(0) for m in INJECTION.finditer(text)]


def scope_check(product: str, country: str, questions: list[dict]) -> dict:
    """Every question must be inside the country's approved label. One miss and the case is off-label."""
    s = world.scope(product, country)
    if s is None:
        return {"in_scope": False, "reasons": [f"{product} has no approved label in {country}"]}
    reasons = []
    for q in questions:
        pop, ind = q.get("population", "unspecified"), q.get("indication", "unspecified")
        if pop not in ("unspecified", *s["populations"]):
            reasons.append(f"Population '{pop}' is outside the {country} label ({', '.join(s['populations'])})")
        if ind not in ("unspecified", *s["indications"]):
            reasons.append(f"Indication '{ind}' is outside the {country} label ({', '.join(s['indications'])})")
    return {"in_scope": not reasons, "reasons": list(dict.fromkeys(reasons))}


def autonomy_check(country: str, questions: list[dict], enabled: bool, topics: list[str]) -> dict:
    """Auto-send only when the country switch is on, every topic is cleared, and every question is
    about an adult or an unspecified population. Anything else waits for a human."""
    reasons = []
    if not enabled:
        reasons.append(f"Automatic replies are switched off for {country}")
    for q in questions:
        if q["topic"] not in topics:
            reasons.append(f"Topic '{q['topic']}' is not cleared for automatic replies in {country}")
        if q.get("population", "unspecified") not in ("adult", "unspecified"):
            reasons.append(f"Questions about '{q['population']}' patients always need a reviewer")
    return {"auto_allowed": not reasons, "reasons": list(dict.fromkeys(reasons))}
