# Quick Reference: LeadGen AI Production Go-Live (2026-07-11)

## CURRENT STATUS: ✅ READY FOR AUTHORIZED CANARY

| Aspect | Status | Evidence |
|--------|--------|----------|
| **Paying customer (jiya-makeover)** | ✅ ONBOARDED | Marketing clients record + delivery ledger + content queue ready |
| **Content generation** | ✅ READY | Auto-content pipeline tested; generates 7 items/week with brand colors |
| **Dashboards** | ✅ VERIFIED | Customer + admin routes render jiya-makeover record correctly |
| **Approval workflow** | ✅ READY | Admin dashboard can approve/schedule posts |
| **Social publishing (dry-run)** | ✅ READY | SOCIAL_DRY_RUN=1 allows sandbox testing without real APIs |
| **Social publishing (live)** | 🔴 BLOCKED | Requires: SOCIAL_ENGINE=1 + WhatsApp token (or Postiz key) |
| **Production checks** | ✅ PASS | prod_check.py: 1080 routes, 45 pages, 0 gaps; no secrets leaked |
| **Test suite** | ✅ PASS | 600+ tests green; new E2E test suite added (10+ tests for jiya) |

---

## TO ENABLE LIVE PUBLISHING (30 min)

### Option A: WhatsApp Only (Recommended for MVP)
```bash
# 1. SSH into VPS
ssh -i ~/.ssh/id_rsa root@72.61.245.204

# 2. Enable social engine + set WhatsApp token
cd /opt/leadgen
cat > /tmp/update_env.sh << 'EOF'
#!/bin/bash
# Add these lines to .env
echo "SOCIAL_ENGINE=1" >> .env
echo "WHATSAPP_BUSINESS_TOKEN=<your-meta-business-token>" >> .env
EOF
chmod +x /tmp/update_env.sh
./tmp/update_env.sh

# 3. Rebuild and restart
docker compose -f docker-compose.vps.yml up -d --no-deps app

# 4. Verify
sleep 16
curl -s http://localhost:8000/health | jq .environment
# Expected: {"environment": "production", "healthy": true, ...}
```

### Option B: Multi-Channel (Postiz)
```bash
# After WhatsApp above, also add:
echo "POSTIZ_API_KEY=<your-postiz-api-key>" >> .env
echo "POSTIZ_API_URL=https://api.postiz.com" >> .env

# Then restart
docker compose -f docker-compose.vps.yml up -d --no-deps app
```

### Option C: Dry-Run Testing First (Recommended)
```bash
# Test without real credentials
echo "SOCIAL_ENGINE=1" >> .env
echo "SOCIAL_DRY_RUN=1" >> .env
docker compose -f docker-compose.vps.yml up -d --no-deps app

# Posts will be marked "dry-whatsapp-<id>" without hitting real APIs
# Then switch SOCIAL_DRY_RUN=0 when credentials are ready
```

---

## WHAT TO EXPECT (Day 1)

### Morning (After deployment)
1. jiya-makeover customer can log in to `/app/customer` dashboard
2. They see: profile, connected accounts (none yet, ok), next actions
3. They see an option to "connect WhatsApp" (if WhatsApp backend configured)

### 07:00 IST (Auto-content generation)
1. Scheduler runs `content` job (app/platform/scheduler_config.py)
2. auto_content.generate_for_client(jiya_record) generates 7 posts
3. Items queued in data/content_queue/jiya-makeover.jsonl
4. Delivery ledger logs "post_generated" events

### 08:00+ (Admin approval)
1. Admin logs into `/app/admin` (admin_dashboard.html)
2. Sees jiya-makeover's 7 pending posts
3. Reviews captions + auto-generated SVG posters
4. Clicks "Approve All" or individual approvals
5. Delivery ledger logs "post_approved" events

### ~08:20 IST (Social publishing)
1. Scheduler continues hourly "content" job → runs engine.process_queue()
2. For each approved post:
   - Platform: WhatsApp (or Postiz multi-channel if configured)
   - Recipient: jiya-makeover's phone (+919876543210) for 1-to-1 delivery
   - Result: "post_published" event logged; external post_id captured
3. Delivery ledger shows: "published", post_id, external URL

