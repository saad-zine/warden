# Policy: Deletions are destructive and need approval

Any tool that deletes data (`delete_file`) is destructive and cannot be
undone. Deletions require a human approval, and the agent must state
exactly what will be deleted and why.

Rules:
- `delete_file` ALWAYS requires a human approval before it runs.
- The approval must show the exact path and a reason.
- Never delete a file outside the agent's output sandbox.
- Prefer archiving over deleting when the task allows it.
