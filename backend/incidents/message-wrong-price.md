# Incident: Agent sent a message with unverified pricing (2026-11-03)

An agent sent a customer a message quoting a price it had computed
itself. The price was wrong (it used a monthly rate instead of an annual
one). The customer accepted the quote and the company had to honour it.

Lesson: outbound messages must be approved by a human, and the approval
must show the full message text. Never send pricing the agent computed
without human verification.
