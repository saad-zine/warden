# Policy: CRM writes require human approval

Any tool that writes to the CRM (`crm_update`) changes customer-facing
records: contact details, quotes, deal stage, and pricing. A wrong write
propagates to billing, support, and sales dashboards.

Rules:
- `crm_update` ALWAYS requires a human approval before it runs.
- The approval must show the exact record id and the exact fields being
  changed.
- Never update a CRM record for a customer whose account is flagged
  "do not contact".
- If the agent is unsure about a field value, it must ask the human
  instead of guessing.
