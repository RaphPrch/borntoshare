-- Tasks launched by the smart policies (ACL read and content, sensitivity scan) on the folders that match:
-- when each folder last got them, so that a policy run every 15 minutes respects the frequency it asks for.
-- Idempotent: can be applied again.

ALTER TABLE governance_policy_hits ADD COLUMN IF NOT EXISTS last_job_at DATETIME NULL;
