# Incident: Agent looped 12 times on a failing search (2026-10-28)

A web search tool started returning errors. The agent retried the same
search 12 times before the iteration cap stopped it, burning the run's
entire token budget.

Lesson: the platform must cap iterations, detect repeated identical
tool calls (a loop), and halt the run with a clear failure reason
instead of burning budget.
