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
- **A migration task runs before the service.** `MigrationTask` is a one-off Fargate task that runs
  `python -m hcpagents.db` with the cluster owner's credentials. A custom resource starts it whenever the
  image changes and waits for it; a non-zero exit fails the stack update, and both services depend on that
  resource, so no new task starts on an old schema. `tests/test_deploy.py` reads the template for the edge.
- **Blue/green through CodeDeploy.** The API service uses the CodeDeploy deployment controller with a green
  target group and a test listener on port 9000. The group shifts 10 percent of traffic, waits five minutes,
  then shifts the rest, and rolls back a failed deployment.
- **A second region keeps the ledger.** `SecondRegion` holds one locked, encrypted bucket per tenant in
  `eu-west-1`; each ledger bucket replicates into it. S3 names are global, so the copy carries its region in
  its name (`replica_bucket`). Replication keeps the retention rule, and the test asserts both buckets lock.
- **The app role's password is a secret.** `mi/db/hcp_app` holds the role's host, port and a generated
  password. The app reads it at boot and the migration sets it on the role, so there is no password in a file
  or an environment variable (`tests/test_env.py`). The stack creates the same name on AWS.
- **The console's policy comes from the API.** The console is a static export, so `next.config` headers never
  apply; the API sends `Content-Security-Policy` with each page, allowing this origin and the page's own inline
  bootstrap scripts by hash. `web/scripts/check-csp.mjs` loads every route and fails on a violation.
- **Synth only.** Nothing deploys from this repo. The Anthropic key secret is created empty and filled in by hand.

## Consequences

- The picture and the template cannot disagree: tests read the template.
- Temporal is an input (`-c temporal=host:7233`): Temporal Cloud or a self-hosted cluster, not part of
  this stack. ECS was chosen over EKS because the platform is two stateless services and one worker;
  nothing needs a cluster operator.
- Not deployed: the stacks synthesize and are checked, and the migration handler runs against a fake
  ECS client. Running them on AWS needs an account (see Known limits in the case study).
