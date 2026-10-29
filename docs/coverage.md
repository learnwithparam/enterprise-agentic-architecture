---
title: Coverage
description: Every case-study ask, role requirement and agentic-system concept, with the doc section, screen, lab and test that cover it
---

# Coverage

One row per requirement. Each row names where it is explained, which screen shows it, which lab teaches it
and which test proves it. `tests/test_coverage.py` fails when a file, screen, lab or test named here does
not exist, and when a required topic has no row, so this table cannot drift from the code.

A dash means the requirement has no screen or no lab of its own. Every row has a test.

## Case study, Part A

| Requirement | Doc | Screen | Lab | Test |
|---|---|---|---|---|
| Overlapping messages to one doctor are held | case-study.md | /hcp | arbitrate-agents-with-a-supervisor | tests/test_outreach.py::test_an_open_medical_case_holds_the_promotion_and_the_reason_points_at_the_case |
| Product questions are routed in seconds | architecture-walkthrough.md | /inbox | route-inquiries-with-a-routing-table | tests/test_graph.py::test_step_functions_on_floci_route_like_python |
| Insight is combined across teams | architecture-walkthrough.md | /hcp | - | tests/test_perception.py::test_a_theme_needs_two_doctors_and_names_its_sources_but_never_quotes_them |
| Content is provably current and approved | architecture-walkthrough.md | /content | ground-replies-with-approved-blocks | tests/test_grounding.py::test_a_block_withdrawn_after_drafting_fails_at_send_time |
| One record per doctor across channels | case-study.md | /hcp | - | tests/test_identity.py::test_a_landed_interaction_joins_the_360_of_its_doctor_and_unknowns_wait_for_a_human |
| Channel events are signed and land once | architecture-walkthrough.md | - | - | tests/test_ingest.py::test_a_signed_webhook_is_stored_and_the_same_event_again_changes_nothing |
| A nightly batch is a durable schedule | architecture-walkthrough.md | - | - | tests/test_ingest.py::test_the_nightly_schedule_exists_once_per_tenant_and_runs_the_import |
| Multi-country rules are data | case-study.md | /review | - | tests/test_flow.py::test_reviewer_approves_only_in_their_own_country |
| A kill switch per country that Compliance holds | case-study.md | /proof | - | tests/test_flow.py::test_compliance_kill_switch_stops_automatic_replies |
| Pharmacovigilance reached with day zero and quotes | case-study.md | /inbox | route-inquiries-with-a-routing-table | tests/test_rules.py::test_keyword_screen_catches_english_adverse_events |
| Off-label questions go to Medical | case-study.md | /inbox | - | tests/test_rules.py::test_one_off_label_question_makes_the_whole_case_off_label |
| Prompt injection is declined | architecture-walkthrough.md | /inbox | - | tests/test_rules.py::test_injection_screen |
| Audit trail nobody can edit | architecture-walkthrough.md | /proof | prove-the-audit-trail-with-a-hash-chain | tests/test_flow.py::test_ledger_detects_tampering_and_the_archive_refuses_deletion |
| GDPR erasure against an immutable ledger | architecture-walkthrough.md | - | - | tests/test_privacy.py::test_erasing_a_person_makes_their_data_unreadable_and_the_chain_still_verifies |
| Human approval is an electronic signature | architecture-walkthrough.md | /review | - | tests/test_durable.py::test_approval_without_a_fresh_signature_is_refused_and_the_case_stays_open |
| First release scope and success measures | case-study.md | /releases | gate-releases-with-evals | tests/test_releases.py::test_the_eval_gate_blocks_a_release_that_regresses |
| EU AI Act classification and duties | eu-ai-act.md | - | - | tests/test_world.py::test_every_reference_resolves |
| Validation pack | validation-pack.md | - | - | tests/test_guardian.py::test_a_redteam_miss_fails_the_eval_gate |

## Case study, Part B

