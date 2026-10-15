"""Operational signals: CloudWatch metrics per route, latency and model cost, and one structured
log line per case. The per-case trace (spans with inputs, outputs and token use) lives on the case
record in the shape Langfuse ingests, so production can ship it there unchanged."""

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
    cw, out = client("cloudwatch"), {}
    now = time.time()
    for m in cw.list_metrics(Namespace=NAMESPACE, MetricName="CasesRouted")["Metrics"]:
        route = next(d["Value"] for d in m["Dimensions"] if d["Name"] == "Route")
        pts = cw.get_metric_statistics(Namespace=NAMESPACE, MetricName="CasesRouted", Dimensions=m["Dimensions"],
                                       StartTime=now - 86400, EndTime=now + 60, Period=86400, Statistics=["Sum"])["Datapoints"]
        out[route] = out.get(route, 0) + sum(p["Sum"] for p in pts)
    return out
