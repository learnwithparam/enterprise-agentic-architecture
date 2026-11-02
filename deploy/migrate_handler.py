"""Runs the database migration as a one-off ECS task and waits for it (ADR 0029).

CloudFormation calls on_event when the migration task definition changes (a new image), then polls
is_complete until the task stops. A non-zero exit code fails the resource, so the stack update that
would start the new service version never begins on a database the migration could not reach.
"""

import json

import boto3

ecs = None  # the Lambda runtime has credentials; importing this file in a test must not need any


def _ecs():
    global ecs
    ecs = ecs or boto3.client("ecs")
    return ecs


def on_event(event, _ctx=None):
    if event["RequestType"] == "Delete":
        return {"PhysicalResourceId": event["PhysicalResourceId"]}
    p = event["ResourceProperties"]
    out = _ecs().run_task(
        cluster=p["Cluster"], taskDefinition=p["TaskDefinition"], launchType="FARGATE", count=1,
        networkConfiguration={"awsvpcConfiguration": {
            "subnets": p["Subnets"], "securityGroups": p["SecurityGroups"], "assignPublicIp": "DISABLED"}})
    if out["failures"]:
        raise RuntimeError(f"The migration task did not start: {json.dumps(out['failures'])}")
    return {"PhysicalResourceId": out["tasks"][0]["taskArn"]}


def is_complete(event, _ctx=None):
    if event["RequestType"] == "Delete":
        return {"IsComplete": True}
    task = _ecs().describe_tasks(cluster=event["ResourceProperties"]["Cluster"], tasks=[event["PhysicalResourceId"]])["tasks"][0]
    if task["lastStatus"] != "STOPPED":
        return {"IsComplete": False}
    code = task["containers"][0].get("exitCode")
    if code != 0:
        raise RuntimeError(f"The migration exited with {code}: {task.get('stoppedReason', 'no reason given')}")
    return {"IsComplete": True}
