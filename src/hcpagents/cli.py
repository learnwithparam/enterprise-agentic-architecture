"""hcp is the platform in a terminal. It uses the same /v1 API as any other client (ADR 0028).

    hcp login

    hcp cases | case <id> | watch <id>

    hcp dlq | dlq-replay <id>

    hcp releases | release-diff <first> <second>

    hcp release-promote <release>

Login opens your browser. The token is kept in ~/.config/hcp/token for you only.
"""

import base64
import functools
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
    path = token_file()
    if not path.exists():
        raise typer.Exit(typer.echo("Not signed in. Run: hcp login", err=True) or 1)
    return httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {path.read_text().strip()}"}, timeout=30)


def show(response: httpx.Response):
    if response.status_code >= 400:
        typer.echo(f"{response.status_code}: {response.json().get('detail', response.text)}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(response.json(), indent=2))


def pkce_pair() -> tuple[str, str]:
    """A one-use secret and its SHA-256 challenge. The identity provider sees only the challenge until we use the code."""
    verifier = secrets.token_urlsafe(48)
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def wait_for_code(state: str, open_browser) -> str:
    """Listen on the local redirect and call `open_browser`. Return the code the provider sends back."""
    got: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({key: values[0] for key, values in query.items()})
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
    """Sign in with the code flow and PKCE. The person types their password on the identity provider's page.

    This process never sees it. It returns the ID token.
    """
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
    code = wait_for_code(state, functools.partial(opener, url))
    response = httpx.post(oidc["token_endpoint"], timeout=30, data={
        "grant_type": "authorization_code", "code": code, "client_id": client_id,
        "redirect_uri": auth.CLI_REDIRECT, "code_verifier": verifier})
    if response.status_code != 200:
        raise typer.Exit(typer.echo("Sign-in refused.", err=True) or 1)
    return response.json()["id_token"]


@app.command()
def login():
    """Sign in on the identity page. The token is kept for later commands."""
    token = sign_in()
    path = token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.write_text(token)
    typer.echo("Signed in.")


@app.command()
def cases():
    """Every case you may see."""
    with client() as session:
        for case in session.get("/v1/cases").json():
            typer.echo(f"{case['id']:20} {case['route']:11} {case['status']}")


@app.command()
def case(case_id: str):
    """One case in full."""
    with client() as session:
        show(session.get(f"/v1/cases/{case_id}"))


@app.command()
def watch(case_id: str, seconds: int = 60):
    """Follow a case until it no longer needs a person."""
    with client() as session, session.stream("GET", f"/v1/cases/{case_id}/events", params={"max_s": seconds}) as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                typer.echo(line[5:].strip())


@app.command()
def dlq():
    """Events that failed every try and wait for a person."""
    with client() as session:
        show(session.get("/v1/dead-letters"))


@app.command("dlq-replay")
def dlq_replay(dead_letter_id: int):
    """Put a parked event back on the bus. Only compliance may."""
    with client() as session:
        show(session.post(f"/v1/dead-letters/{dead_letter_id}/replay"))


@app.command()
def releases():
    """Eval metrics, cost and spend per release."""
    with client() as session:
        show(session.get("/v1/releases"))


@app.command("release-diff")
def release_diff(first: str, second: str):
    """What moved between two releases."""
    with client() as session:
        show(session.get("/v1/releases/diff", params={"a": first, "b": second}))


@app.command("release-promote")
def release_promote(release: str):
    """Make a release that passed the gate the baseline. Only compliance may."""
    with client() as session:
        show(session.post(f"/v1/releases/{release}/promote"))


if __name__ == "__main__":
    app()
