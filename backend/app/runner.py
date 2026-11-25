"""Background run execution.

HTTP handlers must not execute agents. A run takes seconds to minutes,
may pause at an approval gate, and may retry a flaky model; doing that
inside the request means a proxy timeout kills work that already happened
and the client cannot show progress.

So every run is:

    POST /api/runs        -> create row (status=queued), submit, return 202
    worker thread         -> status=running, execute graph, write trace rows
    GET /api/runs/{id}/events -> stream those rows as they appear

The pool is bounded (WARDEN_WORKERS) so a burst of requests cannot exhaust
memory or hammer a model provider. A run paused at a gate releases its
worker: the state lives in the checkpointer, and the approval endpoint
re-submits the continuation.

Crash behaviour is explicit (see db.recover_interrupted_runs): a paused run
survives and resumes; a run killed mid-tool is marked failed rather than
replayed, because replaying a node can repeat a side effect.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import config, db, llm
from .agents.graphs import run_agent, resume_run

log = logging.getLogger("warden.runner")

_executor = ThreadPoolExecutor(
    max_workers=config.WORKER_THREADS, thread_name_prefix="warden-run"
)
_inflight: set[str] = set()
_lock = threading.Lock()


class RunBusy(RuntimeError):
    """The run already has a job in the pool."""


def _claim(run_id: str) -> None:
    with _lock:
        if run_id in _inflight:
            raise RunBusy(f"run {run_id} is already executing")
        _inflight.add(run_id)


def _release(run_id: str) -> None:
    with _lock:
        _inflight.discard(run_id)


def is_inflight(run_id: str) -> bool:
    with _lock:
        return run_id in _inflight


def inflight() -> int:
    with _lock:
        return len(_inflight)


def start_run(agent_id: str, task: str, *, version: str = "1.0.0",
              provider: str | None = None, tool_mode: str | None = None) -> dict:
    """Create the run row, queue the work, return immediately."""
    run_id = db.new_id("run")
    thread_id = db.new_id("th")
    provider_name = provider or llm.resolve_provider()
    model_id = llm.model_name(provider_name)
    db.create_run(run_id, thread_id, agent_id, task, version,
                  provider=provider_name, model=model_id, status="queued")
    _claim(run_id)
    _executor.submit(_run_job, run_id, thread_id, agent_id, task, version,
                     provider_name, tool_mode)
    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "status": "queued",
        "agent_id": agent_id,
        "provider": provider_name,
        "model": model_id,
    }


def _run_job(run_id, thread_id, agent_id, task, version, provider, tool_mode):
    started = time.time()
    try:
        run_agent(agent_id, task, version=version, run_id=run_id,
                  thread_id=thread_id, precreated=True,
                  provider=provider, tool_mode=tool_mode)
    except Exception as e:  # never leave a run stuck in "running"
        log.exception("run %s crashed", run_id)
        db.update_run(run_id, status="failed", success=0,
                      result=f"Failed: internal error — {type(e).__name__}: {e}"[:2000],
                      failure_reason="internal_error",
                      ended_at=time.time(),
                      duration_ms=int((time.time() - started) * 1000))
    finally:
        _release(run_id)


def submit_resume(run_id: str, approval_id: str, approved: bool, note: str = "") -> None:
    """Queue the continuation of a paused run."""
    _claim(run_id)
    try:
        _executor.submit(_resume_job, run_id, approval_id, approved, note)
    except Exception:
        _release(run_id)
        raise


def _resume_job(run_id, approval_id, approved, note):
    started = time.time()
    try:
        result = resume_run(run_id, approval_id, approved, note)
        if isinstance(result, dict) and result.get("error"):
            # The decision was already recorded or the run moved on; the
            # approval row is the source of truth, so this is not a crash.
            log.warning("resume %s rejected: %s", run_id, result["error"])
    except Exception as e:
        log.exception("resume %s crashed", run_id)
        db.update_run(run_id, status="failed", success=0,
                      result=f"Failed: internal error — {type(e).__name__}: {e}"[:2000],
                      failure_reason="internal_error",
                      ended_at=time.time(),
                      duration_ms=int((time.time() - started) * 1000))
    finally:
        _release(run_id)


def shutdown() -> None:
    _executor.shutdown(wait=True, cancel_futures=False)
