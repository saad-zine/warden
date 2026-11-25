# Policy: Spend and token limits

Every agent run has a cost budget. The platform estimates cost from
token usage using reference frontier-model rates (documented in the
README — the number is an estimate, not a metered bill).

Rules:
- A run halts immediately if its estimated cost exceeds $0.50 or its
  token usage exceeds 20,000 tokens.
- A halted run is marked `failed` with reason `spend_limit` and the
  trace shows exactly where the budget was exhausted.
- The limit can be raised per run by an operator, but never by the agent
  itself.
- Cost is reported per run and per agent on the dashboard.
