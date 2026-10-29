"""The CDK app: `cdk synth` writes the CloudFormation for the platform. Nothing here deploys (ADR 0029)."""

import os

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks

from stack import Platform

app = cdk.App()
Platform(app, "HcpPlatform", env=cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT", "123456789012"), region="eu-central-1"))
cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app))
app.synth()
