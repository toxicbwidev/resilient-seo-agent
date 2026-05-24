"""Watchdog timer for zombie-state detection.

A step is "zombie" when it has not failed and not finished — the
operation is alive but making no progress. Common causes: the model
provider stops streaming mid-response, an MCP tool server hangs in a
syscall, the network read returns nothing but doesn't close. Retry
loops never fire because there is no exception.

This module wraps any callable in a watchdog timer. If the callable
doesn't return within the timeout, ZombieStepDetected is raised and
the pipeline's normal retry path takes over.

Implementation note: Python has no safe way to kill a busy thread. If
the underlying call truly never returns, the worker thread leaks until
process exit. The agent's *state* is preserved (we never lose the
checkpoint), and the pipeline can resume cleanly — but a long-running
deployment should treat a recurring watchdog trip as a signal to
restart the worker. This trade-off is documented in
docs/failure-modes.md.
"""
from __future__ import annotations

import concurrent.futures
import contextvars
from typing import Callable, TypeVar

T = TypeVar("T")


class ZombieStepDetected(TimeoutError):
    """A wrapped callable did not return within the watchdog timeout."""

    def __init__(self, step_name: str, timeout_sec: float) -> None:
        super().__init__(
            f"step {step_name!r} exceeded watchdog timeout of {timeout_sec:.2f}s "
            f"(no exception, no return — zombie state)"
        )
        self.step_name = step_name
        self.timeout_sec = timeout_sec


def call_with_watchdog(
    fn: Callable[[], T],
    timeout_sec: float,
    step_name: str = "<unknown>",
) -> T:
    """Run fn() in a worker thread, cancel via timeout if it hangs.

    Returns the value fn() returned, or re-raises whatever fn() raised.
    If fn() takes longer than timeout_sec, raises ZombieStepDetected.

    The worker thread is *not* killed on timeout — Python can't safely
    interrupt a busy thread. The thread keeps running in the background;
    callers should treat a watchdog trip as a hint to restart the process
    after the run completes. For agent-level resilience this is fine:
    state is on disk, the pipeline retries, and the leaked thread dies
    with the process.
    """
    if timeout_sec <= 0:
        return fn()
    # Don't use `with` here — ThreadPoolExecutor.__exit__ calls
    # shutdown(wait=True), which blocks until the hung thread returns. That
    # defeats the entire purpose of a watchdog. We manage shutdown manually
    # and pass wait=False so the caller can move on while the zombie thread
    # leaks (a documented trade-off — see module docstring).
    # Propagate the caller's contextvars (e.g. failover_client.current_step_var
    # set by pipeline._run_one_step) into the worker thread. Without this,
    # the worker starts with an empty Context and downstream telemetry
    # callbacks lose attribution. copy_context().run also isolates worker
    # mutations from the caller — symmetric with what Future itself promises.
    ctx = contextvars.copy_context()
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = ex.submit(ctx.run, fn)
        try:
            return future.result(timeout=timeout_sec)
        except concurrent.futures.TimeoutError as exc:
            raise ZombieStepDetected(step_name, timeout_sec) from exc
    finally:
        ex.shutdown(wait=False)
