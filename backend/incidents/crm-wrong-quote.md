# Incident: CRM update overwrote the wrong quote (2026-11-12)

An agent updated a CRM record for Acme Corp with a quote meant for
Globex Ltd. The quote was sent to the customer before anyone noticed.
Root cause: the agent matched the customer by name only, and two
customers share a similar name.

Lesson: `crm_update` must show the exact record id and the exact fields
being changed, and a human must approve before the write. Matching by
name alone is not enough.
