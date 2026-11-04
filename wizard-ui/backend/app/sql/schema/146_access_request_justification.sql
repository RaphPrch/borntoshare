-- The reason given by the requester gets its own column: it was kept in decision_comment, which the guardian's
-- comment then replaced. Existing rows: decision_comment is copied as the justification; on a pending request it
-- was only the justification, so it is emptied. On a decided request the two cannot be told apart and both stay.
-- Idempotent: can be applied again.

ALTER TABLE access_requests ADD COLUMN IF NOT EXISTS justification TEXT NULL AFTER status;

UPDATE access_requests
SET justification = decision_comment,
    decision_comment = CASE WHEN status = 'pending' THEN NULL ELSE decision_comment END
WHERE justification IS NULL AND decision_comment IS NOT NULL;
