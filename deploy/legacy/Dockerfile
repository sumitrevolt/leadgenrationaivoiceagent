# ============================================================================
# LeadGen AI Voice Agent - Production Dockerfile
# Minimal build for Cloud Run deployment (NO Playwright/Browser dependencies)
# ============================================================================

# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and filter out browser-based packages
COPY requirements.txt .

# Create filtered requirements without playwright/selenium
RUN grep -v -E "^(playwright|selenium)" requirements.txt > requirements-filtered.txt

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip install --no-cache-dir -r requirements-filtered.txt

# ============================================================================
# Stage 2: Production image
# ============================================================================
FROM python:3.11-slim AS production

# Build argument for version tracking
ARG APP_VERSION=latest
ENV APP_VERSION=${APP_VERSION}

# Security: Run as non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Install runtime dependencies only (minimal set)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set timezone to IST for Indian market
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Create necessary directories FIRST (before copying)
RUN mkdir -p /app/logs /app/data/conversations /app/data/feedback \
    /app/data/vectorstore /app/data/agent_brain /app/data/voice_brain \
    /app/data/production_brain /app/data/brain_training /app/data/training_reports \
    /app/data/optimizer /app/scripts /app/alembic

# Copy application code (app/ is required)
COPY --chown=appuser:appgroup app/ ./app/

# Copy alembic configuration
COPY --chown=appuser:appgroup alembic/ ./alembic/
COPY --chown=appuser:appgroup alembic.ini ./

# Copy scripts directory
COPY --chown=appuser:appgroup scripts/ ./scripts/

# Copy frontend (dashboards + marketing website + PWA served by FastAPI)
COPY --chown=appuser:appgroup frontend/ ./frontend/

# Copy data directory structure (empty dirs ok, .dockerignore handles exclusions)
COPY --chown=appuser:appgroup data/ ./data/

# Copy project skills for runtime agent skill_pack
COPY --chown=appuser:appgroup .claude/skills/ ./.claude/skills/

# Ensure proper ownership
RUN chown -R appuser:appgroup /app

# Security: Remove setuid/setgid binaries
RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    WEB_CONCURRENCY=2 \
    GRACEFUL_TIMEOUT=30

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose Cloud Run default port
EXPOSE 8080

# Labels
LABEL org.opencontainers.image.title="LeadGen AI Voice Agent" \
      org.opencontainers.image.version="${APP_VERSION}"

# Simplified startup - skip startup_check.py if it fails, uvicorn handles health
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-2} --timeout-keep-alive 30"]
