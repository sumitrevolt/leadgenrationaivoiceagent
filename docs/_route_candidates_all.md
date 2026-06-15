# Repo-wide Route Deletion-Candidate Map (read-only, 2026-06-14)

Scanned **47 API routers** = **593 routes**, cross-referenced against **554** non-router files (frontend, app services, tests).

- Likely KEEP (referenced): **485**
- CANDIDATES to review: **108**  (~18% of routes)

> Heuristic. "No ref found" can be a false positive when the frontend builds URLs dynamically. VERIFY each (grep frontend/ app/ tests/) before removing. Cut via: deprecate-behind-flag → prod_check.py + run_tests.bat → /ship → /health=production → delete in small batches.

## Candidates per router (most first)

| Candidates | Total routes | Router |
|---|---|---|
| 31 | 158 | app/api/growth.py |
| 13 | 31 | app/api/ml_training.py |
| 8 | 13 | app/api/widgets.py |
| 7 | 53 | app/api/marketing.py |
| 5 | 12 | app/api/clientcrm.py |
| 5 | 7 | app/api/ai.py |
| 4 | 21 | app/api/billing.py |
| 4 | 13 | app/api/analytics.py |
| 4 | 10 | app/api/team.py |
| 4 | 9 | app/api/niche_db.py |
| 3 | 11 | app/api/whatsapp.py |
| 2 | 17 | app/api/platform.py |
| 2 | 13 | app/api/clientops.py |
| 2 | 12 | app/api/contentplus.py |
| 2 | 12 | app/api/admin.py |
| 2 | 10 | app/api/contentauto.py |
| 2 | 3 | app/api/telephony_vobiz.py |
| 1 | 13 | app/api/minisite_builder.py |
| 1 | 11 | app/api/voiceai.py |
| 1 | 9 | app/api/memory_api.py |
| 1 | 8 | app/api/leads.py |
| 1 | 6 | app/api/public_site.py |
| 1 | 6 | app/api/health.py |
| 1 | 5 | app/api/engage.py |
| 1 | 5 | app/api/clients.py |

## Full candidate list

