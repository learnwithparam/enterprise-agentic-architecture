# ADR 0030: Agents have a roster, and the console is a static Next.js export

Status: accepted, 29 October 2026.

## Context

Eight agents now run on the platform. Without one place that states each agent's goal and its limit, a
reader cannot tell what an agent may do alone, and Compliance cannot check it. The console also had to
show agents, releases and live case activity, behind a real sign-in with several tenants.

## Decision

- **A roster file.** `world/agents.toml` holds one row per agent: goal, what it perceives, what it does
  alone, what it only proposes, what it never does, and which model class it uses. `GET /api/agents`
  joins each row with its calls and cost from the AI gateway's spend log. The rule underneath is that an
  agent acts alone only in the direction that lowers risk.
- **Next.js 16 as a static export.** `web/` is plain JavaScript and JSX with the App Router. `next build`
  writes `web/dist`, and FastAPI serves it from the same origin, so there is one deployable and no CORS.
  Pages fetch in the browser with a bearer token. TypeScript is left out to keep the toolchain small.
- **Sign-in before the shell.** The sign-in screen reads the public `GET /api/login-options` (tenants
  and demo personas, no credentials), then exchanges a password for a signed token. Every other call
  carries that token, and Cedar decides what it may do.
- **Approval is a signature.** The case page asks for the password again before it posts an approval.
- **Live case activity.** While a case waits for a reviewer, the page follows `/v1/cases/{id}/events`.
- **A test ties the two sides together.** `tests/test_console.py` fails when a page calls a path that
  is not a route, or a nav link has no page.

## Consequences

- No server-side rendering, so a page is empty until its data arrives.
- A static export sets no content security policy of its own. The API should send one header for it.
- `/api/login-options` lists demo personas and is for the local emulator only.
