# Policy: Outbound messages require human approval

Any tool that sends a message to a customer or an external party
(`send_message`) requires a human approval. An agent must never send an
external message on its own.

Rules:
- `send_message` ALWAYS requires a human approval before it runs.
- The approval must show the full message text and the recipient.
- Messages must not contain pricing the agent computed itself unless a
  human has verified the numbers.
- No message may be sent outside business hours (09:00–18:00) without an
  explicit approval note.
