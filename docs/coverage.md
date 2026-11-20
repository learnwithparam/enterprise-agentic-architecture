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
| Insight is combined across teams | architecture-walkthrough.md | /hcp | watch-with-the-sentinel-and-steward | tests/test_perception.py::test_a_theme_needs_two_doctors_and_names_its_sources_but_never_quotes_them |
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
| Human approval is an electronic signature | architecture-walkthrough.md | /review | keep-a-case-alive-with-temporal | tests/test_durable.py::test_approval_without_a_fresh_signature_is_refused_and_the_case_stays_open |
| First release scope and success measures | case-study.md | /releases | gate-releases-with-evals | tests/test_releases.py::test_the_eval_gate_blocks_a_release_that_regresses |
| EU AI Act classification and duties | eu-ai-act.md | - | - | tests/test_world.py::test_every_reference_resolves |
| Validation pack | validation-pack.md | - | let-the-guardian-only-tighten | tests/test_guardian.py::test_a_redteam_miss_fails_the_eval_gate |

## Case study, Part B

| Requirement | Doc | Screen | Lab | Test |
|---|---|---|---|---|
| The clickable slice and every screen | product-walkthrough.md | / | - | tests/test_walkthrough.py::test_doc_and_capture_list_the_same_screens_in_order |
| The moments the system refuses to answer or act | case-study.md | /review | - | tests/test_flow.py::test_nobody_approves_on_a_pharmacovigilance_case |
| A field rep sees status but not detail | case-study.md | /review | guard-tool-calls-with-cedar | tests/test_flow.py::test_field_rep_sees_status_but_not_case_detail |
| Content withdrawn mid-review blocks the send | product-walkthrough.md | /content | - | tests/test_flow.py::test_content_pulled_outside_withdraw_still_blocks_the_send |
| Edge cases and open questions | case-study.md | - | - | tests/test_rules.py::test_scope_is_per_country |
| A grounded reply is emailed and the ledger names the message | architecture-walkthrough.md | - | - | tests/test_delivery.py::test_the_outbox_holds_the_exact_grounded_reply_and_the_ledger_names_the_message |
| A withdrawn block sends no email | architecture-walkthrough.md | /content | - | tests/test_delivery.py::test_a_block_withdrawn_before_the_send_sends_nothing |
| A reply to a doctor who asked is sent without marketing consent | case-study.md | /hcp | - | tests/test_delivery.py::test_a_reply_to_a_doctor_who_asked_is_sent_even_without_marketing_consent |
| A failed delivery is never marked sent | architecture-walkthrough.md | - | - | tests/test_delivery.py::test_a_delivery_that_fails_is_not_marked_sent |
| A planned touch is checked again when a human approves it | case-study.md | /hcp | arbitrate-agents-with-a-supervisor | tests/test_outreach_approval.py::test_an_open_medical_case_blocks_an_approved_touch |
| A rep approves outreach only in their own country | case-study.md | /hcp | - | tests/test_outreach_approval.py::test_only_a_rep_in_the_doctors_country_may_approve |
| A safety signal opens an intake with a 24 hour clock | case-study.md | - | - | tests/test_handoff_workers.py::test_a_safety_signal_opens_an_intake_with_a_24_hour_clock |
| Review handoffs reach the reviewers and overdue ones escalate | architecture-walkthrough.md | /review | - | tests/test_handoff_workers.py::test_a_review_overdue_event_escalates_the_case_once |

## Role requirements

