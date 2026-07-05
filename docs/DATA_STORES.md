# Data Stores Registry (jsonl / json / db / csv mini-databases)

**Purpose:** The app persists a lot of state in gitignored `data/*.jsonl` / `*.json` / `*.db` /
`*.csv` files that behave as mini-databases (append-only ledgers, config toggles, caches — plus
PII/auth stores). There was **no registry** (GAP `R-17`). This file is that registry: one place to
see every code-referenced data store, whether it looks PII/compliance-sensitive, and which modules
own it.

**AUTO-GENERATED via `scripts/data_store_inventory.py`** — edits between the AUTO markers are
overwritten. Regenerate: `python scripts/data_store_inventory.py` · drift-check (CI-safe):
`python scripts/data_store_inventory.py --check`.

**Policy (NOT this file's job):** jsonl → Postgres migration = *migrate-when-volume* (ADR; see
`docs/GAP_REGISTER_2026_07_05.md` **R-33**, PARKED). Retention / DPDP purge rules live in the
`data-retention-dpdp` skill. **Ye file sirf REGISTRY hai** — schema/owner/retention ko yahan track
karo, migration nahi.

**Gaps:** `R-17` (build this inventory) · `R-33` (jsonl→Postgres, deferred) — `docs/GAP_REGISTER_2026_07_05.md`.

**Placeholder convention:** `<date>` = per-day partition (e.g. `%Y-%m-%d`) · `<shard>` =
per-id/per-day file inside a directory store · `<client_id>` etc. = f-string key. Date/shard-sharded
references are collapsed to one row. `type = dir` = directory store whose file extension couldn't be
inferred cheaply (may hold non-jsonl payloads such as `.wav` recordings).

<!-- AUTO-DATASTORES:START -->

## Inventory — auto-generated (209 stores, 20 PII-likely; scanned 763 source files)

> Regenerate: `python scripts/data_store_inventory.py`. Edits between AUTO markers are overwritten.
> `PII-likely?`: `⚠️ yes` = path name matches a compliance pattern (consent/auth/totp/dpdp/customer/lead/recording/transcript/prospect/client_api_keys) → treat as regulated data. Non-PII rows show best-guess class (`state`/`config`/`cache`). `notes` intentionally blank for owner annotation.

