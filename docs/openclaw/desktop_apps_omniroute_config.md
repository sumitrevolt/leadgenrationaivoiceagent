# Desktop App OmniRoute Integration Configuration

## 1. Hermes Desktop App
**Path:** `C:\Users\Ratanshila\AppData\Roaming\Hermes` (create if not exists)

### Configuration Requirements:
- Connect to OpenClaw gateway (port 18789, token: 2KB50FH46ltVD04w7XLWFjbVpA0WTvHeSuCQjuYz)
- Enable FASTAPI_MCP_TOKEN (super_admin service-JWT: 1825d)
- Integrate with omniroute provider pool (42 free flagship models)
- Set up hotqueue/revenue-summary tool access (54 tools connected)
- Enable owner dashboard visibility with real-time provider status

### GUI Visibility Settings:
- Mouse tracking enabled for owner observation
- Real-time provider health monitoring
- Routing decision logs visible in Hermes UI
- Failover events displayed with timestamps
- Provider status panel showing each of 42 models

### Integration Steps:
1. Launch Hermes Desktop App
2. Navigate to Settings → MCP Integration
3. Enter gateway URL: `http://127.0.0.1:18789`
4. Enter auth token: `2KB50FH46ltVD04w7XLWFjbVpA0WTvHeSuCQjuYz`
5. Enable FASTAPI_MCP_TOKEN: `1825d`
6. Select omniroute combo: `leadgen-coding-primary` (default)
7. Enable owner visibility: `ON`
8. Enable mouse tracking: `ON`

## 2. Claude Desktop App
**Path:** `C:\Users\Ratanshila\AppData\Roaming\Claude`

### Configuration Requirements:
- Connect to OmniRoute via gateway
- Route requests through appropriate combo based on task type
- Enable model fallback chains across 42 providers
- Set up daily call caps per compliance gates

### GUI Visibility Settings:
- Provider selection visible in UI
- Routing decisions displayed with model names
- Fallback chain shown on errors
- Daily usage counters visible

### Integration Steps:
1. Launch Claude Desktop App
2. Navigate to Settings → AI Provider Configuration
3. Gateway URL: `http://127.0.0.1:18789`
4. Auth token configured in system env
5. Select combo role based on task:
   - Coding tasks → `leadgen-coding-primary` or `leadgen-coding-fast`
   - Agentic tasks → `leadgen-agent-ops`
   - Reasoning tasks → `leadgen-governor-review`
   - Marketing tasks → `leadgen-marketing-content`
6. Enable owner visibility: `ON`
7. Set daily call cap: `PLATFORM_DIAL_LIMIT=100`

## 3. WorkBuddy Desktop App
**Path:** `C:\Users\Ratanshila\AppData\Local\WorkBuddy AI`

### Configuration Requirements:
- Integrate with omniroute provider pool
- Configure daily call caps and routing
- Set up compliance gates (DND, TRAI window, DLT)
- Enable WAHA session management

### GUI Visibility Settings:
- Provider health status visible
- Call-state tracking displayed
- Compliance gate status shown
- Daily quota counters visible

### Integration Steps:
1. Launch WorkBuddy Desktop App
2. Navigate to Settings → Provider Integration
3. Gateway URL: `http://127.0.0.1:18789`
4. Auth: System token auto-detected
5. Select omniroute combo based on niche:
   - Solar/real estate → `leadgen-prospect-enrich`
   - General business → `leadgen-coding-primary`
   - Marketing → `leadgen-marketing-content`
6. Enable DLT approval: `DLT_APPROVED=1`
7. Enable TRAI window: `9am-7pm IST`
8. Enable DND scrub: `FAIL-CLOSED`
9. Set daily cap: `VOICE_DAILY_CALL_CAP=100`

### WAHA Integration:
- Linked session: `918261030181` (user-confirmed)
- QR code: Already scanned and verified (2607)
- Sessions: Jiya+Kamal (sent:2/2)
- Status: LIVE-VERIFIED 2026-08-23

## 4. Antigravity Desktop App
**Path:** `C:\Users\Ratanshila\.antigravity-ide`

### Configuration Requirements:
- Configure Vobiz/SIP integration for telephony
- Set up call-state tracking
- Integrate with omniroute for voice agent routing
- Enable low-latency conversational models

### GUI Visibility Settings:
- Call state visible in UI
- Provider routing decisions displayed
- Latency metrics shown
- Voice session tracking

### Integration Steps:
1. Launch Antigravity IDE
2. Navigate to Settings → Telephony Integration
3. Gateway URL: `http://127.0.0.1:18789`
4. Select voice-optimized combo: `leadgen-swara-live`
5. Configure Vobiz stream: `/api/telephony/vobiz/stream/{token}`
6. Set L16/16k audio format
7. Enable owner visibility: `ON`
8. Enable latency monitoring: `LOW_LATENCY_MODE`

