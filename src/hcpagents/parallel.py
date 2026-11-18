"""Run independent workers side by side. One slow or failing worker never blocks the others.

Each worker gets the same time limit. A worker that is late or raises is written to the ledger and left out of the results.
The others still finish. A late worker cannot be stopped, so its answer is dropped when it arrives.
"""

import contextvars
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait

from hcpagents import ledger

TIMEOUT_S = 10.0


def _reason(future) -> str:
    error = future.exception()
    return f"{type(error).__name__}: {error}"[:200]


def fan_out(jobs: dict[str, Callable[[], object]], timeout_s: float = TIMEOUT_S, record: Callable[[dict], object] | None = None) -> dict:
    """Run every job at once. Gives back results by name and a reason for each job that failed or ran late."""
    record = record or ledger.append
    if not jobs:
        return {"results": {}, "failed": {}}
    pool = ThreadPoolExecutor(max_workers=len(jobs))
    # Each worker runs in a copy of this context, so it acts for the same tenant.
    futures = {name: pool.submit(contextvars.copy_context().run, job) for name, job in jobs.items()}
    wait(futures.values(), timeout=timeout_s)
    pool.shutdown(wait=False, cancel_futures=True)
    results, failed = {}, {}
    for name, future in futures.items():
        if not future.done():
            failed[name] = f"No answer after {timeout_s} seconds"
        elif future.exception() is not None:
            failed[name] = _reason(future)
        else:
            results[name] = future.result()
    for name, reason in failed.items():
        record({"type": "worker_failed", "agent": "parallel-workers", "worker": name, "reason": reason})
    return {"results": results, "failed": failed}
