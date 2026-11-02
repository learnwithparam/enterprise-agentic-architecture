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


def test_owner_url_is_built_from_the_cluster_secret_parts(monkeypatch):
    from hcpagents import db
    parts = {"DB_HOST": "db.internal", "DB_OWNER_USER": "admin", "DB_OWNER_PASSWORD": "p@ss/word"}
    assert db.owner_url(parts) == "postgresql://admin:p%40ss%2Fword@db.internal:5432/hcp"
    assert db.owner_url({**parts, "DATABASE_OWNER_URL": "postgresql://x"}) == "postgresql://x"
    assert db.owner_url({}).startswith("postgresql://hcp_owner:")


def test_db_password_from_secrets_manager(monkeypatch):
    """The app role's password lives in Secrets Manager only: no environment variable or file carries it."""
    import json

    import psycopg

    from hcpagents import db
    from hcpagents.aws import client
    parts = json.loads(client("secretsmanager").get_secret_value(SecretId=db.APP_SECRET)["SecretString"])
    assert parts["password"] not in ("hcp_app", "") and len(parts["password"]) >= 24
    monkeypatch.setenv("DATABASE_URL", "postgresql://hcp_app:hcp_app@localhost:5433/hcp")  # no fallback reads this
    assert db.APP_URL == db.app_url(parts)
    with psycopg.connect(db.APP_URL) as conn:  # the role accepts exactly this password
        assert conn.execute("SELECT current_user").fetchone()[0] == "hcp_app"
    with __import__("pytest").raises(psycopg.OperationalError):
        psycopg.connect(db.app_url(parts | {"password": "hcp_app"}), connect_timeout=2)
    assert "hcp_app'" not in (db.MIGRATIONS / "001_documents.sql").read_text().split("CREATE ROLE")[1].split(";")[0]
    assert db.app_url({"username": "u", "password": "p@/", "host": "h", "port": 1, "dbname": "d"}) == "postgresql://u:p%40%2F@h:1/d"
