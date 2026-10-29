# ADR 0029: The platform is one CDK stack, checked at synth, never deployed from here

Status: accepted, 29 October 2026.

## Context

A regulated platform has to show where its data lives, who can reach it and which models it may call.
A diagram can drift from what runs. Deploying to a real account from a teaching repo costs money and
needs credentials that must not sit here.

## Decision

- **One stack in Python CDK** (`deploy/stack.py`), read top to bottom: network, one KMS key and one
  Object Lock ledger bucket per tenant, Aurora Postgres (Serverless v2, private subnets), a Valkey
  serverless cache, a Cognito user pool with required MFA, a Verified Permissions store loaded from
  `policies/cedar/*.cedar`, and ECS Fargate for the api and the worker.
- **Per-tenant keys.** Erasing a tenant is destroying its key, which is how the ledger honours GDPR
  erasure while Object Lock keeps its entries (ADR 0015).
- **Bedrock for two models.** The task role may call Bedrock for Haiku 5.5 and Sonnet 5.5 only, and
  `tests/test_deploy.py` reads the synthesized policy to prove it.
- **cdk-nag fails the synth.** `AwsSolutionsChecks` runs at `app.synth()`; any finding raises, so
  `make check` cannot pass with one. Every acknowledged finding names its reason in the stack. A
  counter-test shows the plugin refuses a bad stack.
- **CI runs the same gate** plus a secret scan (gitleaks), a dependency audit (pip-audit), a CycloneDX
  SBOM and CodeQL (`.github/workflows/ci.yml`). A nightly run catches a new advisory without a push.
  `tests/test_ci.py` fails if a step is dropped.
- **Synth only.** Nothing deploys from this repo. The two secrets (the Anthropic key and the
  `hcp_app` database URL) are created empty and filled in by hand.

## Consequences

- The picture and the template cannot disagree: tests read the template.
- Temporal is an input (`-c temporal=host:7233`): Temporal Cloud or a self-hosted cluster, not part of
  this stack. ECS was chosen over EKS because the platform is two stateless services and one worker;
  nothing needs a cluster operator.
- Not built: a migration job task, blue/green deploys, a second region for residency, and a Bedrock
  failover adapter in the gateway.
