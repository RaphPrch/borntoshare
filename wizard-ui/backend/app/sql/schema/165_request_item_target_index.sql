-- The items of the requests looked up by their folder (pending requests of a server, access already granted on a
-- folder, alerts, reviews): without this index every lookup read all the items. Target first: the views join on it.
-- Applied by the migration account. Idempotent.

CREATE INDEX IF NOT EXISTS ix_access_request_items_target ON access_request_items (target_id, target_type);
