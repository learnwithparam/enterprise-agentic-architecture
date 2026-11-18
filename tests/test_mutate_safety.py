"""A mutation run never leaves a mutated file behind: a stray argument runs nothing, a kill puts the file back,
and a leftover mutation stops the next run before it starts (found 18 Nov 2026: a killed run left one in workflows.py)."""

import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mutate  # noqa: E402

FAKE_RUN = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/scripts")
import mutate
mutate.ROOT = Path(sys.argv[2])
sys.argv = sys.argv[:1]
mutate.MUTANTS = [("slow", "target.txt", "good", "bad", [sys.executable, "-c", "import time; time.sleep(60)"])]
sys.exit(mutate.main())
"""


def test_a_help_flag_prints_usage_and_runs_no_mutant():
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "mutate.py"), "--help"], capture_output=True, text=True, timeout=20)
    assert done.returncode == 0 and "usage" in done.stdout and "killed" not in done.stdout


def test_a_leftover_mutation_stops_the_run_and_names_the_file(tmp_path, monkeypatch):
    (tmp_path / "target.txt").write_text("this is bad")
    monkeypatch.setattr(mutate, "ROOT", tmp_path)
    monkeypatch.setattr(mutate, "MUTANTS", [("slow", "target.txt", "good", "bad", ["true"])])
    found = mutate.problems()
    assert len(found) == 1 and "target.txt" in found[0] and "left it" in found[0]


def test_killing_a_run_puts_the_mutated_file_back(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("this is good")
    run = subprocess.Popen([sys.executable, "-c", FAKE_RUN, str(ROOT), str(tmp_path)])
    for _ in range(100):
        if target.read_text() == "this is bad":
            break
        time.sleep(0.1)
    assert target.read_text() == "this is bad"
    run.send_signal(signal.SIGTERM)
    run.wait(timeout=20)
    assert target.read_text() == "this is good"