| Requirement | Doc | Screen | Lab | Test |
|---|---|---|---|---|
| Solution shaping and ADRs | adr/README.md | - | - | tests/test_claude_config.py::test_every_file_a_skill_rule_or_subagent_names_exists |
| Governance gates | validation-pack.md | /releases | gate-releases-with-evals | tests/test_releases.py::test_only_a_clean_run_can_become_the_baseline |
| A vendor-agnostic model layer | adr/0019-one-thin-gateway-meters-every-model-call.md | /agents | pick-the-model-with-a-router | tests/test_gateway.py::test_when_the_first_provider_is_busy_the_next_one_answers_and_the_log_says_which |
| Swappable embeddings | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | - | retrieve-behind-a-facet-gate | tests/test_retrieval.py::test_an_unknown_adapter_name_is_refused |
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
| Perception through events | architecture-walkthrough.md | /inbox | watch-with-the-sentinel-and-steward | tests/test_perception.py::test_a_rash_in_a_rep_note_opens_a_safety_case_and_freezes_contact_with_nobody_asking |
| Autonomy levels and human in the loop | architecture-walkthrough.md | /review | - | tests/test_rules.py::test_autonomy_needs_switch_topic_and_adult_population |
| Verification and grounding | architecture-walkthrough.md | /review | ground-replies-with-approved-blocks | tests/test_grounding.py::test_an_invented_sentence_fails_the_check |
| Guardrails and injection defence | architecture-walkthrough.md | /inbox | guard-tool-calls-with-cedar | tests/test_rules.py::test_tool_guard_blocks_other_countries_and_unknown_tools |
| Authentication | adr/0010-signed-tokens-and-server-side-tenant.md | / | - | tests/test_flow.py::test_a_token_for_another_audience_is_refused |
| Authorization with Cedar | architecture-walkthrough.md | - | guard-tool-calls-with-cedar | tests/test_flow.py::test_cedar_refuses_a_principal_acting_across_tenants |
| Multi-tenant isolation | adr/0009-postgres-with-row-level-security.md | / | isolate-tenants-with-row-level-security | tests/test_tenancy.py::test_every_table_forces_row_level_security_with_a_tenant_policy |
| Caching | architecture-walkthrough.md | - | - | tests/test_cache.py::test_search_still_answers_when_valkey_is_down |
| Long running and durable execution | adr/0016-temporal-owns-the-life-of-a-case.md | /review | keep-a-case-alive-with-temporal | tests/test_durable.py::test_another_worker_resumes_a_case_from_temporal_history_without_repeating_a_step |
| Always on agents | architecture-walkthrough.md | /content | - | tests/test_cache.py::test_the_always_on_steward_invalidates_a_draft_when_content_is_withdrawn |
| Idempotency and the dead-letter queue | adr/0020-delivery-is-at-least-once-so-consumers-are-idempotent.md | - | - | tests/test_events.py::test_an_event_that_fails_every_attempt_is_parked_with_its_error_and_leaves_the_queue |
| Hybrid retrieval | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | /content | retrieve-behind-a-facet-gate | tests/test_retrieval.py::test_hybrid_finds_every_answer_that_full_text_alone_misses |
| Self-improvement proven per release | adr/0025-a-release-is-a-hash-and-must-beat-its-baseline.md | /releases | gate-releases-with-evals | tests/test_releases.py::test_a_diff_names_the_metrics_and_the_parts_that_changed |
| The improver proposes and promotes nothing | adr/0026-the-guardian-only-tightens-and-the-improver-only-proposes.md | /agents | let-the-guardian-only-tighten | tests/test_guardian.py::test_a_topic_reviewers_keep_rejecting_becomes_one_proposal_and_nothing_is_promoted |
| Red-team evals | architecture-walkthrough.md | /proof | let-the-guardian-only-tighten | tests/test_guardian.py::test_every_attack_in_the_corpus_is_caught |
| Cost control and budgets | adr/0019-one-thin-gateway-meters-every-model-call.md | /agents | pin-the-model-with-agent-sdk-options | tests/test_model_policy.py::test_spend_cap_stops_live_calls |
| Harness engineering | architecture-walkthrough.md | - | pin-the-model-with-agent-sdk-options | tests/test_model_policy.py::test_options_are_isolated_and_pinned |
| Observability with OpenTelemetry | adr/0027-one-trace-per-case-with-pii-redacted.md | - | - | tests/test_tracing.py::test_a_case_is_one_trace_with_a_child_per_step |
| CLI | architecture-walkthrough.md | - | - | tests/test_cli.py::test_login_keeps_the_token_private_and_commands_use_it |
| Endpoints with streaming | adr/0028-machine-interfaces-share-one-front-door.md | / | - | tests/test_interfaces.py::test_the_case_stream_ends_with_its_status |
| Rate limits | adr/0028-machine-interfaces-share-one-front-door.md | - | - | tests/test_interfaces.py::test_a_user_over_the_limit_is_told_to_wait |
| Channel questions open cases once | architecture-walkthrough.md | /inbox | - | tests/test_ingest_cases.py::test_a_signed_question_opens_exactly_one_case_and_a_repeat_opens_none |
| Email copy is fact-checked against approved content | architecture-walkthrough.md | - | ground-replies-with-approved-blocks | tests/test_factcheck.py::test_an_invented_sentence_is_flagged |
| SaaS console | adr/0030-agents-have-a-roster-and-the-console-is-a-static-next-export.md | / | - | tests/test_console.py::test_every_path_the_console_calls_is_a_route |

