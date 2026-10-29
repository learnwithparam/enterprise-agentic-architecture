"""The repository's .claude folder: the model hook refuses what it should, and the files it names exist."""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude/hooks/model_allowlist.py"

spec = importlib.util.spec_from_file_location("model_allowlist", HOOK)
model_allowlist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model_allowlist)


def run_hook(tool_input: dict) -> subprocess.CompletedProcess:
    event = {"tool_name": "Edit", "cwd": str(ROOT), "tool_input": tool_input}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True)


def test_the_hook_blocks_a_model_off_the_allowlist_in_source():
    r = run_hook({"file_path": str(ROOT / "src/hcpagents/agents.py"), "old_string": "x",
                  "new_string": 'MODEL = "claude-opus-5-5"'})
    assert r.returncode == 2
    assert "claude-opus-5-5" in r.stderr


def test_the_hook_blocks_a_dated_model_id_in_a_multi_edit():
    r = run_hook({"file_path": str(ROOT / "web/app/page.jsx"),
                  "edits": [{"old_string": "a", "new_string": "claude-haiku-4-5-20251001"}]})
    assert r.returncode == 2


def test_the_hook_allows_haiku_5_5_and_sonnet_5_5():
    for model in ("claude-haiku-5-5", "claude-sonnet-5-5"):
        r = run_hook({"file_path": str(ROOT / "src/hcpagents/agents.py"), "content": f'MODEL = "{model}"'})
        assert r.returncode == 0, r.stderr


def test_the_hook_allows_other_models_as_examples_in_tests_and_docs():
    for rel in ("tests/test_agents.py", "docs/adr/0003-model.md", "labs/x/test_model_pin.py"):
        r = run_hook({"file_path": str(ROOT / rel), "content": "claude-opus-5-5 is refused"})
        assert r.returncode == 0, rel


def test_settings_wire_the_hook_on_every_file_edit_tool():
    settings = json.loads((ROOT / ".claude/settings.json").read_text())
    (entry,) = settings["hooks"]["PreToolUse"]
    assert set(entry["matcher"].split("|")) == {"Edit", "Write", "MultiEdit"}
    assert entry["hooks"][0]["command"].endswith(".claude/hooks/model_allowlist.py")


def test_every_model_id_in_guarded_code_is_on_the_allowlist():
    seen = 0
    for top in model_allowlist.GUARDED:
        for f in (ROOT / top).rglob("*"):
            if f.is_file() and f.suffix in {".py", ".toml", ".json", ".jsx", ".mjs", ".cedar", ".js"}:
                text = f.read_text(errors="ignore")
                seen += sum(text.count(m) for m in model_allowlist.ALLOWED)
                assert not model_allowlist.offending(text), f
    assert seen > 0


def test_every_file_a_skill_rule_or_subagent_names_exists():
    named = set()
    for md in (ROOT / ".claude").rglob("*.md"):
        named |= set(re.findall(r"`((?:src|world|policies|evals|scripts|tests|\.claude)/[\w./-]+?)`", md.read_text()))
    assert named
    for rel in named:
        rel = rel.rstrip("/").removesuffix("/**")
        assert (ROOT / rel).exists() or (ROOT / (rel.rsplit(".", 1)[0].replace(".", "/") + ".py")).exists(), rel


def test_rules_are_path_scoped():
    for md in (ROOT / ".claude/rules").glob("*.md"):
        head = md.read_text().split("---")[1]
        assert "paths:" in head, md.name
