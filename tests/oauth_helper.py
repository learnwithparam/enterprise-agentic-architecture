"""What a person does in the browser during `hcp login`, so tests can run the real CLI flow without one."""

import re
from urllib.parse import urljoin

import httpx

from hcpagents import auth


def hosted_login(url: str, user: str = "u-brandt", password: str = auth.DEMO_PASSWORD) -> None:
    """Open the sign-in URL, type the credentials into the provider's page, and follow the redirect to the CLI's loopback."""
    with httpx.Client(follow_redirects=False, timeout=30) as h:
        r = h.get(url)
        while r.status_code in (301, 302):
            r = h.get(urljoin(url, r.headers["location"]))
        fields = dict(re.findall(r'name="(\w+)" value="([^"]*)"', r.text))
        r = h.post(urljoin(url, "/cognito-idp/login"), data={**fields, "username": user, "password": password})
        if r.status_code in (301, 302):  # a wrong password stays on the page, so the loopback is never reached
            h.get(r.headers["location"])
