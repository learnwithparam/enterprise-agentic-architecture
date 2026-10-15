# ADR 0006: Replay recorded model calls by default

Status: accepted, 15 October 2026

## Context

Tests, evals, CI and every demo would otherwise call the model. That costs money on every run, gives a
slightly different answer each time, and makes a failing test impossible to reproduce.

## Decision

Each agent call is keyed by agent, model, prompt version, system prompt, output schema and the prompt
text (`agents.recording_key`).
Replay, the default, loads the recorded output and runs the recorded tool calls through the same guards and
Cedar checks as a live call. `LIVE=1` calls the model and writes the recording. A missing recording fails
loudly; it never falls back to a live call.

## Options considered

- **Mock the model in tests.** Rejected: the mock is not the model's real output.
- **Always live.** Rejected: cost and flakiness.
- **Record once, replay everywhere, re-record on purpose.** Chosen.

## Consequences

`make check`, `make evals` and the walkthrough cost nothing. Changing a prompt changes its key, so the
change cannot ship until someone records it and the gate passes on the new recording.

## Enforced by

`tests/test_model_policy.py::test_every_recording_used_only_haiku_5_5` and the eval gate, which runs
every recording.