| Requirement | Doc | Screen | Lab | Test |
|---|---|---|---|---|
| The clickable slice and every screen | product-walkthrough.md | / | - | tests/test_walkthrough.py::test_doc_and_capture_list_the_same_screens_in_order |
| The moments the system refuses to answer or act | case-study.md | /review | - | tests/test_flow.py::test_nobody_approves_on_a_pharmacovigilance_case |
| A field rep sees status but not detail | case-study.md | /review | guard-tool-calls-with-cedar | tests/test_flow.py::test_field_rep_sees_status_but_not_case_detail |
| Content withdrawn mid-review blocks the send | product-walkthrough.md | /content | - | tests/test_flow.py::test_withdrawn_content_invalidates_the_draft_and_blocks_the_send |
| Edge cases and open questions | case-study.md | - | - | tests/test_rules.py::test_scope_is_per_country |

## Role requirements

| Requirement | Doc | Screen | Lab | Test |
|---|---|---|---|---|
| Solution shaping and ADRs | adr/README.md | - | - | tests/test_claude_config.py::test_every_file_a_skill_rule_or_subagent_names_exists |
| Governance gates | validation-pack.md | /releases | gate-releases-with-evals | tests/test_releases.py::test_only_a_clean_run_can_become_the_baseline |
| A vendor-agnostic model layer | adr/0019-one-thin-gateway-meters-every-model-call.md | /agents | pick-the-model-with-a-router | tests/test_gateway.py::test_when_the_first_provider_is_busy_the_next_one_answers_and_the_log_says_which |
| Swappable embeddings | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | - | - | tests/test_retrieval.py::test_an_unknown_adapter_name_is_refused |
| QA with mutation testing | architecture-walkthrough.md | - | - | tests/test_ci.py::test_ci_runs_the_gate_and_every_security_check_on_each_pull_request |
| DevSecOps in CI | architecture-walkthrough.md | - | - | tests/test_ci.py::test_every_ci_dependency_is_pinned |
| Data engineering, streaming and batch | architecture-walkthrough.md | - | - | tests/test_ingest.py::test_a_batch_file_is_ingested_once_moved_aside_and_bad_lines_do_not_stop_it |
| AWS infrastructure as code | adr/0029-the-platform-is-one-cdk-stack-checked-before-any-deploy.md | - | - | tests/test_deploy.py::test_cdk_nag_finds_nothing_to_fix |
| Docker and the container choice over Kubernetes | adr/0031-one-codebase-two-services-and-ecs-not-kubernetes.md | - | - | tests/test_deploy.py::test_the_database_is_private_encrypted_and_protected |
| LLMOps: cost and prompt per release | architecture-walkthrough.md | /releases | gate-releases-with-evals | tests/test_gateway.py::test_spend_splits_by_release_and_prompt_version |
| Regulated industry controls | eu-ai-act.md | /proof | - | tests/test_deploy.py::test_each_tenant_has_its_own_locked_encrypted_ledger_and_key |

## Agentic-system concepts

