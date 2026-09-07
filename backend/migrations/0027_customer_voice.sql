-- 0027_customer_voice.sql - W-9: back-fill the structured customer voice.
--
-- The public assistant used to be told how to sound by tenant_config.tone, one
-- free-text word read straight into a prompt. W-9 replaces it with a structured
-- value at config->customer_voice - {"preset": ..., "custom_style": ...} - that
-- selects one line of expression guidance inside the code-owned contract
-- (app/agents/contract.py). Free prose can no longer reach the prompt as
-- authority, which is the point of the change.
--
-- The mapping is the ticket's: friendly -> warm_casual, professional ->
-- clear_professional, anything direct or concise -> direct_concise, any other
-- non-empty word -> a bounded custom description, missing -> warm_casual (the
-- same default a tenant who never reached the voice beat resolves to).
--
-- This does NOT drop tenant_config.system_prompt or .tone, and the seeds keep
-- writing both. Application code stops reading them with this ticket; dropping
-- the columns is a separate follow-up after production verification, the same
-- shape as 0025 dropping escalation_threshold.
--
-- Only rows without a voice are touched: onboarding writes config->customer_voice
-- on confirm, and a backfill must never overwrite an owner's own choice.
update tenant_config
   set config = coalesce(config, '{}'::jsonb) || jsonb_build_object(
         'customer_voice',
         case
           when coalesce(trim(tone), '') = '' or lower(trim(tone)) = 'friendly'
             then jsonb_build_object('preset', 'warm_casual', 'custom_style', null)
           when lower(trim(tone)) = 'professional'
             then jsonb_build_object('preset', 'clear_professional', 'custom_style', null)
           when lower(trim(tone)) like '%direct%' or lower(trim(tone)) like '%concise%'
             then jsonb_build_object('preset', 'direct_concise', 'custom_style', null)
           else jsonb_build_object('preset', 'custom', 'custom_style', left(trim(tone), 300))
         end)
 where not (coalesce(config, '{}'::jsonb) ? 'customer_voice');
