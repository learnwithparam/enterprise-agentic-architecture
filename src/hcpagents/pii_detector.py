"""Find private details in free text that a list of names cannot catch (concept 37).

Presidio reads the text with a small English model. The model is pinned and comes from a wheel.
Nothing is fetched while the code runs.
It finds a patient name, a birth date and a street address.
In German the model takes plain nouns for names, so it looks for names in English text only.
The date and address patterns work in any language.
The regex floor in `phi_vault` runs first. This adds to it.
"""

import re

from functools import cache

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import SpacyRecognizer

MODEL = "en_core_web_sm"
MIN_SCORE = 0.6
IGNORED = ["QUANTITY", "ORDINAL", "CARDINAL", "MONEY", "PERCENT", "TIME", "DATE", "GPE", "LOC", "FAC", "ORG", "NORP", "PRODUCT",
           "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE"]
KIND_OF = {"PERSON": "NAME", "DOB": "DOB", "ADDRESS": "ADDRESS"}
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
BORN = r"(?:(?:born|dob|d\.o\.b\.|date of birth)[:\s]+(?:on\s+)?)"
DATE = rf"(?:\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{2,4}}|\d{{1,2}} {MONTH} \d{{4}}|{MONTH} \d{{1,2}},? \d{{4}})"
STREET = r"\b\d{1,4} [A-Z][\w.]*(?: [A-Z][\w.]*)? (?:Street|St|Road|Rd|Avenue|Ave|Lane|Strasse|Straße|Platz)\b"


COMMON = {"the", "a", "an", "is", "are", "was", "were", "and", "of", "to", "in", "for", "with", "on", "at", "has",
          "have", "had", "who", "what", "does", "do", "my", "her", "his", "patient", "please", "about", "that", "this"}
ENGLISH_SHARE = 0.12


def _looks_english(text: str) -> bool:
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return False
    return sum(1 for word in words if word in COMMON) / len(words) >= ENGLISH_SHARE


def _own_recognizers() -> list[PatternRecognizer]:
    born = Pattern("born", rf"(?i:{BORN})\b{DATE}", 0.9)
    street = Pattern("street", STREET, 0.8)
    return [PatternRecognizer(supported_entity="DOB", patterns=[born]),
            PatternRecognizer(supported_entity="ADDRESS", patterns=[street])]


@cache
def _engine() -> AnalyzerEngine:
    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": MODEL}],
        "ner_model_configuration": {"labels_to_ignore": IGNORED, "model_to_presidio_entity_mapping": {"PERSON": "PERSON"}}})
    registry = RecognizerRegistry(supported_languages=["en"])
    registry.add_recognizer(SpacyRecognizer(supported_entities=["PERSON"]))
    for recognizer in _own_recognizers():
        registry.add_recognizer(recognizer)
    return AnalyzerEngine(nlp_engine=provider.create_engine(), registry=registry, supported_languages=["en"])


def _start_then_longest(hit) -> tuple[int, int]:
    return hit.start, hit.start - hit.end


def find(text: str) -> list[tuple[int, int, str]]:
    """Each personal value as (start, end, kind). The spans never overlap, and the longest one wins."""
    kinds = list(KIND_OF)
    if not _looks_english(text):
        kinds.remove("PERSON")
    hits = _engine().analyze(text=text, language="en", entities=kinds, score_threshold=MIN_SCORE)
    spans = []
    for hit in sorted(hits, key=_start_then_longest):
        if spans and hit.start < spans[-1][1]:
            continue
        spans.append((hit.start, hit.end, KIND_OF[hit.entity_type]))
    return spans
