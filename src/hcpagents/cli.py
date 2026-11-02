"""hcp: the platform from a terminal, over the same /v1 API any other client uses (ADR 0028).

    hcp login                       sign in in the browser (code flow with PKCE); the token is kept in ~/.config/hcp/token (owner only)
    hcp cases | case <id> | watch <id>
    hcp dlq | dlq-replay <id>
    hcp releases | release-diff <a> <b> | release-promote <release>
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
import typer

from hcpagents import auth

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
URL = os.environ.get("HCP_URL", "http://localhost:8765")


def token_file() -> Path:
    return Path(os.environ.get("HCP_CONFIG", Path.home() / ".config" / "hcp")) / "token"


def client() -> httpx.Client:
    """An HTTP client carrying the saved token. Tests replace this with one bound to the app."""
    f = token_file()
    if not f.exists():
        raise typer.Exit(typer.echo("Not signed in. Run: hcp login", err=True) or 1)
    return httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {f.read_text().strip()}"}, timeout=30)


def show(r: httpx.Response):
    if r.status_code >= 400:
        typer.echo(f"{r.status_code}: {r.json().get('detail', r.text)}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))


def pkce_pair() -> tuple[str, str]:
    """A one-use secret and its SHA-256 challenge. The identity provider sees only the challenge until the code is redeemed."""
    verifier = secrets.token_urlsafe(48)
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def wait_for_code(state: str, open_browser) -> str:
    """Listen on the loopback redirect, hand the sign-in URL to `open_browser`, and return the code the provider sends back."""
    got: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.update({k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Signed in. You can close this tab.")

        def log_message(self, *_):
            pass

    port = urllib.parse.urlparse(auth.CLI_REDIRECT).port
    with http.server.HTTPServer(("127.0.0.1", port), Handler) as server:
        server.timeout = int(os.environ.get("HCP_LOGIN_TIMEOUT", "120"))
        threading.Thread(target=open_browser, daemon=True).start()
        server.handle_request()
    if got.get("state") != state or "code" not in got:
        raise typer.Exit(typer.echo("Sign-in did not complete.", err=True) or 1)
    return got["code"]


def sign_in(open_url=None) -> str:
    """Authorization code flow with PKCE. The person types their password into the identity provider's page; this
    process never sees it. Returns the ID token."""
    options = httpx.get(f"{URL}/api/login-options", timeout=30).json()
    client_id = os.environ.get("HCP_CLIENT_ID") or options["cli_client_id"]
    meta = httpx.get(f"{URL}/.well-known/oauth-protected-resource", timeout=30).json()
    oidc = httpx.get(f"{meta['authorization_servers'][0]}/.well-known/openid-configuration", timeout=30).json()
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    url = oidc["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "scope": "openid", "redirect_uri": auth.CLI_REDIRECT,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
    typer.echo(f"Open this page to sign in:\n{url}")
    opener = open_url or webbrowser.open  # looked up now, so a test can replace it
    code = wait_for_code(state, lambda: opener(url))
    r = httpx.post(oidc["token_endpoint"], timeout=30, data={
        "grant_type": "authorization_code", "code": code, "client_id": client_id,
        "redirect_uri": auth.CLI_REDIRECT, "code_verifier": verifier})
    if r.status_code != 200:
        raise typer.Exit(typer.echo("Sign-in refused.", err=True) or 1)
    return r.json()["id_token"]


@app.command()
def login():
    """Sign in through the identity provider's page and keep the token for the next commands."""
    token = sign_in()
    f = token_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.touch(mode=0o600)
    f.write_text(token)
    typer.echo("Signed in.")


@app.command()
def cases():
    """Every case you may see."""
    with client() as c:
        for d in c.get("/v1/cases").json():
            typer.echo(f"{d['id']:20} {d['route']:11} {d['status']}")


@app.command()
def case(case_id: str):
    """One case in full."""
    with client() as c:
        show(c.get(f"/v1/cases/{case_id}"))


@app.command()
def watch(case_id: str, seconds: int = 60):
    """Follow a case until a person is no longer needed."""
    with client() as c, c.stream("GET", f"/v1/cases/{case_id}/events", params={"max_s": seconds}) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                typer.echo(line[5:].strip())


@app.command()
def dlq():
    """Events that failed every attempt and wait for a person."""
    with client() as c:
        show(c.get("/v1/dead-letters"))


@app.command("dlq-replay")
def dlq_replay(dead_letter_id: int):
    """Put a parked event back on the bus. Compliance only."""
    with client() as c:
        show(c.post(f"/v1/dead-letters/{dead_letter_id}/replay"))


@app.command()
def releases():
    """Eval metrics, cost and spend per release."""
    with client() as c:
        show(c.get("/v1/releases"))


@app.command("release-diff")
def release_diff(a: str, b: str):
    """What moved between two releases."""
    with client() as c:
        show(c.get("/v1/releases/diff", params={"a": a, "b": b}))


@app.command("release-promote")
def release_promote(release: str):
    """Make a release that passed the gate the baseline. Compliance only."""
    with client() as c:
        show(c.post(f"/v1/releases/{release}/promote"))


if __name__ == "__main__":
    app()
