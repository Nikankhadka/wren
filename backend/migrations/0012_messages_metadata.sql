-- 0012_messages_metadata.sql - T-021: a place for the Reasoning-Inspection
-- layer's verdicts on the assistant message they gate, for the Surface-2
-- trace viewer. Verdicts belong on the row itself (the message they
-- describe), not a separate role='system' trace row - that would pollute
-- every transcript query with rows no surface wants to render as chat.

alter table messages add column metadata jsonb not null default '{}';