| Router | Method | Path | Handler | Line | Why |
|---|---|---|---|---|---|
| admin.py | PATCH | /admin/users/{user_id} | update_user | 597 | no ref found |
| admin.py | DELETE | /admin/users/{user_id} | delete_user | 672 | no ref found |
| ai.py | POST | /ai/generate-script | generate_sales_script | 139 | no ref found |
| ai.py | POST | /ai/generate-transcript | generate_call_transcript | 169 | no ref found |
| ai.py | POST | /ai/strategy-suggestion | get_strategy_suggestion | 196 | no ref found |
| ai.py | POST | /ai/ab-test-variant | generate_ab_test_variant | 220 | demo/debug name |
| ai.py | POST | /ai/qualify-call | qualify_call | 453 | no ref found |
| analytics.py | GET | /analytics/calls/by-day | get_calls_by_day | 345 | no ref found |
| analytics.py | GET | /analytics/leads/by-city | get_leads_by_city | 382 | no ref found |
| analytics.py | GET | /analytics/hourly-distribution | get_hourly_distribution | 464 | no ref found |
| analytics.py | GET | /analytics/reports/daily | get_daily_report | 492 | no ref found |
| billing.py | GET | /billing/plans/{plan_id} | get_plan_details | 296 | no ref found |
| billing.py | GET | /billing/invoices/{invoice_id} | get_invoice_details | 650 | no ref found |
| billing.py | GET | /billing/payment-methods | get_payment_methods | 730 | no ref found |
| billing.py | POST | /billing/balance/add | add_account_balance | 747 | no ref found |
| clientcrm.py | GET | /clientcrm/customers/{client_id} | get_customers | 60 | no ref found |
| clientcrm.py | POST | /clientcrm/catalog/{slug} | catalog_add | 104 | no ref found |
| clientcrm.py | GET | /clientcrm/catalog/{slug} | catalog_list | 119 | no ref found |
| clientcrm.py | POST | /clientcrm/catalog/{slug}/{product_id} | catalog_update | 136 | no ref found |
| clientcrm.py | DELETE | /clientcrm/catalog/{slug}/{product_id} | catalog_delete | 145 | no ref found |
| clientops.py | POST | /clientops/snapshots/{snapshot_id}/apply | snapshot_apply | 135 | no ref found |
| clientops.py | POST | /clientops/track-proposal | track_proposal | 204 | no ref found |
| clients.py | POST | /clients/{cid}/content/run | run_client_content | 161 | no ref found |
| contentauto.py | POST | /contentauto/team-report/run | team_report_run | 155 | no ref found |
| contentauto.py | GET | /contentauto/push/subscribe.js | push_subscribe_js | 180 | no ref found |
| contentplus.py | GET | /contentplus/gif-presets | gif_presets | 197 | no ref found |
| contentplus.py | POST | /contentplus/outreach-variants/reply | outreach_variant_reply | 250 | no ref found |
| engage.py | POST | /engage/alerts/test | alerts_test | 150 | demo/debug name |
| growth.py | POST | /growth/whatsapp/flow/send | whatsapp_flow_send | 92 | no ref found |
| growth.py | GET | /growth/niche/pack/{niche_key} | niche_pack_one | 161 | no ref found |
| growth.py | POST | /growth/niche/packs | niche_packs | 174 | no ref found |
| growth.py | POST | /growth/sms/send | sms_send | 266 | no ref found |
| growth.py | POST | /growth/partnership/batch | partnership_batch | 335 | no ref found |
| growth.py | POST | /growth/tools/missed-call-revenue | tool_missed_call | 349 | no ref found |
| growth.py | POST | /growth/tools/google-score | tool_google_score | 375 | no ref found |
| growth.py | GET | /growth/affiliate/stats | affiliate_stats | 406 | no ref found |
| growth.py | POST | /growth/community/batch | community_batch | 427 | no ref found |
| growth.py | POST | /growth/sales/deal/{deal_id}/stage | sales_stage | 452 | no ref found |
| growth.py | POST | /growth/sales/run | sales_run | 469 | no ref found |
| growth.py | POST | /growth/revenue/dunning/case | dunning_open_case | 514 | no ref found |
| growth.py | DELETE | /growth/webhooks/{webhook_id} | webhooks_remove | 893 | no ref found |
| growth.py | GET | /growth/infra/hermes/scans | infra_hermes_scans | 949 | no ref found |
| growth.py | POST | /growth/infra/dlq/sweep | infra_dlq_sweep | 991 | no ref found |
| growth.py | POST | /growth/crm/test | crm_test | 1102 | demo/debug name |
| growth.py | POST | /growth/notify/test | notify_test | 1148 | demo/debug name |
| growth.py | POST | /growth/prospects/find-email-batch | prospects_find_email_batch | 1241 | no ref found |
| growth.py | GET | /growth/reply/feedback/stats | reply_feedback_stats | 1398 | no ref found |
| growth.py | POST | /growth/content/reel-video | content_reel_video | 1556 | no ref found |
| growth.py | GET | /growth/content/templates | content_templates | 1600 | demo/debug name |
| growth.py | GET | /growth/loyalty/check/{code} | loyalty_check | 1632 | no ref found |
| growth.py | POST | /growth/revenue/client-report | client_report_build | 1661 | no ref found |
| growth.py | POST | /growth/revenue/client-reports/run | client_reports_run | 1669 | no ref found |
| growth.py | DELETE | /growth/client-keys/{hash_prefix} | client_key_revoke | 1696 | no ref found |
| growth.py | GET | /growth/nps/stats | nps_stats | 1733 | no ref found |
| growth.py | GET | /growth/nps/request-drafts | nps_request_drafts | 1741 | no ref found |
| growth.py | GET | /growth/skills/pack | skills_pack_list | 1900 | no ref found |
| growth.py | GET | /growth/skills/pack/{name} | skills_pack_get | 1910 | no ref found |
| growth.py | POST | /growth/social/batch | social_batch | 2000 | no ref found |
| growth.py | GET | /growth/process/run/{run_id} | process_run_detail | 2090 | no ref found |
| health.py | GET | /health/deep | deep_health_check | 111 | no ref found |
| leads.py | GET | /scrape/{task_id} | get_scrape_status | 284 | no ref found |
| marketing.py | GET | /marketing/ai-img-file/{name} | ai_img_file | 439 | no ref found |
| marketing.py | GET | /marketing/poster/templates | get_poster_templates | 901 | demo/debug name |
| marketing.py | POST | /marketing/page-kit | generate_page_kit | 1027 | no ref found |
| marketing.py | POST | /marketing/gbp-texts | generate_gbp_texts | 1409 | no ref found |
| marketing.py | POST | /marketing/blog/run | run_blog_publish | 1484 | no ref found |
| marketing.py | GET | /marketing/referral/stats | get_referral_stats | 1541 | no ref found |
| marketing.py | POST | /marketing/evergreen/{client_id} | recycle_evergreen_content | 1559 | no ref found |
| memory_api.py | DELETE | /memory/topics/{topic_id} | topic_remove | 107 | no ref found |
| minisite_builder.py | GET | /minisite/logo/{filename} | serve_logo | 522 | no ref found |
| ml_training.py | GET | /ml/best-responses | get_best_responses | 137 | no ref found |
| ml_training.py | GET | /ml/objection-handlers | get_objection_handlers | 155 | no ref found |
| ml_training.py | GET | /ml/training-history | get_training_history | 169 | no ref found |
| ml_training.py | GET | /ml/data-stats | get_data_statistics | 194 | no ref found |
| ml_training.py | POST | /ml/ab-test | create_ab_test | 213 | demo/debug name |
| ml_training.py | GET | /ml/ab-test/{test_id} | get_ab_test_results | 234 | demo/debug name |
| ml_training.py | POST | /ml/scheduler/stop | stop_scheduler | 272 | no ref found |
| ml_training.py | POST | /ml/brain/train | train_brains | 351 | no ref found |
| ml_training.py | POST | /ml/brain/train/now | train_brains_immediate | 389 | no ref found |
| ml_training.py | POST | /ml/vertex/train | trigger_vertex_training | 629 | no ref found |
| ml_training.py | POST | /ml/vertex/train/now | vertex_train_now | 671 | no ref found |
| ml_training.py | POST | /ml/unified/train | unified_train_all | 928 | no ref found |
| ml_training.py | POST | /ml/unified/train/now | unified_train_all_now | 958 | no ref found |
| niche_db.py | POST | /niche/prospects/bulk | bulk_import_prospects | 143 | no ref found |
| niche_db.py | GET | /niche/prospects/next-to-call | next_to_call | 268 | no ref found |
| niche_db.py | PATCH | /niche/prospects/{lead_id} | post_call_update | 291 | no ref found |
| niche_db.py | GET | /niche/voice-niches | voice_niches_list | 348 | no ref found |
| platform.py | DELETE | /platform/tenants/{tenant_id} | delete_tenant | 386 | no ref found |
| platform.py | POST | /platform/scrape/tenant/{tenant_id} | trigger_tenant_scrape | 422 | no ref found |
| public_site.py | POST | /public/ai-demo | ai_demo | 323 | demo/debug name |
| team.py | POST | /platform/team/run/{member} | run_team_member | 45 | no ref found |
| team.py | POST | /platform/team/email-outreach/run | run_email_outreach_now | 93 | no ref found |
| team.py | GET | /platform/team/email-outreach/stats | get_email_outreach_stats | 104 | no ref found |
| team.py | POST | /platform/team/email-followups/run | run_email_followups_now | 114 | no ref found |
| telephony_vobiz.py | POST | /telephony/vobiz/test-call | place_test_call | 91 | demo/debug name |
| telephony_vobiz.py | POST | /telephony/vobiz/stream-call | place_stream_call | 207 | no ref found |
| voiceai.py | POST | /voiceai/consent/retention-sweep | consent_retention_sweep | 205 | no ref found |
| whatsapp.py | GET | /wa/templates | list_templates | 66 | demo/debug name |
| whatsapp.py | POST | /wa/templates | register_template | 82 | demo/debug name |
| whatsapp.py | POST | /wa/templates/status | set_template_status | 102 | demo/debug name |
| widgets.py | GET | /widgets/popup-config | popup_config_get | 89 | no ref found |
| widgets.py | POST | /widgets/popup-config | popup_config_save | 100 | no ref found |
| widgets.py | POST | /widgets/popup-wheel-coupons | popup_wheel_coupons | 111 | no ref found |
| widgets.py | GET | /widgets/popup-snippet | popup_snippet | 122 | no ref found |
| widgets.py | GET | /widgets/bio-config | bio_config_get | 141 | no ref found |
| widgets.py | POST | /widgets/bio-config | bio_config_save | 154 | no ref found |
| widgets.py | GET | /widgets/site-stats | site_stats | 240 | no ref found |
| widgets.py | GET | /widgets/beacon-snippet | beacon_snippet | 255 | no ref found |

## Safe reduction plan
1. **Quick wins:** delete the `demo/debug/test`-named endpoints first (lowest risk).
2. **Verify each `no ref found`:** `grep -rn "<full-path>" frontend/ app/ tests/ | grep -v app/api/`. Zero hits → deprecate.
3. **Batch & gate:** group confirmed-dead per router into one commit (return HTTP 410 or remove), keep diffs small.
4. **Verify loop:** prod_check.py + run_tests.bat (read pytest_run.log) → /ship → /health=production.
5. Realistic target: ~108 candidates here is the safe ceiling for pure dead-route removal; deeper 593→~400 cuts need product decisions (retire whole features/duplicate flows), not just dead endpoints.
