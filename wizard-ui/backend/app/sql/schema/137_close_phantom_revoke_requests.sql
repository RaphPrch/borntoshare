-- A revocation used to leave a technical « REVOKE-… » request in the pending state, processed by nothing.
-- It blocked any new request of the same person on the same storage root and inflated the pending counts.
-- The revocation itself is kept on the source request (status revoked, revoked_at) and in the activity log.
-- Idempotent: can be applied again.

UPDATE access_requests
SET status = 'revoked',
    revoked_at = COALESCE(revoked_at, created_at),
    updated_at = CURRENT_TIMESTAMP
WHERE code LIKE 'REVOKE-%'
  AND status = 'pending';
