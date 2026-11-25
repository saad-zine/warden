"""Per-run trace recording.

A Tracer owns one run's step sequence and accumulates tokens/cost. It
writes steps to the SQLite trace store (see db.py) and is passed to the
agent graph so every node, tool call, LLM call, gate decision, and
memory lookup is recorded with timing and cost.
"""
import time

from . import db


class Tracer:
    def __init__(self, run_id):
        self.run_id = run_id
        # Resume the sequence from the existing max (a resumed run keeps
        # appending steps after the ones recorded before the pause).
        try:
            steps = db.get_trace(run_id)
            self.seq = max((s["seq"] for s in steps), default=0)
        except Exception:
            self.seq = 0
        self.tokens = 0
        self.cost_usd = 0.0

    def _next_seq(self):
        self.seq += 1
        return self.seq

    def log(self, type_, name, input_data=None, output_data=None,
            duration_ms=0, tokens=0, cost_usd=0.0, status="ok"):
        db.add_step(
            self.run_id,
            self._next_seq(),
            type_, name, input_data, output_data,
            duration_ms=duration_ms, tokens=tokens,
            cost_usd=cost_usd, status=status,
        )
        self.tokens += tokens
        self.cost_usd += cost_usd
        return self.seq

    def log_tool(self, name, args, output, duration_ms, status="ok",
                 tokens=0, cost_usd=0.0):
        return self.log("tool", name, args, output, duration_ms,
                        tokens=tokens, cost_usd=cost_usd, status=status)

    def log_node(self, name, input_data=None, output_data=None,
                 duration_ms=0, status="ok"):
        return self.log("node", name, input_data, output_data,
                        duration_ms=duration_ms, status=status)

    def log_gate(self, name, input_data=None, output_data=None, status="ok"):
        return self.log("gate", name, input_data, output_data, status=status)

    def log_llm(self, name, input_data=None, output_data=None,
                tokens=0, cost_usd=0.0, status="ok"):
        return self.log("llm", name, input_data, output_data,
                        tokens=tokens, cost_usd=cost_usd, status=status)

    def log_memory(self, name, input_data=None, output_data=None, status="ok"):
        return self.log("memory", name, input_data, output_data, status=status)


class NullTracer:
    """A tracer that records nothing (used in unit tests)."""

    def __init__(self):
        self.tokens = 0
        self.cost_usd = 0.0

    def log(self, *args, **kwargs):
        return 0

    def log_tool(self, *args, **kwargs):
        return 0

    def log_node(self, *args, **kwargs):
        return 0

    def log_gate(self, *args, **kwargs):
        return 0

    def log_llm(self, *args, **kwargs):
        return 0

    def log_memory(self, *args, **kwargs):
        return 0
