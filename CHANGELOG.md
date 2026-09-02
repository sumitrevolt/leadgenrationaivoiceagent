# Changelog

All notable changes to the LeadGen AI Voice Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Production middleware stack (security headers, rate limiting, request tracing)
- Redis-based caching and distributed rate limiting
- Custom exception handling with structured error responses
- JSON logging for production (Cloud Logging compatible)
- Alembic database migrations
- Production deployment checklist
- Pre-commit hooks for code quality
- Secrets detection baseline
- Comprehensive production tests (29 tests)
- Nginx reverse proxy configuration
- Docker Compose production override

### Changed
- Database models now use lazy engine initialization
- Logger supports both colored console and JSON output
- Main application includes graceful shutdown for all services

### Fixed
- Missing `deepgram_api_key` in settings
- Missing `log_level` configuration option

## [1.0.0] - 2024-01-01

### Added

#### Core Platform
- Multi-tier B2B lead generation platform
- 24/7 automated platform orchestrator
- Multi-tenant architecture with subscription tiers
- Automated client onboarding (trial ? paid)

#### Voice Agent
- AI-powered voice agent with natural conversations
- Multi-LLM support (Gemini, GPT-4, Claude)
- Speech-to-Text (Deepgram, Google)
- Text-to-Speech (Edge TTS, ElevenLabs, Azure)
- Intent detection and objection handling
- Hinglish language support

#### Lead Scraping
- Google Maps business scraper
- IndiaMart B2B scraper
- JustDial scraper
- LinkedIn company scraper
- Rate limiting and proxy support

#### Telephony
- Twilio integration (international)
- Exotel integration (India)
- Call queue management
- Concurrent call handling
- Call recording and transcription

#### Integrations
- HubSpot CRM sync
- Zoho CRM sync
- Google Sheets export
- WhatsApp Business notifications
- Email notifications

#### ML/AI
- Automatic model training pipeline
- Feedback loop for continuous improvement
- Vector store for conversation context
- Lead scoring optimization

#### Infrastructure
- Terraform modules for GCP
- Cloud Run deployment
- Cloud SQL PostgreSQL
- Memorystore Redis
- Secret Manager
- GitHub Actions CI/CD

### Security
- API key authentication
- VPC with private subnets
- Workload Identity Federation
- DND registry compliance (India)

---

## Version History

### Versioning Scheme

- **MAJOR**: Breaking API changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

### Upgrade Notes

#### Upgrading to 1.0.0
1. Run database migrations: `alembic upgrade head`
2. Update environment variables (see `.env.example`)
3. Review `PRODUCTION_CHECKLIST.md`

---

[Unreleased]: https://github.com/sumitrevolt/leadgenrationaivoiceagent/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/sumitrevolt/leadgenrationaivoiceagent/releases/tag/v1.0.0
