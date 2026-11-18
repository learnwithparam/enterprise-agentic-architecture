# ADR 0031: One codebase, two services today, and ECS rather than microservices on Kubernetes

Status: accepted, 30 October 2026.

## Context

The platform has an API, a Temporal worker, an MCP server and an ingestion path. A reader from a large company will ask two things. Is each one a microservice? Does each belong on Kubernetes? The team that runs this is small. Every moving part is one more thing to patch, watch and explain to Compliance.

## Decision

- **A modular monolith.** One Python package, `hcpagents`, holds every agent, the policy kernel and the
  stores. Modules call each other as functions. So a safety check cannot be skipped by a network hop.
- **Two services from one image today.** `api` serves the console API, `/v1`, `/mcp` and the channel
  webhooks. `worker` (`python -m hcpagents.worker`) runs Temporal workflows and activities. The CDK stack
  has one Fargate service for each. MCP and ingestion are modules mounted in the API. They are not services.
- **ECS Fargate, not EKS.** The stateless services need a load balancer, a task role and autoscaling. They
  do not need operators, custom schedulers or a service mesh. The CDK stack in ADR 0029 states this.
- **Postgres, not DynamoDB, for state.** Row-level security and joins decide this (ADR 0009). The ledger
  keeps DynamoDB and S3 Object Lock because it is append-only.

## Consequences

- One version of the kernel is deployed everywhere. A policy change is one image and one release id.
- MCP and ingestion can become their own entrypoints of the same image. That can happen when their load or
  blast radius asks for it. Modules only talk through their public functions and the event bus.
- No second region, blue/green or migration task is in the stack yet. They are listed as limits.

## Alternatives rejected

- **Microservice per agent.** Rejected: that is eight network boundaries. Each needs its own authentication,
  tracing and tenant propagation. It would protect nothing that the module boundary does not already protect.
- **EKS.** Rejected: the cluster is the largest cost and the largest attack surface, for two services.