## Hardening

| Requirement | Doc | Screen | Lab | Test |
|---|---|---|---|---|
| The cloud and local user pools match | adr/0010-signed-tokens-and-server-side-tenant.md | - | - | tests/test_auth_parity.py::test_the_pool_has_every_attribute_the_app_reads_and_requires_mfa |
| A sign-in that needs an MFA code says so | adr/0010-signed-tokens-and-server-side-tenant.md | / | - | tests/test_auth_parity.py::test_an_mfa_challenge_is_unauthenticated_not_a_key_error |
| Password sign-in works only on a local run | adr/0010-signed-tokens-and-server-side-tenant.md | / | - | tests/test_auth_parity.py::test_password_sign_in_refuses_outside_the_local_emulator |
| Local demo passwords are random per user | adr/0010-signed-tokens-and-server-side-tenant.md | / | - | tests/test_auth_parity.py::test_each_local_user_has_their_own_random_password |
| Demo routes exist only on a local run | architecture-walkthrough.md | /proof | - | tests/test_hardening.py::test_the_demo_routes_exist_only_when_the_run_is_local |
| Production uses real AWS unless told otherwise | adr/0003-floci-locally-bedrock-in-production.md | - | - | tests/test_hardening.py::test_production_names_no_aws_endpoint_so_it_talks_to_real_aws |
| Console routes are rate limited per user | adr/0028-machine-interfaces-share-one-front-door.md | - | - | tests/test_console_ratelimit.py::test_a_user_over_the_console_limit_gets_429 |
| The sign-in screen reads its mode from a public config route | architecture-walkthrough.md | / | - | tests/test_console_config.py::test_the_sign_in_screen_can_read_the_config_without_a_token |
| The page policy allows Cognito only outside a local run | architecture-walkthrough.md | / | - | tests/test_console_config.py::test_the_page_policy_allows_cognito_only_outside_a_local_run |
| Handoff teams run on their own schedule | architecture-walkthrough.md | /review | - | tests/test_handoff_schedule.py::test_the_handoff_task_drains_a_review_event_into_the_reviewer_queue |
| Sign-in and channel webhooks are rate limited | adr/0028-machine-interfaces-share-one-front-door.md | - | - | tests/test_hardening.py::test_a_caller_over_the_limit_gets_429_on_sign_in_and_on_the_webhook |
| Cedar is validated strictly against a schema | adr/0010-signed-tokens-and-server-side-tenant.md | - | - | tests/test_hardening.py::test_the_stack_validates_cedar_strictly_against_a_schema_that_names_every_action |
| Alarms on 5xx and parked events stop a deploy | architecture-walkthrough.md | - | - | tests/test_hardening.py::test_the_stack_alarms_on_5xx_and_parked_events_and_a_deploy_rolls_back_on_them |
| A firewall guards the load balancer | architecture-walkthrough.md | - | - | tests/test_hardening.py::test_the_load_balancer_sits_behind_a_firewall_with_common_rules_and_a_rate_cap |
| A big request body is blocked everywhere except the signed webhooks | architecture-walkthrough.md | - | - | tests/test_hardening.py::test_a_big_body_is_blocked_everywhere_except_the_signed_webhooks |
| Withdrawing an unknown block is a 404 | architecture-walkthrough.md | /content | - | tests/test_hardening.py::test_withdrawing_an_unknown_block_is_a_404_not_a_crash |
| A question whose case cannot open is kept, logged and retried | adr/0021-channels-arrive-signed-and-land-once.md | - | - | tests/test_ingest_cases.py::test_a_question_whose_case_cannot_open_is_kept_logged_and_opened_on_a_repeat |
| The limits in the case study and the Floci page agree | floci-support.md | - | - | tests/test_known_limits.py::test_both_pages_list_the_same_limits |

