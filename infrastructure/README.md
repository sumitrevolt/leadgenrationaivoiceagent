# LeadGen AI Voice Agent - Infrastructure

## 🏗️ Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           Google Cloud Platform                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │   Cloud Run      │    │    Vertex AI     │    │   Cloud SQL      │  │
│  │   (API + Voice)  │◄──►│   (Gemini LLM)   │    │  (PostgreSQL)    │  │
│  │   Auto-scaling   │    │   Rate Limited   │    │   Private IP     │  │
│  └────────┬─────────┘    └──────────────────┘    └────────┬─────────┘  │
│           │                                                │            │
│           │              ┌──────────────────┐              │            │
│           │              │   Memorystore    │              │            │
│           └──────────────┤     (Redis)      ├──────────────┘            │
│                          │   Cache/Queue    │                            │
│                          └──────────────────┘                            │
│                                                                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │  Secret Manager  │    │ Artifact Registry│    │ Cloud Monitoring │  │
│  │   API Keys       │    │ Container Images │    │ Alerts/Dashboards│  │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                        VPC Network                                │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │  │
│  │  │ App Subnet  │  │ Data Subnet │  │  ML Subnet  │               │  │
│  │  │ 10.0.1.0/24 │  │ 10.0.2.0/24 │  │ 10.0.3.0/24 │               │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## 📁 Directory Structure

```text
infrastructure/
├── terraform/
│   ├── main.tf                 # Main configuration
│   ├── variables.tf            # Input variables
│   ├── modules/
│   │   ├── networking/         # VPC, subnets, NAT
│   │   ├── security/           # IAM, service accounts
│   │   ├── database/           # Cloud SQL PostgreSQL
│   │   ├── redis/              # Memorystore Redis
│   │   ├── cloud_run/          # Cloud Run service
│   │   ├── secrets/            # Secret Manager
│   │   ├── storage/            # GCS buckets
│   │   ├── artifact_registry/  # Container registry
│   │   └── monitoring/         # Alerts, dashboards
│   └── environments/
│       ├── production.tfvars   # Production config
│       └── staging.tfvars      # Staging config
├── DEPLOYMENT.md               # Deployment guide
└── README.md                   # This file
```

## 🚀 Quick Start

### Prerequisites

- GCP Project with billing
- Terraform >= 1.5.0
- gcloud CLI authenticated

### Deploy

```bash
# 1. Set variables
export PROJECT_ID="your-project-id"
export TF_VAR_db_password="secure-password"  # nosecret (placeholder)
export TF_VAR_gemini_api_key="your-key"

# 2. Initialize
cd infrastructure/terraform
terraform init

# 3. Deploy
terraform apply -var-file="environments/production.tfvars"
```

## 🔒 Security Features

| Feature | Implementation |
|---------|----------------|
| **Network Isolation**  | Private VPC with 3-tier subnets        |
| **Database**           | Private IP only, no public access      |
| **Secrets**            | Google Secret Manager with rotation    |
| **Authentication**     | Workload Identity for CI/CD            |
| **IAM**                | Least privilege service accounts       |
| **Container Scanning** | Vulnerability scan before deploy       |
| **Audit Logging**      | Cloud Audit Logs enabled               |

## 📊 Monitoring & Alerts

| Metric           | Alert Threshold      |
|------------------|----------------------|
| Error Rate       | > 5% for 5 minutes   |
| P99 Latency      | > 5 seconds          |
| Instance Count   | > 80 instances       |
| Database CPU     | > 80%                |
| LLM Token Usage  | > 1M tokens/hour     |

## 💰 Cost Optimization

| Service   | Optimization                            |
|-----------|------------------------------------------|
| Cloud Run | Min instances = 2 (prod), 0 (staging)  |
| Gemini    | Flash model ($0.75/M tokens) vs Pro    |
| Cloud SQL | Autoscale disk, shared CPU for staging |
| Storage   | Lifecycle policies for audio files     |

## 🔄 CI/CD Pipeline

```text
Push to main → Test → Build → Scan → Deploy Staging → Smoke Test → Production (Canary)
                                                                    ↓
                                                            10% → 50% → 100%
```

## 📖 Related Documentation

- [Deployment Guide](DEPLOYMENT.md)
- [Cloud Build Config](../cloudbuild.yaml)
- [GitHub Actions](../.github/workflows/deploy.yml)
- [Production Dockerfile](../Dockerfile.production)
