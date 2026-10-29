# ADR 0032: Agents coordinate through shared state and events, and MCP serves tools, not peers

Status: accepted, 30 October 2026.

## Context

Eight agents work on the same doctors and cases. Two protocols are often proposed for this: A2A, where an
agent calls another agent as a remote peer, and MCP, where an agent or host calls a tool. Free-form
agent-to-agent conversation is hard to audit, and in a regulated setting every decision must be on the
ledger with its reason.

## Decision

- **Shared state is the memory.** The HCP 360 record, the case and the ledger are what agents read and
  write. The outreach coordinator reads the open medical case; it does not ask the inquiry agent.
- **Events are the nudge.** The bus carries facts (`ContentWithdrawn`, `AdverseEventSuspected`, a case
  decided). A consumer reacts and is idempotent (ADR 0020).
- **The supervisor arbitrates in code.** When two agents want different things for one doctor, a rule in
  the policy table decides and writes the reason (ADR 0023). No agent negotiates.
- **MCP is for tools.** The server exposes read and operate tools to a client's own agents, each one a
  Cedar decision (ADR 0028). It does not let an outside agent instruct ours.
- **A2A is not used.** There is no peer discovery or task delegation across trust boundaries today.

## Consequences

- Every coordination step is a row or an event, so the trace and the ledger explain it without chat logs.
- Adding a ninth agent means a roster row (ADR 0030), its event subscriptions and its Cedar actions.
- If a client's agents ever need to delegate work to ours, that is a new ADR with identity, scope and
  Cedar for the delegated task. Until then the door stays shut.

## Alternatives rejected

- **A2A between our own agents.** Rejected: it turns a table lookup into a conversation nobody can replay.
- **A shared scratchpad the agents write to freely.** Rejected: no owner per field, so no accountability.
