"""The platform on AWS, one stack read top to bottom: network, keys, data, identity, policy, compute.

Each tenant gets its own KMS key and its own locked ledger bucket, so one tenant's data can be erased
by destroying its key. The task role may call Bedrock for the two allowed models and no others.
"""

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_bedrock as bedrock,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as patterns,
    aws_elasticache as elasticache,
    aws_iam as iam,
    aws_kms as kms,
    aws_logs as logs,
    aws_rds as rds,
    aws_s3 as s3,
    aws_secretsmanager as secrets,
    aws_verifiedpermissions as avp,
)
from constructs import Construct

ROOT = Path(__file__).resolve().parent.parent
TENANTS = ("quillon", "marlowe")
MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")  # the two allowed models (ADR 0007)
LEDGER_RETENTION_YEARS = 7


def suppress(node: Construct, rule: str, reason: str) -> None:
    """Acknowledge one cdk-nag finding on one construct, with the reason it is acceptable."""
    cdk.Validations.of(node).acknowledge(cdk.Acknowledgment(id=rule, reason=reason))


class Platform(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kw):
        super().__init__(scope, id, **kw)
        self.vpc = self.network()
        self.app_sg = ec2.SecurityGroup(self, "AppSg", vpc=self.vpc, description="Tasks that run the platform")
        self.keys = {t: kms.Key(self, f"Key-{t}", enable_key_rotation=True, alias=f"alias/hcp-{t}") for t in TENANTS}
        self.logs_bucket = self.access_logs()
        self.ledgers = {t: self.ledger(t) for t in TENANTS}
        self.database = self.postgres()
        self.cache = self.valkey()
        self.users = self.identity()
        self.policies = self.cedar()
        self.compute()

    def network(self) -> ec2.Vpc:
        vpc = ec2.Vpc(
            self, "Vpc", max_azs=2, nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="app", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
                ec2.SubnetConfiguration(name="data", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24),
            ],
            flow_logs={"all": ec2.FlowLogOptions(destination=ec2.FlowLogDestination.to_cloud_watch_logs())})
        return vpc

    def access_logs(self) -> s3.Bucket:
        b = s3.Bucket(self, "AccessLogs", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
                      encryption=s3.BucketEncryption.S3_MANAGED, versioned=True, removal_policy=cdk.RemovalPolicy.RETAIN)
        suppress(b, "AwsSolutions-S1", "This is the access-log bucket; logging it would only point at itself.")
        return b

    def ledger(self, tenant: str) -> s3.Bucket:
        """WORM storage for the hash-chained ledger: nobody, including an admin, edits an entry in its retention."""
        return s3.Bucket(
            self, f"Ledger-{tenant}", object_lock_enabled=True,
            object_lock_default_retention=s3.ObjectLockRetention.compliance(cdk.Duration.days(365 * LEDGER_RETENTION_YEARS)),
            encryption=s3.BucketEncryption.KMS, encryption_key=self.keys[tenant], bucket_key_enabled=True,
            versioned=True, block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            server_access_logs_bucket=self.logs_bucket, server_access_logs_prefix=f"ledger-{tenant}/",
            removal_policy=cdk.RemovalPolicy.RETAIN)

    def postgres(self) -> rds.DatabaseCluster:
        db = rds.DatabaseCluster(
            self, "Postgres", engine=rds.DatabaseClusterEngine.aurora_postgres(version=rds.AuroraPostgresEngineVersion.VER_16_4),
            writer=rds.ClusterInstance.serverless_v2("writer"), serverless_v2_min_capacity=0.5, serverless_v2_max_capacity=4,
            vpc=self.vpc, vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            storage_encrypted=True, iam_authentication=True, deletion_protection=True, backup=rds.BackupProps(retention=cdk.Duration.days(14)),
            cloudwatch_logs_exports=["postgresql"], removal_policy=cdk.RemovalPolicy.RETAIN)
        db.add_rotation_single_user(automatically_after=cdk.Duration.days(30))
        suppress(db, "AwsSolutions-RDS6", "The app role signs in with a password held in Secrets Manager (DATABASE_URL); IAM authentication is enabled for operators.")
        suppress(db, "AwsSolutions-SMG4", "Rotation is added with add_rotation_single_user above.")
        return db

    def valkey(self) -> elasticache.CfnServerlessCache:
        sg = ec2.SecurityGroup(self, "CacheSg", vpc=self.vpc, description="Valkey: reachable from the app subnets only")
        sg.add_ingress_rule(self.app_sg, ec2.Port.tcp(6379), "app to Valkey")
        return elasticache.CfnServerlessCache(
            self, "Valkey", engine="valkey", serverless_cache_name="hcp-cache", security_group_ids=[sg.security_group_id],
            subnet_ids=self.vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED).subnet_ids)

    def identity(self) -> cognito.UserPool:
        pool = cognito.UserPool(
            self, "Users", self_sign_up_enabled=False, mfa=cognito.Mfa.REQUIRED, mfa_second_factor=cognito.MfaSecondFactor(otp=True, sms=False),
            password_policy=cognito.PasswordPolicy(min_length=14, require_digits=True, require_symbols=True, require_lowercase=True, require_uppercase=True),
            feature_plan=cognito.FeaturePlan.PLUS, standard_threat_protection_mode=cognito.StandardThreatProtectionMode.FULL_FUNCTION, removal_policy=cdk.RemovalPolicy.RETAIN,
            custom_attributes={"tenant": cognito.StringAttribute(mutable=False), "role": cognito.StringAttribute(mutable=True)})
        # a signed-in user may not write their own role or tenant, so the claims Cedar reads stay admin-only
        pool.add_client("Console", auth_flows=cognito.AuthFlow(user_srp=True), generate_secret=False,
                        write_attributes=cognito.ClientAttributes().with_standard_attributes(fullname=True))
        return pool

    def cedar(self) -> avp.CfnPolicyStore:
        """Every policy file in policies/cedar becomes one Verified Permissions policy."""
        store = avp.CfnPolicyStore(self, "Policies", validation_settings=avp.CfnPolicyStore.ValidationSettingsProperty(mode="OFF"))
        for f in sorted((ROOT / "policies" / "cedar").glob("*.cedar")):
            avp.CfnPolicy(self, f"Policy-{f.stem}", policy_store_id=store.attr_policy_store_id, definition=avp.CfnPolicy.PolicyDefinitionProperty(
                static=avp.CfnPolicy.StaticPolicyDefinitionProperty(statement=f.read_text())))
        return store

    def task_role(self) -> iam.Role:
        role = iam.Role(self, "TaskRole", assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"))
        role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=[f"arn:aws:bedrock:*::foundation-model/anthropic.{m}*" for m in MODELS]
                      + [f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/*anthropic.{m}*" for m in MODELS]))
        role.add_to_policy(iam.PolicyStatement(actions=["verifiedpermissions:IsAuthorized"], resources=[self.policies.attr_arn]))
        for t in TENANTS:
            role.add_to_policy(iam.PolicyStatement(actions=["s3:PutObject", "s3:GetObject"], resources=[self.ledgers[t].arn_for_objects("*")]))
            role.add_to_policy(iam.PolicyStatement(actions=["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"], resources=[self.keys[t].key_arn]))
            logical = self.get_logical_id(self.ledgers[t].node.default_child)
            suppress(role, f"AwsSolutions-IAM5[Resource::<{logical}.Arn>/*]", f"{t} ledger: the task writes and reads entries by key, so the object path is the resource.")
        for m in MODELS:
            suppress(role, f"AwsSolutions-IAM5[Resource::arn:aws:bedrock:*::foundation-model/anthropic.{m}*]", f"{m}: the wildcard is the version suffix of one allowed model.")
            suppress(role, f"AwsSolutions-IAM5[Resource::arn:aws:bedrock:{self.region}:{self.account}:inference-profile/*anthropic.{m}*]", f"{m}: the regional inference profile of one allowed model.")
        return role

    def compute(self) -> None:
        cluster = ecs.Cluster(self, "Cluster", vpc=self.vpc, container_insights_v2=ecs.ContainerInsights.ENABLED)
        anthropic = secrets.Secret(self, "AnthropicKey", description="Filled in by hand after deploy; never in the template")
        suppress(anthropic, "AwsSolutions-SMG4", "A third-party API key cannot be rotated by AWS; rotation is a manual runbook step.")
        role = self.task_role()
        db_url = secrets.Secret(self, "DatabaseUrl", description="The hcp_app role URL; filled in by hand after the migration job creates the role")
        suppress(db_url, "AwsSolutions-SMG4", "The URL is rotated by changing the hcp_app password and this value together, a runbook step.")
        env = {"MI_VALKEY": f"valkeys://{self.cache.attr_endpoint_address}:6379/0", "MI_TEMPORAL": self.node.try_get_context("temporal") or "temporal.internal:7233"}
        keys = {"ANTHROPIC_API_KEY": ecs.Secret.from_secrets_manager(anthropic), "DATABASE_URL": ecs.Secret.from_secrets_manager(db_url)}
        image = ecs.ContainerImage.from_asset(str(ROOT))
        api = patterns.ApplicationLoadBalancedFargateService(
            self, "Api", cluster=cluster, cpu=512, memory_limit_mib=1024, desired_count=2, public_load_balancer=True,
            task_image_options=patterns.ApplicationLoadBalancedTaskImageOptions(
                image=image, container_port=8765, task_role=role, environment=env, enable_logging=True,
                secrets=keys),
            health_check_grace_period=cdk.Duration.seconds(60), security_groups=[self.app_sg])
        api.target_group.configure_health_check(path="/api/health")
        api.load_balancer.log_access_logs(self.logs_bucket, "alb")
        api.load_balancer.set_attribute("routing.http.drop_invalid_header_fields.enabled", "true")
        suppress(api.load_balancer, "AwsSolutions-EC23", "The load balancer is the public entry; the console and webhooks need 0.0.0.0/0 on the listener port.")
        suppress(api.load_balancer, "AwsSolutions-ELB2", "Access logs go to the shared log bucket via log_access_logs above.")
        suppress(api.task_definition, "AwsSolutions-ECS2", "Environment holds hostnames only; every secret comes from Secrets Manager.")
        suppress(api.task_definition.execution_role, "AwsSolutions-IAM5[Resource::*]", "ECR GetAuthorizationToken has no resource-level form.")
        worker = ecs.FargateService(
            self, "Worker", cluster=cluster, desired_count=2, security_groups=[self.app_sg], task_definition=self.worker_task(image, role, env, keys))
        self.database.connections.allow_default_port_from(api.service)
        self.database.connections.allow_default_port_from(worker)

    def worker_task(self, image, role, env, keys) -> ecs.FargateTaskDefinition:
        task = ecs.FargateTaskDefinition(self, "WorkerTask", cpu=512, memory_limit_mib=1024, task_role=role)
        task.add_container(
            "worker", image=image, command=["python", "-m", "hcpagents.worker"], environment=env,
            secrets=keys,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="worker", log_retention=logs.RetentionDays.ONE_YEAR))
        suppress(task, "AwsSolutions-ECS2", "Environment holds hostnames only; every secret comes from Secrets Manager.")
        suppress(task.execution_role, "AwsSolutions-IAM5[Resource::*]", "ECR GetAuthorizationToken has no resource-level form.")
        return task
