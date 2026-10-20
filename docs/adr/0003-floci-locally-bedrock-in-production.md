# ADR 0003: Floci locally, AWS and Bedrock in production

Status: accepted, 15 October 2026

## Context

The buildcamp project must run on a laptop with one command and no cloud account, and the
code must be the code that runs on AWS. Mocks diverge from the service; a shared dev account costs money and
needs credentials.

## Decision

Every AWS service runs on Floci, a local AWS emulator, through ordinary boto3 clients pointed at
`localhost:4566` (`hcpagents.aws`). `make up` starts it and provisions every resource. In production the
same code points at AWS, and the model call moves from the Agent SDK's API endpoint to Claude on Amazon
Bedrock in the data's region.

## Options considered

- **moto or hand-written fakes.** Rejected: in-process fakes do not exercise Step Functions or Object Lock.
- **A dev AWS account.** Rejected for the demo: cost, credentials and network.
- **Floci.** Chosen. It covers DynamoDB, S3 Object Lock, KMS signing, SQS, EventBridge, SSM, Step Functions,
  Verified Permissions, Cognito and CloudWatch, which is every service this slice uses.

## Consequences

Anyone can run the platform offline. A service Floci does not emulate faithfully would need a test on
real AWS before production.

## Enforced by

`tests/test_flow.py` and `tests/test_graph.py` run against Floci and are skipped with a reason, not
passed, when it is down.
