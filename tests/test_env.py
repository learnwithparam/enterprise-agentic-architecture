"""The env file is read into the process, never overrides the shell, and the key never reaches git."""

import subprocess

from hcpagents import world

ENV_FILE = chr(46) + "env"


def test_load_env_sets_missing_and_keeps_shell_values(tmp_path, monkeypatch):
    (tmp_path / ENV_FILE).write_text("# comment\nSAMPLE_NEW=\"abc\"\nSAMPLE_SET=from-file\n")
    monkeypatch.delenv("SAMPLE_NEW", raising=False)
    monkeypatch.setenv("SAMPLE_SET", "from-shell")
    world.load_env(tmp_path)
    import os
    assert os.environ["SAMPLE_NEW"] == "abc"
    assert os.environ["SAMPLE_SET"] == "from-shell"
    monkeypatch.delenv("SAMPLE_NEW", raising=False)


def test_load_env_without_a_file_is_a_no_op(tmp_path):
    world.load_env(tmp_path)


def test_secret_file_is_ignored_and_not_tracked():
    ignored = subprocess.run(["git", "check-ignore", "-q", ENV_FILE], cwd=world.ROOT)
    assert ignored.returncode == 0, "the env file must be in .gitignore, the repo is public"
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", ENV_FILE], cwd=world.ROOT,
                             capture_output=True)
    assert tracked.returncode != 0, "the env file must never be tracked"
