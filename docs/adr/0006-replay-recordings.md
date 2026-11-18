# ADR 0006: Replay recorded model calls by default

Status: accepted, 15 October 2026

## Context

Tests, evals, CI and every demo would otherwise call the model. That costs money on every run. It gives a slightly different answer each time. It makes a failing test impossible to repeat.

## Decision

Each agent call has a key (`agents.recording_key`). The key is made from the agent, model, prompt version, system prompt, output schema and the prompt text. Replay is the default. It loads the recorded output. It runs the recorded tool calls through the same guards and Cedar checks as a live call. `LIVE=1` calls the model and writes the recording. A missing recording fails loudly. It never falls back to a live call.

## Options considered

- **Mock the model in tests.** Rejected: the mock is not the model's real output.
- **Always live.** Rejected: cost and flakiness.
- **Record once, replay everywhere, re-record on purpose.** Chosen.

## Consequences

`make check`, `make evals` and the walkthrough cost nothing. Changing a prompt changes its key. So the change cannot ship until someone records it and the gate passes on the new recording.

## Enforced by

`tests/test_model_policy.py::test_every_recording_used_only_allowed_models` and the eval gate. The eval gate runs every recording.
