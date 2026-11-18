"""Parallel workers: one slow or failing worker never blocks the others, and every failure is recorded."""

import threading

from hcpagents import parallel, sentinel


def test_a_slow_worker_and_a_failing_worker_do_not_block_the_others():
    release = threading.Event()
    rows = []

    def slow() -> int:
        release.wait(5)
        return 1

    def broken() -> int:
        raise RuntimeError("the channel is down")

    out = parallel.fan_out({"slow": slow, "broken": broken, "fine": lambda: 7}, timeout_s=0.3, record=rows.append)
    release.set()
    assert out["results"] == {"fine": 7}
    assert set(out["failed"]) == {"slow", "broken"}
    assert "RuntimeError: the channel is down" in out["failed"]["broken"]
    assert {row["worker"] for row in rows} == {"slow", "broken"}
    assert all(row["type"] == "worker_failed" for row in rows)


def test_the_workers_run_at_the_same_time():
    both = threading.Barrier(2, timeout=2)
    out = parallel.fan_out({"a": both.wait, "b": both.wait}, timeout_s=3, record=lambda entry: None)
    assert out["failed"] == {} and set(out["results"]) == {"a", "b"}


def test_the_sentinel_scans_each_doctor_in_its_own_worker(monkeypatch):
    def sweep(hcp_id: str) -> int:
        if hcp_id == "hcp-bad":
            raise RuntimeError("no connection")
        return 2

    rows = []
    monkeypatch.setattr(sentinel, "_sweep", sweep)
    monkeypatch.setattr(sentinel.ledger, "append", rows.append)
    out = sentinel.scan_doctors(["hcp-a", "hcp-bad", "hcp-c"], timeout_s=2)
    assert out["results"] == {"hcp-a": 2, "hcp-c": 2}
    assert list(out["failed"]) == ["hcp-bad"] and rows[0]["worker"] == "hcp-bad"
