# What Floci covers

The platform runs its AWS code against [Floci](https://floci.io/) 2.3.0 on `localhost:4566`, so the labs need no AWS account. This page records what was probed against that image, so a lab never claims a service the emulator does not answer. The probe made one real call per service in `us-east-1` and `eu-west-1`.

| Service | Used for | Floci | Evidence |
|---|---|---|---|
| Bedrock Runtime | Second model provider | Answers Converse; the reply is a stub | `converse` returns `Floci stub response for model=<id>` and accepts any model id |
| CloudFormation | The CDK stack | Deploys in both regions | `cloudformation deploy` ends `UPDATE_COMPLETE`; S3 bucket names are global, so a second region needs its own bucket name |
| ECS | Task definitions, migration task | Registers task definitions | `register-task-definition` returns the ARN in both regions |
| CodeDeploy | Blue/green deploy group | Lists applications | `list-applications` answers |
| Cognito | Sign-in, tenant claim | Pools, clients, custom attributes, JWKS, OpenID configuration, authorize and token endpoints | `/<pool>/.well-known/jwks.json` returns an RSA key set; `admin-create-user` accepts `custom:tenant` |
| Secrets Manager | The `hcp_app` password | Create and read | `create-secret` then `get-secret-value` |
| SQS | One work queue per tenant | Create and list | `create-queue` |
| S3 | Ledger bucket | Create and list | `list-buckets` |
| Verified Permissions | Cedar policies | Policy stores | `list-policy-stores` answers |

## Limits that remain

- A live Bedrock model answer needs an AWS account. Floci returns a stub, so the labs prove failover and the request translation, not the model's words.
- Cognito has no device-code grant, here or on AWS. The `hcp` CLI signs in with the authorization code flow and PKCE against a loopback redirect.