## Live labs

One row per concept of the live labs path. A slug is the lab file name there. Each row names the test that proves it here.
The shell tool is excluded on purpose: a medical agent must never get a shell, and a test holds that line.

| Requirement | Explained in | Screen | Lab | Proof |
|---|---|---|---|---|
| Live lab agent-loop: The agent loop is bounded and what stays uncovered goes to a human | architecture-walkthrough.md | - | bound-agent-plans-with-a-policy-kernel | tests/test_plan.py::test_the_loop_is_bounded_and_what_stays_uncovered_goes_to_a_human |
| Live lab guardrails: Personal data is redacted from traces. Model prompts are not redacted yet | architecture-walkthrough.md | - | - | tests/test_tracing.py::test_redact_removes_emails_phones_and_names |
| Live lab gates: The safety screen cannot be skipped | architecture-walkthrough.md | - | bound-agent-plans-with-a-policy-kernel | tests/test_kernel.py::test_the_safety_screen_cannot_be_skipped |
| Live lab shapes: Every agent answer is a closed object that requires each field it names | architecture-walkthrough.md | - | - | tests/test_live_g_structure.py::test_every_agent_answer_is_a_closed_object_that_requires_each_field_it_names |
| Live lab tool-schemas: The agent tools are the two read-only content tools | architecture-walkthrough.md | - | - | tests/test_live_g_structure.py::test_the_agent_tools_are_the_two_read_only_content_tools |
| Live lab shell-tool: Excluded on purpose: no agent tool or MCP tool can run a shell | architecture-walkthrough.md | - | - | tests/test_live_g_structure.py::test_no_agent_tool_or_mcp_tool_can_run_a_shell |
| Live lab mcp-basics: MCP tools are tenant scoped and checked by Cedar | adr/0028-machine-interfaces-share-one-front-door.md | - | - | tests/test_interfaces.py::test_mcp_tools_are_tenant_scoped_and_cedar_checked |
| Live lab mcp-trust: A tool whose description changed is not served | adr/0028-machine-interfaces-share-one-front-door.md | - | pin-mcp-tools-with-description-hashes | tests/test_live_i_mcp_pins.py::test_a_changed_description_disables_that_tool_and_only_that_tool |
| Live lab three-doors: Every API and v1 route refuses a caller without a verified token | adr/0028-machine-interfaces-share-one-front-door.md | - | - | tests/test_flow.py::test_every_api_and_v1_route_refuses_a_caller_without_a_verified_token |
| Live lab context-budget: A question too big for the budget goes to a person and is never cut | architecture-walkthrough.md | - | fit-the-thread-to-a-token-budget | tests/test_live_g_context.py::test_a_question_too_big_for_the_budget_goes_to_a_person_not_cut |
| Live lab history-trimming: A thread over the budget loses its oldest turns first | architecture-walkthrough.md | - | fit-the-thread-to-a-token-budget | tests/test_live_g_context.py::test_a_thread_over_the_budget_loses_its_oldest_turns_first |
| Live lab retrieval: Hybrid retrieval finds every answer that full text alone misses | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | - | retrieve-behind-a-facet-gate | tests/test_retrieval.py::test_hybrid_finds_every_answer_that_full_text_alone_misses |
| Live lab pick-context: The context for a question holds only that doctor's country and product | architecture-walkthrough.md | - | delegate-with-a-narrow-brief | tests/test_live_h_context.py::test_the_context_for_a_question_holds_only_that_doctors_country_and_product |
| Live lab instructions-vs-data: Inquiry text cannot close its own wrapper | architecture-walkthrough.md | - | - | tests/test_model_policy.py::test_inquiry_text_cannot_close_its_own_wrapper |
| Live lab stop-conditions: The kernel stops an attempt past the limit | adr/0013-a-policy-kernel-bounds-every-plan.md | - | bound-agent-plans-with-a-policy-kernel | tests/test_plan.py::test_the_kernel_stops_an_attempt_past_the_limit |
| Live lab error-feedback: A refused id is named in the next prompt and a clean first pick adds nothing | architecture-walkthrough.md | - | redraft-a-failed-check-once | tests/test_live_g_redraft.py::test_a_refused_id_is_named_in_the_next_prompt_and_a_clean_first_pick_adds_nothing |
| Live lab plan-then-act: A gap makes the plan search again, naming what is missing | architecture-walkthrough.md | - | bound-agent-plans-with-a-policy-kernel | tests/test_plan.py::test_a_gap_makes_the_plan_search_again_naming_what_is_missing |
| Live lab reflect-and-fix: A withdrawn block gets one redraft that can fix it | architecture-walkthrough.md | - | redraft-a-failed-check-once | tests/test_live_g_redraft.py::test_a_withdrawn_block_gets_one_redraft_that_can_fix_it |
| Live lab run-state: Another worker resumes a case from Temporal history without repeating a step | adr/0016-temporal-owns-the-life-of-a-case.md | - | keep-a-case-alive-with-temporal | tests/test_durable.py::test_another_worker_resumes_a_case_from_temporal_history_without_repeating_a_step |
| Live lab tool-failures: The tool guard blocks other countries and unknown tools | architecture-walkthrough.md | - | guard-tool-calls-with-cedar | tests/test_rules.py::test_tool_guard_blocks_other_countries_and_unknown_tools |
| Live lab crash-and-resume: A workflow reaches the same route, facts and ledger as the in-process run | adr/0016-temporal-owns-the-life-of-a-case.md | - | keep-a-case-alive-with-temporal | tests/test_durable.py::test_a_workflow_reaches_the_same_route_facts_and_ledger_as_the_in_process_run |
| Live lab budgets: A case at the hop cap makes no further call | adr/0019-one-thin-gateway-meters-every-model-call.md | - | cap-model-calls-per-case-and-day | tests/test_live_g_caps.py::test_a_case_at_the_hop_cap_makes_no_further_call |
| Live lab budgets: Workers racing for the last calls of the day cannot pass the cap | adr/0019-one-thin-gateway-meters-every-model-call.md | - | cap-model-calls-per-case-and-day | tests/test_atomic_day_cap.py::test_ten_workers_racing_for_five_calls_leave_exactly_five_through |
| Live lab budgets: A run that ends in review is still charged for its calls | adr/0019-one-thin-gateway-meters-every-model-call.md | - | cap-model-calls-per-case-and-day | tests/test_atomic_day_cap.py::test_a_run_that_fails_twice_and_goes_to_review_is_charged_for_both_calls |
| Sign-in accepts a token from a clock a few seconds ahead | adr/0010-signed-tokens-and-server-side-tenant.md | - | - | tests/test_clock_skew.py::test_a_token_from_a_clock_a_few_seconds_ahead_is_accepted |
| Compliance revokes and reinstates a user from the API and the CLI | adr/0010-signed-tokens-and-server-side-tenant.md | - | - | tests/test_revocation_routes.py::test_compliance_revokes_a_user_and_the_next_call_with_their_token_is_refused_until_they_are_reinstated |
| A block that fails the check after a tool runs never reaches the model | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | - | - | tests/test_post_tool.py::test_a_block_for_another_country_is_dropped_and_the_ledger_says_so |
| Live lab model-routing: The call retries once on Sonnet, then escalates | adr/0008-model-router.md | - | pick-the-model-with-a-router | tests/test_router.py::test_the_call_retries_once_on_sonnet_then_escalates |
| Live lab identity-and-scopes: A reviewer approves only in their own country | adr/0010-signed-tokens-and-server-side-tenant.md | - | guard-tool-calls-with-cedar | tests/test_flow.py::test_reviewer_approves_only_in_their_own_country |
| Live lab act-for-user: No API or MCP handler touches a service credential | adr/0028-machine-interfaces-share-one-front-door.md | - | - | tests/test_live_i_act_for_user.py::test_no_api_or_mcp_handler_touches_a_service_credential |
| Live lab hooks: Every tool call is on the ledger with its guard decision | adr/0004-cedar-for-every-permission.md | - | guard-tool-calls-with-cedar | tests/test_flow.py::test_every_tool_call_is_on_the_ledger_with_its_guard_decision |
| Live lab traces-and-audit: A case is one trace with a child per step | adr/0027-one-trace-per-case-with-pii-redacted.md | - | prove-the-audit-trail-with-a-hash-chain | tests/test_tracing.py::test_a_case_is_one_trace_with_a_child_per_step |
| Live lab evals-and-release: The eval gate blocks a release that regresses | adr/0025-a-release-is-a-hash-and-must-beat-its-baseline.md | - | gate-releases-with-evals | tests/test_releases.py::test_the_eval_gate_blocks_a_release_that_regresses |
| Live lab routing: Step Functions route like the Python graph | architecture-walkthrough.md | - | route-inquiries-with-a-routing-table | tests/test_graph.py::test_step_functions_on_floci_route_like_python |
| Live lab chain-and-delegate: An answer naming a block outside the brief is refused and written to the ledger | adr/0032-agents-talk-through-state-and-events-not-to-each-other.md | - | delegate-with-a-narrow-brief | tests/test_live_h_context.py::test_an_answer_naming_a_block_outside_the_brief_is_refused_and_written_to_the_ledger |
| Live lab parallel-workers: A slow worker and a failing worker do not block the others | architecture-walkthrough.md | - | - | tests/test_live_h_workers.py::test_a_slow_worker_and_a_failing_worker_do_not_block_the_others |
| The steward sweeps every doctor of every tenant each cycle | architecture-walkthrough.md | - | - | tests/test_handoff_schedule.py::test_the_sweep_task_covers_every_tenant_and_every_doctor |
| Live lab subagent-isolation: A delegated step gets only the narrow brief, never the case or the doctor | adr/0032-agents-talk-through-state-and-events-not-to-each-other.md | - | delegate-with-a-narrow-brief | tests/test_live_h_context.py::test_a_delegated_step_gets_only_the_narrow_brief_never_the_case_or_the_doctor |
| Live lab handoffs: A handoff is written to the ledger and read once by the receiver | architecture-walkthrough.md | - | - | tests/test_live_h_handoff_db.py::test_a_handoff_is_written_to_the_ledger_and_read_once_by_the_receiver |
| Live lab shared-memory: A note that went stale or crossed a tenant is never read | architecture-walkthrough.md | - | - | tests/test_live_h_memory.py::test_a_note_that_went_stale_or_crossed_a_tenant_is_never_read |
| Erasing a doctor wipes their shared memory notes | adr/0015-sealed-ledger-data-and-erasure-by-key-deletion.md | - | - | tests/test_live_h_handoff_db.py::test_erasing_a_doctor_wipes_their_shared_memory_notes |
| Live lab wakeups-and-board: The always-on steward invalidates a draft when content is withdrawn | adr/0018-a-steward-watches-content-and-a-cache-only-ever-forgets.md | - | watch-with-the-sentinel-and-steward | tests/test_cache.py::test_the_always_on_steward_invalidates_a_draft_when_content_is_withdrawn |
| Live lab hcp-360: A landed interaction joins the 360 of its doctor and unknowns wait for a human | adr/0022-unknown-handles-stay-unlinked.md | - | - | tests/test_identity.py::test_a_landed_interaction_joins_the_360_of_its_doctor_and_unknowns_wait_for_a_human |
| Live lab phi-vault: The model reads tokens for a doctor and the case keeps the real name | adr/0015-sealed-ledger-data-and-erasure-by-key-deletion.md | - | tokenise-phi-with-a-vault | tests/test_live_i_phi_vault.py::test_the_model_reads_tokens_for_a_doctor_and_the_case_keeps_the_real_name |
| Live lab fact-checker: An invented sentence is flagged | architecture-walkthrough.md | - | ground-replies-with-approved-blocks | tests/test_factcheck.py::test_an_invented_sentence_is_flagged |
| Live lab revocation: A revoked user is refused on the next call on every machine route | adr/0010-signed-tokens-and-server-side-tenant.md | - | - | tests/test_live_i_revocation.py::test_a_revoked_user_is_refused_on_the_next_call_on_every_machine_route |
| Live lab end-to-end: The whole flow runs and an auto send records a touch on the doctor's timeline | architecture-walkthrough.md | - | - | tests/test_flow.py::test_auto_send_records_a_touch_on_the_hcp_timeline |