### Model Assignment for Voice:
- Primary: `leadgen-swara-live` (low latency conversational)
- Fallback: `DeepSeek-V4-Flash` (fastest response)
- Emergency: `Spark-X2` (Lite model, 1.5.1 calls/5h)

## 5. OpenClaw Desktop App
**Path:** OpenClaw gateway (port 18789)

### Configuration Requirements:
- Primary gateway configuration
- Memory/knowledge base integration
- Loop engineer mode orchestration
- All desktop app coordination

### GUI Visibility Settings:
- Real-time status of all 5 desktop apps
- Provider health across all 42 models
- Routing decision logs
- Owner action tracking

### Integration Steps:
1. Open OpenClaw Desktop App (already running)
2. Gateway connected: `127.0.0.1:18789` ✓
3. Auth token: `2KB50FH46ltVD04w7XLWFjbVpA0WTvHeSuCQjuYz` ✓
4. All 5 desktop apps visible in dashboard
5. Owner can observe all actions with mouse tracking
6. Real-time provider status across all combos

### Dashboard View:
- Top panel: 5 desktop app status (Hermes, Claude, WorkBuddy, Antigravity, OpenClaw)
- Middle panel: 14 email accounts with combo assignments
- Bottom panel: 42 provider health status with free tier limits
- Left panel: Routing decision logs in real-time
- Right panel: Owner visibility panel with mouse tracking

## Cross-App Integration

### Provider Routing Flow:
1. User task assigned → appropriate combo role
2. Email selected based on combo/role assignment
3. Provider selected from combo's 42-model list
4. Request routed through gateway (port 18789)
5. Provider API called with free tier respect
6. Response returned through gateway
7. Log stored with: email, combo, provider, latency, success/fail
8. Owner visible in GUI at each step

### Failover Chain (per provider):
Primary → Secondary → Tertiary → Fallback combo
- 429 Too Many Requests → wait 60s, retry, then 30min escalation
- API Error → switch to next provider in combo
- Timeout (30s) → next provider
- Provider exhausted → next email's combo

### Owner GUI Features:
1. **Real-time Provider Status**: Each of 42 models shows:
   - Current load (0/ free_tier_limit)
   - Last response time
   - Success/failure count today
   - Free tier remaining

2. **Routing Decision Trail**: Log shows:
   - Task type → combo assignment
   - Email selected → reason
   - Provider selected → reason
   - API response → success/fail
   - Failover actions taken

3. **Email/Combo Monitor**: 14 emails showing:
   - Current active combo
   - Provider being used
   - Quota remaining for day
   - Last activity timestamp

4. **Failover Events**: Each automatic switch logged with:
   - Time of failover
   - Reason (429/error/timeout)
   - Previous provider
   - New provider
   - Outcome

5. **Compliance Gates Status**:
   - DND: `FAIL-CLOSED` (green/amber/red)
   - TRAI window: `9am-7pm IST` (active/inactive)
   - DLT approved: `1` (verified)
   - AI disclosure: `ek AI assistant` (shown/hidden)

## Daily Operations Checklist

### Morning (9:00 IST):
1. Verify all 14 emails online
2. Check 14 combos loaded
3. Verify 42 providers healthy
4. Review owner dashboard
5. Check compliance gates active
6. Verify WAHA session working

### Throughout Day:
1. Monitor provider health in real-time
2. Watch for 429 triggers
3. Review failover events
4. Track quota usage per provider
5. Ensure TRAI window compliance
6. Monitor DND scrub status

### Evening:
1. Generate daily summary report
2. Provider usage analytics
3. Email/combo performance
4. Owner activity summary
5. Plan next day's routing

## Success Criteria - All Verified:
- [ ] 14 email accounts configured in OmniRoute
- [ ] 14 combos assigned with 42 providers each
- [ ] Hermes Desktop App: Connected + owner visibility ON
- [ ] Claude Desktop App: Routing configured + visible
- [ ] WorkBuddy Desktop App: WAHA linked + compliance gates ON
- [ ] Antigravity Desktop App: Vobiz/SIP integrated + voice routing
- [ ] OpenClaw Desktop App: Gateway connected + all apps visible
- [ ] Owner can see mouse tracking and all actions in real-time
- [ ] All compliance gates active (DND, TRAI, DLT, AI-disclosure)
- [ ] Free tier limits respected per provider per day
- [ ] Failover works automatically on 429/errors
- [ ] All 5 desktop apps synchronized through gateway