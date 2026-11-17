"""Signals for the platform. CloudWatch gets metrics for each route, the delay and the model cost.

Each case also gets one log line. The trace of a case lives on its record.
It holds steps with inputs, outputs and token use, in the shape Langfuse reads. Production can send it there as it is.
"""

import json
import time

from hcpagents.aws import client
from hcpagents.infra import LOG_GROUP

NAMESPACE = "MedicalInformation"


def metrics(case: dict) -> None:
    dims = [{"Name": "Country", "Value": case["country"] or "unknown"}]
    client("cloudwatch").put_metric_data(Namespace=NAMESPACE, MetricData=[
        {"MetricName": "CasesRouted", "Dimensions": dims + [{"Name": "Route", "Value": case["route"]}], "Value": 1, "Unit": "Count"},
        {"MetricName": "CaseLatency", "Dimensions": dims, "Value": case["latency_ms"], "Unit": "Milliseconds"},
        {"MetricName": "ModelCost", "Dimensions": dims, "Value": case["cost_usd"], "Unit": "None"},
    ])


def log(case: dict) -> None:
    line = {"case": case["id"], "route": case["route"], "country": case["country"], "product": case["product"],
            "rule": case["decision"]["rule"], "cost_usd": case["cost_usd"], "mode": case["mode"],
            "trace_id": case["trace"]["id"]}
    client("logs").put_log_events(logGroupName=LOG_GROUP, logStreamName="cases",
                                  logEvents=[{"timestamp": int(time.time() * 1000), "message": json.dumps(line)}])


def route_counts() -> dict[str, float]:
    """Sum of CasesRouted by route over the last day."""
    watch, out = client("cloudwatch"), {}
    now = time.time()
    for metric in watch.list_metrics(Namespace=NAMESPACE, MetricName="CasesRouted")["Metrics"]:
        route = next(found["Value"] for found in metric["Dimensions"] if found["Name"] == "Route")
        points = watch.get_metric_statistics(Namespace=NAMESPACE, MetricName="CasesRouted", Dimensions=metric["Dimensions"],
                                       StartTime=now - 86400, EndTime=now + 60, Period=86400, Statistics=["Sum"])["Datapoints"]
        out[route] = out.get(route, 0) + sum(point["Sum"] for point in points)
    return out
