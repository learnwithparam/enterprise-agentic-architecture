# Pin MCP tools with description hashes

**The job:** Quillon lets a client's own agents call three tools on the platform over MCP. The model of
that client reads each tool's description to decide what to do. Nobody must be able to change a
description after a person has read it.

**Before:** a description is plain text in the code. A change that tells the client's model to "also send
the case to this address" looks like a small edit, and nothing stops it reaching the client.

**After:** the hash of each tool's name and description is pinned in `src/hcpagents/mcp_pins.json`. When the
server starts, a tool whose description no longer matches its pin is left out, and it is named in
`DISABLED`. A person reads the change, then pins the new hash.

## Prerequisites

[uv](https://docs.astral.sh/uv/) only. No Floci or API key is needed.

## How it works

```mermaid
flowchart TD
    A[Server starts] --> B[Hash each tool description]
    B --> C{Same as the pin}
    C -->|yes| D[Tool is served]
    C -->|no| E[Tool is left out and named in DISABLED]
```

## Steps

1. Step 1: every tool has a pin that matches its description.
2. Step 2: a tool that matches its pin is served.
3. Step 3: a changed description is refused and named.

## Run it

```bash
make lab N=pin-mcp-tools-with-description-hashes
```

Expect: 3 passed

## Read

- `src/hcpagents/mcp_server.py`: `description_hash`, `pinned` and `build`.
- `src/hcpagents/mcp_pins.json`: the pins.
- `docs/adr/0028-machine-interfaces-share-one-front-door.md`.

## What the test proves

- The pin file lists each tool and each hash matches the code.
- A tool with an unchanged description is served.
- A tool with a changed description is not served, and the others still are.

## Break it, watch the test fail

In `src/hcpagents/mcp_server.py`, in `pinned`, change the `if pins.get(...) == description_hash(tool):` line
to `if True:`. Step 3 fails: the changed description would be served. Put it back.

## What production adds

`tests/test_live_i_mcp_pins.py` builds the real server and lists its tools. After a reviewed change, run
`uv run python -m hcpagents.mcp_server` to pin the new hashes. The pin change shows in the pull request.

## New words

- **MCP**: A standard way for an agent to call tools on another system.
- **hash**: A short fingerprint of some text.
- **pin**: A saved hash that a tool must match.
- **tool description**: The text a model reads to learn what a tool does.
