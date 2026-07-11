-- 0011_escalations_dedupe.sql - T-020: prevent duplicate escalation rows
-- when concurrent agent turns on the same conversation both decide to
-- escalate (check-then-act race between the status read in /api/chat and
-- the write in the Escalation Agent node). A partial unique index lets the
-- node's insert use ON CONFLICT DO NOTHING instead of relying on the
-- earlier status check alone.

create unique index escalations_open_conversation_idx
  on escalations (tenant_id, conversation_id)
  where status = 'open';