| path | type | PII-likely? | referenced-by (top 3 modules) | notes |
|---|---|---|---|---|
| `data/cadence_leads.jsonl` | jsonl | ⚠️ yes | `scripts.gap_check`, `app.marketing.cadence`, `app.platform.dpdp` | |
| `data/call_recordings/` | dir | ⚠️ yes | `app.api.call_recordings`, `app.api.web_call`, `app.api.web_call_admin` +1 | |
| `data/call_transcripts/<shard>.jsonl` | jsonl | ⚠️ yes | `app.agents.campaign_optimizer`, `app.agents.live_eval`, `app.agents.staff` +9 | |
| `data/client_api_keys.jsonl` | jsonl | ⚠️ yes | `app.platform.client_api_keys` | |
| `data/consent_ledger.jsonl` | jsonl | ⚠️ yes | `app.telephony.consent_ledger` | |
| `data/customer_auth.jsonl` | jsonl | ⚠️ yes | `app.api.customer_auth`, `app.billing.dunning`, `app.billing.usage_alerts` | |
| `data/customer_wish_drafts.jsonl` | jsonl | ⚠️ yes | `app.marketing.customer_crm`, `app.platform.dpdp` | |
| `data/dpdp_audit.jsonl` | jsonl | ⚠️ yes | `app.platform.dpdp` | |
| `data/dpdp_requests.jsonl` | jsonl | ⚠️ yes | `app.platform.dpdp` | |
| `data/lead_alerts.jsonl` | jsonl | ⚠️ yes | `app.platform.lead_alerts`, `app.platform.speed_to_lead` | |
| `data/lead_assignments.jsonl` | jsonl | ⚠️ yes | `app.platform.lead_distribution` | |
| `data/lead_lists.jsonl` | jsonl | ⚠️ yes | `app.platform.prospect_lists` | |
| `data/lead_magnets/` | dir | ⚠️ yes | `app.marketing.lead_magnet` | |
| `data/lead_routing.jsonl` | jsonl | ⚠️ yes | `app.platform.lead_distribution` | |
| `data/lead_status_overrides.jsonl` | jsonl | ⚠️ yes | `app.platform.lead_overrides` | |
| `data/niche_prospect_cursor.json` | json | ⚠️ yes | `app.platform.niche_prospector` | |
| `data/prospect_analyses/` | dir | ⚠️ yes | `app.agents.sales_team` | |
| `data/prospect_export.csv` | csv | ⚠️ yes | `scripts.run_prospect` | |
| `data/prospects.jsonl` | jsonl | ⚠️ yes | `app.platform.dpdp`, `app.platform.identity_resolver`, `app.platform.prospector` +3 | |
| `data/recordings/` | dir | ⚠️ yes | `app.telephony.consent_ledger` | |
| `data/.video_ad_cycle.json` | json | state | `app.marketing.video_ad_cycle` | |
| `data/.watchdog_alert.json` | json | state | `app.platform.ops_watchdog` | |
| `data/affiliate_referrals.jsonl` | jsonl | state | `app.marketing.affiliate` | |
| `data/affiliates.jsonl` | jsonl | state | `app.marketing.affiliate` | |
| `data/agent_graph.db` | db | state | `app.agents.supervisor` | |
| `data/agent_hooks.json` | json | state | `app.agents.lifecycle_hooks` | |
| `data/agent_memory.jsonl` | jsonl | state | `app.agents.coordinator` | |
| `data/agent_pause_state.jsonl` | jsonl | cache | `app.platform.agent_controls` | |
| `data/agent_permissions.json` | json | state | `app.agents.agent_permissions` | |
| `data/agent_recall.jsonl` | jsonl | state | `app.agents.agent_recall` | |
| `data/agent_trajectories.jsonl` | jsonl | state | `app.agents.trajectory` | |
| `data/ai_images/` | dir | state | `app.marketing.ai_image` | |
| `data/approval_decisions.jsonl` | jsonl | state | `app.platform.approvals_bridge` | |
| `data/batch_runs/<shard>.jsonl` | jsonl | state | `app.agents.batch_harness` | |
| `data/beacon_events.jsonl` | jsonl | state | `app.platform.site_beacon` | |
| `data/bg_removed/` | dir | state | `app.marketing.bg_remove` | |
| `data/bio_clicks.jsonl` | jsonl | state | `app.marketing.bio_link` | |
| `data/bio_links.jsonl` | jsonl | state | `app.marketing.bio_link` | |
| `data/booking_reminder_runs.jsonl` | jsonl | state | `app.platform.booking_reminders` | |
| `data/bookings.jsonl` | jsonl | state | `app.marketing.client_report`, `app.platform.booking_reminders` | |
| `data/bookings/<shard>.jsonl` | jsonl | state | `app.integrations.calendar_booking` | |
| `data/brand_kits/<shard>.json` | json | state | `app.marketing.brand_kit` | |
| `data/brand_pulse_cache.jsonl` | jsonl | cache | `app.platform.brand_pulse` | |
| `data/brand_pulse_runs.jsonl` | jsonl | state | `app.platform.brand_pulse` | |
| `data/cadence_runs.jsonl` | jsonl | state | `app.agents.campaign_optimizer`, `app.marketing.cadence`, `app.platform.call_insights` +1 | |
| `data/call_qualifications.jsonl` | jsonl | state | `app.platform.call_insights`, `app.telephony.call_manager`, `app.telephony.post_call_hooks` +2 | |
| `data/call_transfers.jsonl` | jsonl | state | `app.telephony.call_transfer` | |
| `data/callback_touches.jsonl` | jsonl | state | `app.platform.speed_to_lead` | |
| `data/campaign_optimization/` | dir | state | `app.agents.campaign_optimizer` | |
| `data/catalogs/<shard>.jsonl` | jsonl | state | `app.marketing.product_catalog` | |
| `data/channel_experiments.jsonl` | jsonl | state | `app.marketing.channel_experiments` | |
| `data/channel_outcomes.jsonl` | jsonl | state | `app.agents.campaign_optimizer`, `app.marketing.channel_experiments` | |
| `data/claude_feedback.jsonl` | jsonl | state | `app.agents.rl.reward` | |
| `data/client_packs/` | dir | state | `app.marketing.client_report`, `app.marketing.onboarding`, `app.platform.client_health` | |
| `data/client_reports/` | dir | state | `app.marketing.client_report` | |
| `data/clip_jobs.jsonl` | jsonl | state | `app.marketing.video_clips` | |
| `data/clips/` | dir | state | `app.api.contentplus`, `app.marketing.video_clips` | |
| `data/clips/uploads/` | dir | state | `app.api.contentplus` | |
| `data/code_patches.jsonl` | jsonl | state | `app.agents.code_upgrader` | |
| `data/content_approvals.jsonl` | jsonl | state | `app.marketing.content_approval` | |
| `data/content_feedback.jsonl` | jsonl | state | `app.agents.campaign_optimizer`, `app.marketing.content_feedback` | |
| `data/content_queue/<shard>.jsonl` | jsonl | state | `app.marketing.auto_content`, `app.platform.team` | |
| `data/content_schedule.jsonl` | jsonl | state | `app.marketing.content_schedule` | |
| `data/conversation_replies.jsonl` | jsonl | state | `app.platform.conversations` | |
| `data/coordination_runs.jsonl` | jsonl | state | `app.agents.coordinator`, `app.platform.approvals_bridge`, `scripts.coordinator_audit` | |
| `data/crm/<shard>.jsonl` | jsonl | state | `app.marketing.crm_lite`, `app.platform.dpdp` | |
| `data/crm_sync.jsonl` | jsonl | state | `app.platform.crm_sync` | |
| `data/custom_agents/<shard>.json` | json | state | `app.agents.custom_agents` | |
| `data/custom_niches.json` | json | state | `scripts.migrate_custom_niches_lead_band` | |
| `data/deal_actions.jsonl` | jsonl | state | `app.marketing.sales_pipeline` | |
| `data/deals.jsonl` | jsonl | state | `scripts.gap_check`, `app.marketing.sales_pipeline`, `app.platform.identity_resolver` +1 | |
| `data/deliverability_checks.jsonl` | jsonl | state | `app.platform.deliverability_monitor` | |
| `data/dial_test_mode.json` | json | config | `app.telephony.dial_gate` | |
| `data/dialer_logs.jsonl` | jsonl | state | `app.platform.call_insights`, `app.platform.dialer_leaderboard`, `app.platform.dialer_log` +3 | |
| `data/dlq_failed_tasks.jsonl` | jsonl | state | `scripts.automation_health_audit` | |
| `data/dnd_cache.json` | json | cache | `scripts.automation_health_audit` | |
| `data/dunning_cases.jsonl` | jsonl | state | `app.billing.dunning` | |
| `data/dunning_runs.jsonl` | jsonl | state | `app.billing.dunning` | |
| `data/email_events.jsonl` | jsonl | state | `app.marketing.email_tracking` | |
| `data/email_suppression.jsonl` | jsonl | state | `app.platform.email_unsub` | |
| `data/email_warmup.json` | json | state | `app.platform.email_warmup` | |
| `data/exports/trajectories_dataset.jsonl` | jsonl | state | `app.agents.trajectory` | |
| `data/fde_deploys.jsonl` | jsonl | state | `app.agents.fde`, `app.platform.approvals_bridge` | |
| `data/flow_runner/` | dir | state | `app.automation.flow_store` | |
| `data/flow_runner/cron_state.json` | json | cache | `app.automation.flow_triggers` | |
| `data/frames/` | dir | state | `app.api.brandassets`, `app.marketing.brand_frames` | |
| `data/gbp_audits/<shard>.json` | json | state | `app.api.customer_dashboard`, `app.api.customer_marketing_studio` | |
| `data/geo_checks.jsonl` | jsonl | state | `app.marketing.geo_visibility` | |
| `data/gifs/` | dir | state | `app.api.contentplus`, `app.marketing.gif_maker` | |
| `data/grid_rank_runs.jsonl` | jsonl | state | `app.platform.grid_rank` | |
| `data/growth_history.jsonl` | jsonl | state | `app.platform.growth_engine` | |
| `data/growth_ideas.jsonl` | jsonl | state | `app.agents.growth_optimizer` | |
| `data/growth_optimizer_runs.jsonl` | jsonl | state | `app.agents.growth_optimizer` | |
| `data/growth_pulse.json` | json | state | `app.platform.growth_engine` | |
| `data/gtm_coverage.json` | json | state | `app.platform.gtm_targeting` | |
| `data/harvest_runs.jsonl` | jsonl | state | `scripts.gap_check`, `app.platform.lead_harvester`, `app.platform.team` | |
| `data/icp/` | dir | state | `app.platform.icp_generator` | |
| `data/identity_merge_log.jsonl` | jsonl | state | `app.platform.identity_resolver` | |
| `data/indexnow_cursor.json` | json | cache | `app.marketing.indexnow` | |
| `data/infra_scans.jsonl` | jsonl | state | `app.platform.infra_handler` | |
| `data/inquiries.jsonl` | jsonl | state | `app.agents.staff`, `app.api.admin_dashboard`, `app.api.admin_dashboard_builders` +14 | |
| `data/interactions.jsonl` | jsonl | state | `app.platform.conversations`, `app.platform.interaction_log` | |
| `data/invoices.jsonl` | jsonl | state | `app.billing.gst_invoice` | |
| `data/jingles/` | dir | state | `app.marketing.jingle` | |
| `data/job_heartbeats.json` | json | cache | `app.platform.automation_health`, `app.platform.ops_watchdog`, `app.platform.team` +2 | |
| `data/job_runs.jsonl` | jsonl | state | `app.platform.automation_health` | |
| `data/journey_runs.jsonl` | jsonl | state | `app.marketing.journeys` | |
| `data/journeys.jsonl` | jsonl | state | `app.marketing.journeys` | |
| `data/kb_interview_nudges.json` | json | state | `app.marketing.onboarding` | |
| `data/kb_refresh_cursor.json` | json | cache | `app.platform.kb_refresh` | |
| `data/lifecycle_nurture.jsonl` | jsonl | state | `app.marketing.lifecycle_nurture` | |
| `data/lifecycle_runs.jsonl` | jsonl | state | `app.marketing.lifecycle_nurture` | |
| `data/link_clicks.jsonl` | jsonl | state | `app.platform.short_links` | |
| `data/listings_status.jsonl` | jsonl | state | `app.marketing.listings_presence` | |
| `data/live_topics.jsonl` | jsonl | state | `app.platform.live_notes` | |
| `data/llm_calls.jsonl` | jsonl | state | `scripts.gap_check`, `app.platform.llm_metrics` | |
| `data/logos/` | dir | state | `app.marketing.brand_frames` | |
| `data/loyalty_campaigns.jsonl` | jsonl | state | `app.marketing.loyalty` | |
| `data/loyalty_redemptions.jsonl` | jsonl | state | `app.marketing.loyalty` | |
| `data/mailbox_cursor.json` | json | cache | `app.marketing.outreach_variants` | |
| `data/marketing_clients.jsonl` | jsonl | state | `app.marketing.clients_store` | |
| `data/memory/` | dir | state | `app.platform.memory_vault` | |
| `data/meta_connections.jsonl` | jsonl | state | `app.integrations.meta_graph` | |
| `data/newsletter_runs.jsonl` | jsonl | state | `app.marketing.newsletter` | |
| `data/newsletter_subs.jsonl` | jsonl | state | `app.marketing.newsletter` | |
| `data/nps_responses.jsonl` | jsonl | state | `app.platform.nps` | |
| `data/objection_patterns.jsonl` | jsonl | state | `app.platform.objection_extractor` | |
| `data/outbound_webhooks.jsonl` | jsonl | state | `app.platform.outbound_webhooks` | |
| `data/outreach_variants.jsonl` | jsonl | state | `app.marketing.outreach_variants` | |
| `data/perf_baseline.json` | json | cache | `scripts.perf_regression` | |
| `data/pipeline_admin_overrides.jsonl` | jsonl | config | `app.platform.admin_pipeline_overrides` | |
| `data/platform_dial.json` | json | state | `app.platform.platform_dial` | |
| `data/platform_upi.json` | json | state | `app.platform.upi_config` | |
| `data/popup_config.jsonl` | jsonl | config | `app.marketing.popup_widgets` | |
| `data/posthog_config.json` | json | config | `app.platform.posthog_config` | |
| `data/privacy_ops.jsonl` | jsonl | state | `app.platform.data_privacy` | |
| `data/process_runs/<shard>.jsonl` | jsonl | state | `app.agents.dag_engine`, `app.agents.process_engine` | |
| `data/process_runs/dag_index.jsonl` | jsonl | state | `app.agents.dag_engine` | |
| `data/proposal_html/` | dir | state | `app.platform.proposal_tracking` | |
| `data/proposal_sweep_cursor.json` | json | cache | `app.platform.proposal_tracking` | |
| `data/proposal_views.jsonl` | jsonl | state | `app.platform.proposal_tracking` | |
| `data/push_drafts.jsonl` | jsonl | state | `app.platform.webpush` | |
| `data/push_subs.jsonl` | jsonl | state | `app.platform.webpush` | |
| `data/rank_history.jsonl` | jsonl | state | `app.platform.rank_tracker` | |
| `data/rank_tracking.jsonl` | jsonl | state | `app.platform.rank_tracker` | |
| `data/reels/` | dir | state | `app.marketing.reel_video` | |
| `data/referrals.jsonl` | jsonl | state | `app.marketing.referral_kit` | |
| `data/reply_drafts.jsonl` | jsonl | state | `app.api.growth`, `scripts.gap_check`, `app.agents.campaign_optimizer` +4 | |
| `data/reply_feedback.jsonl` | jsonl | state | `app.api.growth`, `app.platform.reply_agent` | |
| `data/reseller_applications.json` | json | state | `app.platform.reseller` | |
| `data/resized/` | dir | state | `app.api.brandassets`, `app.marketing.magic_resize` | |
| `data/revenue_attribution.jsonl` | jsonl | state | `app.platform.revenue_attribution` | |
| `data/revenue_digest.jsonl` | jsonl | state | `app.platform.revenue_digest` | |
| `data/revenue_snapshots.jsonl` | jsonl | state | `app.platform.revenue_snapshots` | |
| `data/review_monitor_drafts.jsonl` | jsonl | state | `app.marketing.review_monitor` | |
| `data/review_monitor_seen.jsonl` | jsonl | cache | `app.marketing.review_monitor` | |
| `data/review_requests.jsonl` | jsonl | state | `app.marketing.client_report`, `app.marketing.review_engine` | |
| `data/rl_rewards.jsonl` | jsonl | state | `app.agents.rl.reward` | |
| `data/scheduler_overrides.json` | json | config | `app.platform.scheduler_config` | |
| `data/segments.jsonl` | jsonl | state | `app.platform.segments` | |
| `data/self_improve_approvals.jsonl` | jsonl | state | `app.agents.self_improve`, `scripts.verify_phase6_integration` | |
| `data/self_improve_heartbeat.json` | json | cache | `scripts.workflow_loop_debug` | |
| `data/self_improve_queue.jsonl` | jsonl | state | `scripts.automation_health_audit`, `app.agents.self_improve` | |
| `data/self_improve_runs.jsonl` | jsonl | state | `scripts.automation_health_audit`, `app.agents.self_improve`, `scripts.verify_phase6_integration` | |
| `data/self_improve_state.json` | json | cache | `scripts.automation_health_audit`, `app.agents.self_improve`, `scripts.verify_phase6_integration` | |
| `data/seo_pages.jsonl` | jsonl | state | `app.marketing.seo_pages` | |
| `data/service_reminders.jsonl` | jsonl | state | `app.platform.service_reminders` | |
| `data/short_links.jsonl` | jsonl | state | `app.platform.short_links` | |
| `data/skill_lessons.jsonl` | jsonl | state | `app.platform.skill_library` | |
| `data/skill_uses.jsonl` | jsonl | state | `app.platform.skill_library` | |
| `data/skills_extra/` | dir | state | `app.platform.skill_pack` | |
| `data/snapshots/<shard>.json` | json | state | `app.platform.client_snapshots` | |
| `data/social_engine.json` | json | state | `app.api.growth_automation`, `app.social_engine.engine` | |
| `data/social_post_jobs.jsonl` | jsonl | state | `app.social_engine.store` | |
| `data/social_tokens.jsonl` | jsonl | state | `app.social_engine.vault` | |
| `data/stickers/` | dir | state | `app.marketing.sticker_pack` | |
| `data/studio_jobs/` | dir | state | `app.api.studio_media` | |
| `data/studio_media/` | dir | state | `app.api.studio_media` | |
| `data/studio_uploads/` | dir | state | `app.api.studio_media` | |
| `data/team_reports/` | dir | state | `app.platform.team_report` | |
| `data/telephony_readiness.jsonl` | jsonl | state | `app.telephony.telephony_readiness` | |
| `data/tracked_proposals.jsonl` | jsonl | state | `app.platform.proposal_tracking` | |
| `data/trainer_suggestions.jsonl` | jsonl | state | `app.agents.staff`, `app.voice_agent.telecaller_brain` | |
| `data/trust_config.json` | json | config | `app.platform.trust_config` | |
| `data/turn_metrics/<shard>.jsonl` | jsonl | state | `app.voice_agent.turn_metrics` | |
| `data/upi_payments.json` | json | state | `app.platform.upi_payments` | |
| `data/usage_alerts.jsonl` | jsonl | state | `app.billing.usage_alerts` | |
| `data/video_ads.jsonl` | jsonl | state | `app.marketing.video_ad_cycle` | |
| `data/voice_gemini_keys.json` | json | config | `app.voice_agent.gemini_keys` | |
| `data/voice_learn_state.json` | json | cache | `app.agents.self_improve` | |
| `data/voice_learned.jsonl` | jsonl | state | `app.voice_agent.voice_learned` | |
| `data/voice_proposals.jsonl` | jsonl | state | `app.voice_agent.voice_self_improve` | |
| `data/voice_selfimprove_counter.json` | json | state | `app.telephony.vobiz_stream` | |
| `data/voice_stt_corrections.jsonl` | jsonl | state | `app.voice_agent.hinglish_stt_fix` | |
| `data/voice_suppression.jsonl` | jsonl | state | `app.telephony.consent_ledger` | |
| `data/wa_campaigns.jsonl` | jsonl | state | `app.marketing.wa_campaign_runner` | |
| `data/wa_failures.jsonl` | jsonl | state | `app.marketing.wa_campaign_runner` | |
| `data/wa_inbound.jsonl` | jsonl | state | `app.api.whatsapp` | |
| `data/wa_selfhost_seen.json` | json | cache | `app.api.whatsapp` | |
| `data/wa_send_counter.json` | json | state | `app.marketing.whatsapp_campaign` | |
| `data/wa_suppression.jsonl` | jsonl | state | `app.marketing.wa_campaign_runner` | |
| `data/wa_templates.jsonl` | jsonl | config | `app.marketing.wa_campaign_runner` | |
| `data/web_call_sessions.jsonl` | jsonl | state | `app.voice_agent.web_call_store` | |
| `data/webhook_deliveries.jsonl` | jsonl | state | `app.platform.outbound_webhooks` | |
| `data/webhook_dlq.jsonl` | jsonl | state | `app.platform.outbound_webhooks` | |
| `data/webhook_retry_queue.jsonl` | jsonl | state | `app.platform.outbound_webhooks` | |
| `data/widget_chats.jsonl` | jsonl | state | `app.api.conversion`, `app.platform.conversations`, `app.platform.dpdp` +1 | |
| `data/widget_forms.jsonl` | jsonl | state | `app.marketing.embed_widget` | |
| `data/winback_drafts.jsonl` | jsonl | state | `app.platform.winback` | |

<!-- AUTO-DATASTORES:END -->
