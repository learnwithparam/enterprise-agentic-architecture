"""The product walkthrough, its captures and the capture script name the same screens, in the same order."""

import re

from hcpagents.world import ROOT

DOC = ROOT / "docs" / "product-walkthrough.md"
SHOTS = ROOT / "docs" / "product-walkthrough-shots"
CAPTURE = ROOT / "web" / "scripts" / "capture.mjs"


def doc_screens() -> list[str]:
    return re.findall(r"product-walkthrough-shots/([a-z0-9-]+)-desktop\.webp", DOC.read_text())


def test_doc_and_capture_list_the_same_screens_in_order():
    captured = re.findall(r"\{ name: '([a-z0-9-]+)'", CAPTURE.read_text())
    assert doc_screens() == captured


def test_every_screen_has_a_shot_and_no_shot_is_orphaned():
    shots = sorted(p.name.removesuffix("-desktop.webp") for p in SHOTS.glob("*.webp"))
    assert shots == sorted(doc_screens())
