# ADR 0029: The platform is one CDK stack, checked at synth, never deployed from here

Status: accepted, 29 October 2026.

## Context

A regulated platform has to show where its data lives. It must show who can reach it and which models it may call. A diagram can drift from what runs. Deploying to a real account from a teaching repo costs money. It also needs credentials that must not sit here.

## Decision

- **One stack in Python CDK** (`deploy/stack.py`), read top to bottom. It has the network. It has one KMS key and one
  Object Lock ledger bucket per tenant. It has Aurora Postgres (Serverless v2, private subnets) and a Valkey
  serverless cache. It has a Cognito user pool with required MFA. It has a Verified Permissions store loaded from
  `policies/cedar/*.cedar`. It has ECS Fargate for the api and the worker.
- **Per-tenant keys.** Erasing a tenant means destroying its key. That is how the ledger honours GDPR
  erasure while Object Lock keeps its entries (ADR 0015).
- **Bedrock for two models.** The task role may call Bedrock for Haiku 5.5 and Sonnet 5.5 only.
  `tests/test_deploy.py` reads the synthesized policy to prove it.
- **cdk-nag fails the synth.** `AwsSolutionsChecks` runs at `app.synth()`. Any finding raises. So
  `make check` cannot pass with one. Every acknowledged finding names its reason in the stack. A
  counter-test shows the plugin refuses a bad stack.
- **CI runs the same gate.** It adds a secret scan (gitleaks), a dependency audit (pip-audit), a CycloneDX
  SBOM and CodeQL (`.github/workflows/ci.yml`). A nightly run catches a new advisory without a push.
  `tests/test_ci.py` fails if a step is dropped.
- **A migration task runs before the service.** `MigrationTask` is a one-off Fargate task. It runs
  `python -m hcpagents.db` with the cluster owner's credentials. A custom resource starts it whenever the
  image changes and waits for it. A non-zero exit fails the stack update. Both services depend on that
  resource. So no new task starts on an old schema. `tests/test_deploy.py` reads the template for the edge.
- **Blue/green through CodeDeploy.** The API service uses the CodeDeploy deployment controller. It has a green
  target group and a test listener on port 9000. The group shifts 10 percent of traffic and waits five minutes.
  Then it shifts the rest. It rolls back a failed deployment.
- **A second region keeps the ledger.** `SecondRegion` holds one locked, encrypted bucket per tenant in
  `eu-west-1`. Each ledger bucket replicates into it. S3 names are global. So the copy carries its region in
  its name (`replica_bucket`). Replication keeps the retention rule. The test asserts both buckets lock.
- **The app role's password is a secret.** `mi/db/hcp_app` holds the role's host, port and a generated
  password. The app reads it at boot. The migration sets it on the role. So there is no password in a file
  or an environment variable (`tests/test_env.py`). The stack creates the same name on AWS.
- **The console's policy comes from the API.** The console is a static export. So `next.config` headers never
  apply. The API sends `Content-Security-Policy` with each page. It allows this origin. It allows the page's own inline
  bootstrap scripts by hash. `web/scripts/check-csp.mjs` loads every route and fails on a violation.
- **Synth only.** Nothing deploys from this repo. The Anthropic key secret is created empty and filled in by hand.

## Consequences

- The picture and the template cannot disagree. Tests read the template.
- Temporal is an input (`-c temporal=host:7233`). It is Temporal Cloud or a self-hosted cluster. It is not part of
  this stack. ECS was chosen over EKS because the platform is two stateless services and one worker.
  Nothing needs a cluster operator.
- Not deployed. The stacks synthesize and are checked. The migration handler runs against a fake
  ECS client. Running them on AWS needs an account (see Known limits in the case study).
