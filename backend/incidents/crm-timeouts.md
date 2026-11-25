# Incident: CRM update timed out five times in one day (2026-11-18)

The CRM API was slow and `crm_update` timed out five times. Each
timeout was retried immediately, which made the load worse. The runs
failed and the queue backed up.

Lesson: add a retry with exponential backoff and a 5-second timeout to
`crm_update`, and surface repeated timeouts as a failure mode on the
dashboard so the team can see it.
