---
title: Validation pack
description: A GAMP 5 style validation pack that maps each requirement to the test and the mutant that prove it
---

# Validation pack

A computerised system that supports a regulated process is validated before use and kept validated after
each change. This pack follows the shape of GAMP 5 (category 5, custom software): what the system must do,
how each requirement is proven, and what keeps it proven.

| GAMP 5 artefact | Here |
|---|---|
| User requirements | The requirement table below |
| Functional and design specification | [Architecture walkthrough](./architecture-walkthrough.md) and the [ADRs](./adr/README.md) |
| Risk assessment | The threat table in the walkthrough and the [EU AI Act classification](./eu-ai-act.md) |
| Installation qualification | `make up` provisions every dependency; `tests/test_deploy.py` synthesizes the stack with cdk-nag |
| Operational qualification | The test suite and the eval gate |
| Performance qualification | The eval gate over the inquiry set, per release, with a baseline |
| Traceability matrix | The table below and [coverage](./coverage.md), both checked by `tests/test_coverage.py` |
| Change control | A release id pins prompts, router, retrieval and policy table; a change is a candidate release that must pass the gate |
| Periodic review | The Releases page and the guardian's override-rate patrol |

## Requirements and the evidence for each

A mutant is an edit that breaks the property. The gate fails if no test notices it, which is what makes the
test evidence and not decoration. `tests/test_coverage.py` fails when a test or mutant named here does not exist.

| Requirement | Test | Mutant |
|---|---|---|
| A possible adverse event always reaches pharmacovigilance | `tests/test_rules.py::test_keyword_screen_catches_english_adverse_events` | An adverse event always goes to pharmacovigilance |
| An injection attempt is declined | `tests/test_rules.py::test_injection_screen` | An injection attempt is declined |
| Only current approved blocks are evidence | `tests/test_grounding.py::test_an_expired_block_is_not_evidence` | Only current blocks count as evidence |
| A withdrawn block never goes out | `tests/test_grounding.py::test_a_block_withdrawn_after_drafting_fails_at_send_time` | The send rechecks content and fails closed |
| One tenant never reads another's rows | `tests/test_tenancy.py::test_a_second_tenant_cannot_see_or_change_the_first_tenants_rows` | Every tenant table forces row-level security |
| Every route needs a verified identity | `tests/test_flow.py::test_every_api_and_v1_route_refuses_a_caller_without_a_verified_token` | Every API route needs a verified token |
| An agent reads only its own case's country and product | `tests/test_rules.py::test_tool_guard_blocks_other_countries_and_unknown_tools` | A tool call stays in the case's country and product |
| A plan cannot skip a safety step | `tests/test_kernel.py::test_the_safety_screen_cannot_be_skipped` | A step never runs out of order |
| Only two models can be called | `tests/test_model_policy.py::test_a_model_off_the_allowlist_fails_the_run` | Only the allowlisted models may answer |
| Past ledger entries cannot be edited | `tests/test_flow.py::test_ledger_detects_tampering_and_the_archive_refuses_deletion` | The ledger bucket is locked in compliance mode |
| An approval is a signature | `tests/test_durable.py::test_approval_without_a_fresh_signature_is_refused_and_the_case_stays_open` | Approval needs a fresh signature by the approver |
| A crashed worker resumes a case once | `tests/test_durable.py::test_another_worker_resumes_a_case_from_temporal_history_without_repeating_a_step` | Asking twice for one inquiry joins one workflow |
| A model call is metered and budgeted | `tests/test_gateway.py::test_a_key_over_its_budget_is_refused` | The gateway refuses a key over its budget |
| A release cannot regress | `tests/test_releases.py::test_the_eval_gate_blocks_a_release_that_regresses` | The eval gate fails on a regression |
| The guardian only lowers autonomy | `tests/test_guardian.py::test_the_guardian_never_raises_autonomy` | The guardian leaves a country inside the limit alone |
| A signed-in user cannot write their own role | `tests/test_deploy.py::test_a_user_cannot_write_their_own_role_or_tenant` | A user cannot write their own role |

## What this pack does not cover

It validates the platform, not a client's content. The client validates its approved blocks in its MLR
system, and signs off the cleared topics per country. Running against real data needs an installation
qualification in the client's account, which this repository synthesizes but does not deploy.
