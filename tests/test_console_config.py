"""The sign-in screen asks the server how to sign in, and the page policy lets it reach Cognito."""
from pathlib import Path

from fastapi.testclient import TestClient

from hcpagents import api, aws


def test_the_sign_in_screen_can_read_the_config_without_a_token():
    answer = TestClient(api.app).get("/api/config")
    assert answer.status_code == 200
    assert answer.json()["mode"] == "local"
    assert answer.json()["pool_id"] is None


def test_the_page_policy_allows_cognito_only_outside_a_local_run(monkeypatch, tmp_path):
    page = tmp_path / "index.html"
    page.write_text("<html></html>")
    assert "cognito-idp" not in api.content_security_policy(page)
    monkeypatch.setattr(aws, "is_local", lambda: False)
    policy = api.content_security_policy(page)
    assert f"connect-src 'self' https://cognito-idp.{aws.REGION}.amazonaws.com;" in policy