| Requirement | Doc | Screen | Lab | Test |
|---|---|---|---|---|
| Goals and a roster of agents | architecture-walkthrough.md | /agents | - | tests/test_flow.py::test_agents_endpoint_lists_the_roster_with_a_goal_and_a_limit_for_each |
| Planning and the agentic loop | architecture-walkthrough.md | /review | bound-agent-plans-with-a-policy-kernel | tests/test_plan.py::test_the_loop_is_bounded_and_what_stays_uncovered_goes_to_a_human |
| Graph engineering with LangGraph | adr/0014-langgraph-plans-inside-one-kernel-step.md | - | - | tests/test_plan.py::test_the_compiled_graph_has_exactly_the_declared_edges |
| The policy kernel | adr/0013-a-policy-kernel-bounds-every-plan.md | - | bound-agent-plans-with-a-policy-kernel | tests/test_kernel.py::test_the_safety_screen_cannot_be_skipped |
| Model routing | adr/0008-model-router.md | /agents | pick-the-model-with-a-router | tests/test_router.py::test_a_schema_failure_escalates_to_sonnet_and_a_second_failure_goes_to_a_human |
| Tool use and MCP | adr/0028-machine-interfaces-share-one-front-door.md | - | - | tests/test_interfaces.py::test_mcp_tools_are_tenant_scoped_and_cedar_checked |
| Multi-agent coordination and arbitration | adr/0032-agents-talk-through-state-and-events-not-to-each-other.md | /hcp | arbitrate-agents-with-a-supervisor | tests/test_outreach.py::test_two_proposals_within_days_of_each_other_yield_to_the_one_that_serves_the_doctor |
| Shared memory in HCP 360 | architecture-walkthrough.md | /hcp | - | tests/test_identity.py::test_every_channel_handle_resolves_to_the_doctor_it_belongs_to |
| Perception through events | architecture-walkthrough.md | /inbox | - | tests/test_perception.py::test_a_rash_in_a_rep_note_opens_a_safety_case_and_freezes_contact_with_nobody_asking |
| Autonomy levels and human in the loop | architecture-walkthrough.md | /review | - | tests/test_rules.py::test_autonomy_needs_switch_topic_and_adult_population |
| Verification and grounding | architecture-walkthrough.md | /review | ground-replies-with-approved-blocks | tests/test_grounding.py::test_an_invented_sentence_fails_the_check |
| Guardrails and injection defence | architecture-walkthrough.md | /inbox | guard-tool-calls-with-cedar | tests/test_rules.py::test_tool_guard_blocks_other_countries_and_unknown_tools |
| Authentication | adr/0010-signed-tokens-and-server-side-tenant.md | / | - | tests/test_flow.py::test_a_token_for_another_audience_is_refused |
| Authorization with Cedar | architecture-walkthrough.md | - | guard-tool-calls-with-cedar | tests/test_flow.py::test_cedar_refuses_a_principal_acting_across_tenants |
| Multi-tenant isolation | adr/0009-postgres-with-row-level-security.md | / | - | tests/test_tenancy.py::test_every_table_forces_row_level_security_with_a_tenant_policy |
| Caching | architecture-walkthrough.md | - | - | tests/test_cache.py::test_search_still_answers_when_valkey_is_down |
| Long running and durable execution | adr/0016-temporal-owns-the-life-of-a-case.md | /review | - | tests/test_durable.py::test_another_worker_resumes_a_case_from_temporal_history_without_repeating_a_step |
| Always on agents | architecture-walkthrough.md | /content | - | tests/test_cache.py::test_the_always_on_steward_invalidates_a_draft_when_content_is_withdrawn |
| Idempotency and the dead-letter queue | adr/0020-delivery-is-at-least-once-so-consumers-are-idempotent.md | - | - | tests/test_events.py::test_an_event_that_fails_every_attempt_is_parked_with_its_error_and_leaves_the_queue |
| Hybrid retrieval | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | /content | - | tests/test_retrieval.py::test_hybrid_finds_every_answer_that_full_text_alone_misses |
| Self-improvement proven per release | adr/0025-a-release-is-a-hash-and-must-beat-its-baseline.md | /releases | gate-releases-with-evals | tests/test_releases.py::test_a_diff_names_the_metrics_and_the_parts_that_changed |
| The improver proposes and promotes nothing | adr/0026-the-guardian-only-tightens-and-the-improver-only-proposes.md | /agents | - | tests/test_guardian.py::test_a_topic_reviewers_keep_rejecting_becomes_one_proposal_and_nothing_is_promoted |
| Red-team evals | architecture-walkthrough.md | /proof | - | tests/test_guardian.py::test_every_attack_in_the_corpus_is_caught |
| Cost control and budgets | adr/0019-one-thin-gateway-meters-every-model-call.md | /agents | pin-the-model-with-agent-sdk-options | tests/test_model_policy.py::test_spend_cap_stops_live_calls |
| Harness engineering | architecture-walkthrough.md | - | pin-the-model-with-agent-sdk-options | tests/test_model_policy.py::test_options_are_isolated_and_pinned |
| Observability with OpenTelemetry | adr/0027-one-trace-per-case-with-pii-redacted.md | - | - | tests/test_tracing.py::test_a_case_is_one_trace_with_a_child_per_step |
| CLI | architecture-walkthrough.md | - | - | tests/test_cli.py::test_login_keeps_the_token_private_and_commands_use_it |
| Endpoints with streaming | adr/0028-machine-interfaces-share-one-front-door.md | / | - | tests/test_interfaces.py::test_the_case_stream_ends_with_its_status |
| Rate limits | adr/0028-machine-interfaces-share-one-front-door.md | - | - | tests/test_interfaces.py::test_a_user_over_the_limit_is_told_to_wait |
| SaaS console | adr/0030-agents-have-a-roster-and-the-console-is-a-static-next-export.md | / | - | tests/test_console.py::test_every_path_the_console_calls_is_a_route |