## Blueprint gaps

| Requirement | Doc | Screen | Lab | Test |
|---|---|---|---|---|
| A failed safety model never drops a rule hit | architecture-walkthrough.md | - | keep-safety-intake-moving-with-a-manual-queue | tests/test_safety_floor.py::test_a_failing_safety_model_still_keeps_the_rule_hit |
| A silent detector hands every note to a person | architecture-walkthrough.md | - | keep-safety-intake-moving-with-a-manual-queue | tests/test_safety_clock.py::test_a_down_detector_sends_every_note_to_manual_screening_and_drops_none |
| A safety intake is acknowledged within one business day | architecture-walkthrough.md | - | keep-safety-intake-moving-with-a-manual-queue | tests/test_safety_clock.py::test_the_acknowledgment_is_due_one_business_day_later |
| Commercial data cannot reach medical or safety zones | architecture-walkthrough.md | /hcp | split-data-into-zones | tests/test_zones.py::test_the_commercial_role_cannot_read_or_write_the_medical_and_safety_zones |
| A hold crosses zones with no case id | architecture-walkthrough.md | /hcp | split-data-into-zones | tests/test_zones.py::test_an_open_case_holds_promotion_and_the_commercial_view_never_names_it |
| Only medical roles get the medical view | architecture-walkthrough.md | /hcp | split-data-into-zones | tests/test_zones.py::test_cedar_gives_reviewers_the_medical_view_and_reps_the_commercial_one |
| Agent modules reach no database | architecture-walkthrough.md | - | - | tests/test_zones.py::test_agent_modules_import_no_database_layer |
| A rep never gets an answer meant for doctors | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | - | retrieve-behind-a-facet-gate | tests/test_content_firewall.py::test_a_rep_never_gets_a_doctor_only_answer |
| The chatbot gets only its own script, word for word | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | - | retrieve-behind-a-facet-gate | tests/test_content_firewall.py::test_the_chatbot_gets_only_its_own_script_word_for_word |
| Every block names its type and who may see it | adr/0012-hybrid-retrieval-behind-a-hard-facet-gate.md | /content | - | tests/test_content_firewall.py::test_every_block_names_a_type_and_who_may_see_it |
| A signature covers one exact reply | adr/0017-a-reviewer-wait-is-a-workflow-with-a-deadline-and-a-signature.md | /review | bind-the-signature-to-the-reply | tests/test_approval_binding.py::test_an_approval_keeps_the_digest_the_release_and_the_draft_version |
| A reply changed after signing is never sent | adr/0017-a-reviewer-wait-is-a-workflow-with-a-deadline-and-a-signature.md | /review | bind-the-signature-to-the-reply | tests/test_approval_binding.py::test_a_reply_changed_after_signing_is_never_sent_and_the_ledger_says_so |
| A withdrawal closes the draft before anyone signs it | adr/0017-a-reviewer-wait-is-a-workflow-with-a-deadline-and-a-signature.md | /review | bind-the-signature-to-the-reply | tests/test_approval_binding.py::test_a_withdrawal_closes_the_draft_before_a_reviewer_can_sign_it |
| A blocked send and a rejection both reach the ledger | adr/0017-a-reviewer-wait-is-a-workflow-with-a-deadline-and-a-signature.md | /review | - | tests/test_approval_binding.py::test_a_rejection_is_on_the_ledger |
| Nothing about a doctor reaches the model client | adr/0015-sealed-ledger-data-and-erasure-by-key-deletion.md | - | tokenise-phi-with-a-vault | tests/test_wire_privacy.py::test_no_doctor_name_email_phone_or_id_reaches_the_model_client |
| Free text is screened for patient names, birth dates and addresses | adr/0015-sealed-ledger-data-and-erasure-by-key-deletion.md | - | tokenise-phi-with-a-vault | labs/tokenise-phi-with-a-vault/test_phi_vault.py::test_step_5_a_patient_name_a_birth_date_and_an_address_are_tokens_too |
| The blueprint tables cannot drift from the code | blueprint.md | - | - | tests/test_blueprint.py::test_the_view_matrix_matches_cedar_and_covers_every_role |
