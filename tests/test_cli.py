"""hcp is a thin client of /v1: it keeps a private token and prints what the API returns (ADR 0028)."""

import asyncio
import stat

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hcpagents import api, auth, cases, cli, infra

pytestmark = pytest.mark.floci

runner = CliRunner()


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    infra.provision(reset=True)
    monkeypatch.setenv("HCP_CONFIG", str(tmp_path))
    monkeypatch.setenv("HCP_PASSWORD", auth.DEMO_PASSWORD)
    monkeypatch.setattr(cli.httpx, "post", lambda url, **kw: TestClient(api.app).post(url.removeprefix(cli.URL), json=kw["json"]))
    monkeypatch.setattr(cli, "client", lambda: TestClient(api.app, headers={"Authorization": f"Bearer {cli.token_file().read_text()}"}))


def test_login_keeps_the_token_private_and_commands_use_it():
    assert runner.invoke(cli.app, ["login", "--user", "u-brandt"]).exit_code == 0
    mode = stat.S_IMODE(cli.token_file().stat().st_mode)
    assert mode == 0o600
    asyncio.run(cases.run("inq-101"))
    out = runner.invoke(cli.app, ["cases"]).output
    assert "inq-101" in out and "sent" in out


def test_a_wrong_password_is_refused_and_saves_nothing(monkeypatch):
    monkeypatch.setenv("HCP_PASSWORD", "wrong")
    r = runner.invoke(cli.app, ["login", "--user", "u-brandt"])
    assert r.exit_code == 1 and not cli.token_file().exists()


def test_the_api_refusal_reaches_the_terminal():
    assert runner.invoke(cli.app, ["login", "--user", "u-brandt"]).exit_code == 0
    r = runner.invoke(cli.app, ["release-promote", "r-none"])
    assert r.exit_code == 1 and "403" in r.output + r.stderr
