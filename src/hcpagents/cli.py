"""hcp: the platform from a terminal, over the same /v1 API any other client uses (ADR 0028).

    hcp login --user u-raman        sign in; the token is kept in ~/.config/hcp/token (owner only)
    hcp cases | case <id> | watch <id>
    hcp dlq | dlq-replay <id>
    hcp releases | release-diff <a> <b> | release-promote <release>
"""

import json
import os
from pathlib import Path

import httpx
import typer

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
URL = os.environ.get("HCP_URL", "http://localhost:8765")


def token_file() -> Path:
    return Path(os.environ.get("HCP_CONFIG", Path.home() / ".config" / "hcp")) / "token"


def client() -> httpx.Client:
    """An HTTP client carrying the saved token. Tests replace this with one bound to the app."""
    f = token_file()
    if not f.exists():
        raise typer.Exit(typer.echo("Not signed in. Run: hcp login --user <id>", err=True) or 1)
    return httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {f.read_text().strip()}"}, timeout=30)


def show(r: httpx.Response):
    if r.status_code >= 400:
        typer.echo(f"{r.status_code}: {r.json().get('detail', r.text)}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))


@app.command()
def login(user: str = typer.Option(...), password: str = typer.Option(..., prompt=True, hide_input=True, envvar="HCP_PASSWORD")):
    """Sign in and keep the token for the next commands."""
    r = httpx.post(f"{URL}/api/login", json={"user": user, "password": password}, timeout=30)
    if r.status_code != 200:
        typer.echo("Sign-in refused.", err=True)
        raise typer.Exit(1)
    f = token_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.touch(mode=0o600)
    f.write_text(r.json()["token"])
    typer.echo(f"Signed in as {user}.")


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