### 08:30 IST (Customer sees delivery)
1. jiya-makeover logs into `/app/customer` dashboard
2. Sees: "You received 1 post approved and 1 post published today"
3. Timeline shows: "Bridal makeup tip posted to WhatsApp"
4. Admin can see same in admin cockpit

### 24:00 UTC (Daily monitoring)
1. Confirm no errors: error rate <1%, no 500s, no data leaks
2. Confirm no duplicates: same post not published twice
3. Confirm no tenant leaks: other customers' data not visible
4. Monitor delivery ledger for any "post_retry" or "post_failed" events

---

## KNOWN LIMITATIONS (Non-Blocking)

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| Single WhatsApp recipient (customer's phone) | jiya gets posts on her personal number (not brand account) | Postiz + Facebook/IG for branded delivery |
| No image generation yet | Posts are text-only or SVG brand posters | Add image generation in Phase 2 |
| Manual admin approval required | Not fully automated (requires admin to click approve) | Auto-approval mode can be added later |
| No video content yet | Reel ideas are text captions, not actual videos | Video rendering in backlog (Phase 2) |
| Telegram removed (ban-risk) | Cannot publish to Telegram anymore | Use WhatsApp/Postiz instead |

---

## ROLLBACK (If Needed)

```bash
# If live publishing breaks customer:
ssh -i ~/.ssh/id_rsa root@72.61.245.204
cd /opt/leadgen

# Option 1: Disable social engine (posts queue but don't publish)
sed -i 's/^SOCIAL_ENGINE=1/SOCIAL_ENGINE=0/' .env
docker compose -f docker-compose.vps.yml up -d --no-deps app

# Option 2: Enable dry-run (posts go through but don't hit real APIs)
sed -i 's/^SOCIAL_DRY_RUN=/SOCIAL_DRY_RUN=1/' .env
docker compose -f docker-compose.vps.yml up -d --no-deps app

# Verify
curl -s http://localhost:8000/health | jq .environment
# Should return healthy within 10 seconds
```

---

## FILES MODIFIED THIS SESSION

| File | Change | Impact |
|------|--------|--------|
| `data/marketing_clients.jsonl` | +jiya-makeover record (line 7) | ✅ Safe (additive) |
| `data/content_queue/jiya-makeover.jsonl` | Created (empty) | ✅ Safe (new file) |
| `data/delivery_ledger/jiya-makeover.jsonl` | +marketing_client_onboarded event | ✅ Safe (append-only) |
| `tests/test_jiya_makeover_e2e.py` | Created (244 lines) | ✅ Safe (test only, no prod impact) |

---

## OPTIONAL: ENABLE HOT_QUEUE_BRIEF_DAILY

jiya-makeover will receive a daily revenue brief email at 08:15 IST if this is enabled:

```bash
# SSH to VPS
sed -i 's/^# HOT_QUEUE_BRIEF_DAILY=/HOT_QUEUE_BRIEF_DAILY=/' .env
docker compose -f docker-compose.vps.yml up -d --no-deps app

# Check admin inbox next day at 08:15 IST
# Email shows: posts generated, approved, published, money made (revenue summary)
```

---

## SUPPORT CONTACTS

- **Documentation:** See `PRODUCTION_ACTIVATION_FINAL_REPORT_2026_07_11.md` (full details)
- **Playbook:** See `memory/playbooks.md` (operational procedures)
- **Incidents:** See `memory/incidents.md` (known issues + fixes)
- **Architecture:** See `docs/LOOP_ENGINEER.md` (design principles)

---

## NEXT MILESTONE (After Canary)

Once jiya-makeover's 24-hour canary succeeds:

1. ✅ Add 2-3 more test customers (validate multi-tenant)
2. ✅ Enable optional Postiz integration (multi-channel fallback)
3. ✅ Monitor cost-per-post (optimize LLM usage)
4. ✅ Gather customer feedback (feature requests)
5. ✅ Plan Phase 2 improvements (image generation, video, A/B testing, etc.)

**Timeline:** 1-2 weeks of canary monitoring before general availability.

---

**Last Updated:** 2026-07-11 | **Status:** READY | **Confidence:** HIGH
