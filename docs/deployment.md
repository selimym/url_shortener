# Deployment Guide

The app runs on **GCP Cloud Run** (stateless container, scales to zero).
State is handled by two external free-tier services:
- **Neon** — managed PostgreSQL
- **Upstash** — managed Redis

## Prerequisites

- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and on your PATH
- Docker installed
- A GCP project with billing enabled
- A [Neon](https://neon.tech) account
- An [Upstash](https://upstash.com) account

## One-time setup

### 1. Authenticate and configure GCP

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com
```

### 2. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create url-shortener \
  --repository-format=docker \
  --location=europe-west2

gcloud auth configure-docker europe-west2-docker.pkg.dev
```

### 3. Create external services

**Neon (PostgreSQL):**
1. Create a project at neon.tech
2. Copy the connection string — it looks like:
   `postgresql://user:pass@ep-xxx.eu-west-2.aws.neon.tech/neondb?sslmode=require`

**Upstash (Redis):**
1. Create a database at upstash.com, pick `eu-west-2` region
2. Copy the Redis URL — it looks like:
   `rediss://default:pass@xxx.eu-west-1.upstash.io:6379`
   (note: `rediss://` with double s = TLS, required by Upstash)

### 4. Run database migrations

Do this once before the first deploy. Alembic needs the sync psycopg2 driver:

```bash
pip install psycopg2-binary
DB_URL="postgresql://user:pass@ep-xxx.eu-west-2.aws.neon.tech/neondb?sslmode=require" \
  alembic upgrade head
```

### 5. Prepare the Cloud Run config file

```bash
cp cloud-run.yaml.example cloud-run.yaml
```

Edit `cloud-run.yaml` and fill in:
- `YOUR_PROJECT_ID` — your GCP project ID (e.g. `url-shortener-selim`)
- `YOUR_NEON_CONNECTION_STRING` — from step 3, replace `postgresql://` with `postgresql+asyncpg://`
- `YOUR_UPSTASH_CONNECTION_STRING` — from step 3
- Leave `YOUR_CLOUD_RUN_URL` as a placeholder for now (see step 7)

### 6. Build and push the Docker image

```bash
docker build -t europe-west2-docker.pkg.dev/YOUR_PROJECT_ID/url-shortener/app:latest .
docker push europe-west2-docker.pkg.dev/YOUR_PROJECT_ID/url-shortener/app:latest
```

### 7. Deploy to Cloud Run

```bash
gcloud run services replace cloud-run.yaml --region europe-west2
```

Then allow public access:

```bash
gcloud run services add-iam-policy-binding url-shortener \
  --region europe-west2 \
  --member="allUsers" \
  --role="roles/run.invoker"
```

The deploy command outputs a URL like `https://url-shortener-xxx-ew.a.run.app`.
Copy it and update `BASE_URL` in `cloud-run.yaml`, then re-deploy:

```bash
# Edit cloud-run.yaml: set BASE_URL to your actual Cloud Run URL
gcloud run services replace cloud-run.yaml --region europe-west2
```

## Redeploying after code changes

```bash
docker build -t europe-west2-docker.pkg.dev/url-shortener-selim/url-shortener/app:latest .
docker push europe-west2-docker.pkg.dev/url-shortener-selim/url-shortener/app:latest
gcloud run services replace cloud-run.yaml --region europe-west2
```

## Running migrations after schema changes

```bash
DB_URL="postgresql://user:pass@ep-xxx.eu-west-2.aws.neon.tech/neondb?sslmode=require" \
  alembic upgrade head
```

Always run migrations before deploying the new image.
