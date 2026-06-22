# ✅ Production Deployment Checklist
## LeadGen AI Voice Agent Platform

Use this checklist before every production deployment.

### Quick Validation
Run the pre-deployment validation script:
```bash
python scripts/validate_deployment.py --env production --strict
```

---

## 🔐 Security

- [ ] **Secrets Management**
  - [ ] Run: `python scripts/setup_secrets.py --project-id YOUR_PROJECT --env production`
  - [ ] All API keys stored in Secret Manager (not .env files)
  - [ ] Database passwords rotated
  - [ ] JWT secret key is cryptographically random (32+ characters)
  - [ ] No hardcoded credentials in code

- [ ] **Authentication & Authorization**
  - [ ] API key authentication enabled for all protected endpoints
  - [ ] Rate limiting configured
  - [ ] CORS origins restricted to known domains
  - [ ] Admin endpoints protected

- [ ] **Network Security**
  - [ ] HTTPS enforced (TLS 1.2+)
  - [ ] VPC configured with private subnets
  - [ ] Database accessible only from VPC
  - [ ] Firewall rules reviewed

- [ ] **Compliance**
  - [ ] DND check enabled for India
  - [ ] Call recording disclosure in scripts
  - [ ] GDPR/data privacy reviewed
  - [ ] Terms of service updated

---

## ⚡ Database

- [ ] **Configuration**
  - [ ] Connection pooling configured (20+ connections)
  - [ ] Read replicas set up (for high traffic)
  - [ ] Automated backups enabled
  - [ ] Point-in-time recovery enabled

- [ ] **Migrations**
  - [ ] All migrations applied: `alembic upgrade head`
  - [ ] Migration tested on staging first
  - [ ] Rollback plan documented
  - [ ] Indexes created for frequently queried columns

- [ ] **Performance**
  - [ ] Query logging enabled for slow queries (>1s)
  - [ ] Database monitoring dashboard set up
  - [ ] Connection limits adequate

---

## 🚀 Application

- [ ] **Environment**
  - [ ] Copy `.env.production.template` to `.env.production`
  - [ ] `APP_ENV=production`
  - [ ] `DEBUG=false`
  - [ ] `LOG_LEVEL=INFO`
  - [ ] All required environment variables set

- [ ] **Dependencies**
  - [ ] All packages pinned to specific versions
  - [ ] Security vulnerabilities scanned
  - [ ] No dev dependencies in production

- [ ] **Configuration**
  - [ ] `AUTO_START_PLATFORM=true` (or as desired)
  - [ ] Telephony provider configured (Twilio/Exotel)
  - [ ] LLM provider configured (Gemini/OpenAI)
  - [ ] CRM integrations configured

---

## 📞 Telephony

- [ ] **Twilio/Exotel Setup**
  - [ ] Phone numbers purchased
  - [ ] Webhook URLs configured and accessible
  - [ ] TwiML/XML responses tested
  - [ ] Call recording enabled

- [ ] **Voice Quality**
  - [ ] TTS voice tested (natural sounding)
  - [ ] STT accuracy verified
  - [ ] Latency tested (<500ms round trip)

- [ ] **Compliance**
  - [ ] Caller ID configured correctly
  - [ ] Working hours enforced (9 AM - 6 PM IST)
  - [ ] DND registry integration working

---

## 🤖 AI/ML
  - [ ] Model selected (Gemini 1.5 Flash recommended for cost)
  - [ ] Token limits configured
  - [ ] Fallback model configured
  - [ ] Cost monitoring enabled

- [ ] **ML Pipeline**
  - [ ] Vector store initialized
  - [ ] Training scheduler running
  - [ ] Feedback loop capturing data

---

## ?? Monitoring

- [ ] **Logging**
  - [ ] Structured logging enabled
  - [ ] Log aggregation set up (Cloud Logging)
  - [ ] Error tracking enabled (Sentry)

- [ ] **Metrics**
  - [ ] Health check endpoint responding
  - [ ] Prometheus metrics exported
  - [ ] Dashboard created in Cloud Monitoring

- [ ] **Alerting**
  - [ ] Error rate alerts configured
  - [ ] Latency alerts configured
  - [ ] Resource utilization alerts
  - [ ] On-call rotation set up

---

## ?? Deployment

- [ ] **Container**
  - [ ] Docker image built with production Dockerfile
  - [ ] Image scanned for vulnerabilities
  - [ ] Non-root user configured
  - [ ] Health check passing

- [ ] **Infrastructure**
  - [ ] Terraform state backed up
  - [ ] Auto-scaling configured (min 2, max 100)
  - [ ] Load balancer configured
  - [ ] CDN configured (if applicable)

- [ ] **CI/CD**
  - [ ] Tests passing
  - [ ] Canary deployment configured
  - [ ] Rollback procedure tested
  - [ ] Deployment notifications set up

---

## ?? Integrations

- [ ] **WhatsApp**
  - [ ] Business API connected
  - [ ] Message templates approved
  - [ ] Webhook verified

- [ ] **CRM**
  - [ ] HubSpot/Zoho connected
  - [ ] Field mapping verified
  - [ ] Sync tested

- [ ] **Email**
  - [ ] SMTP configured
  - [ ] SPF/DKIM records set
  - [ ] Templates tested

---

## ?? Pre-Launch Testing

- [ ] **Functional Tests**
  - [ ] End-to-end call flow tested
  - [ ] Lead scraping tested
  - [ ] Appointment booking tested
  - [ ] CRM sync tested

- [ ] **Load Testing**
  - [ ] Concurrent call capacity verified
  - [ ] API rate limits tested
  - [ ] Database connection limits tested

- [ ] **Recovery Testing**
  - [ ] Database failover tested
  - [ ] Service restart tested
  - [ ] Rollback procedure tested

---

## ?? Post-Deployment

- [ ] **Verification**
  - [ ] Health check passing
  - [ ] API documentation accessible (if enabled)
  - [ ] Sample call made successfully
  - [ ] Logs flowing correctly

- [ ] **Communication**
  - [ ] Team notified of deployment
  - [ ] Change log updated
  - [ ] Customer communication (if applicable)

---

## ?? Rollback Plan

If issues are detected:

1. **Immediate Rollback**
   ```bash
   gcloud run services update-traffic leadgen-ai-api \
     --region=asia-south1 \
     --to-revisions=PREVIOUS_REVISION=100
   ```

2. **Database Rollback** (if migration issues)
   ```bash
   alembic downgrade -1
   ```

3. **Notify Team**
   - Post in #incidents channel
   - Page on-call engineer if severe

---

## ?? Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Platform Lead | [Name] | [Phone] |
| DevOps | [Name] | [Phone] |
| On-Call | [Rotation] | [PagerDuty] |

---

**Last Updated:** [Date]  
**Approved By:** [Name]
