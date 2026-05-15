# Managed Services Setup Guide

## 1. Supabase (Postgres + PostGIS)

### Sign up
1. Go to [supabase.com](https://supabase.com) → **Start your project** (free tier, no credit card).
2. Create org `colab` → project name `colab-dev` → region **US East (N. Virginia)**.
3. Set a strong database password (save it — you'll need it for `DATABASE_URL`).

### Get the DB URL
Settings → Database → **Connection string** → **URI** tab:
```
postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

### Enable extensions
In the Supabase SQL Editor, run:
```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### Apply schemas
```bash
export SUPABASE_DB_URL="postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres"

# Apply base schema init (creates all service schemas + roles)
psql "$SUPABASE_DB_URL" -f scripts/db-init/01-schemas.sql

# Run alembic migrations for each service
bash scripts/deploy/migrate-supabase.sh
```

### Free tier limits
- 500 MB storage, 2 projects, 50,000 MAUs, unlimited API requests.

---

## 2. Upstash Redis

### Sign up
1. Go to [upstash.com](https://upstash.com) → **Create Database**.
2. Name: `colab-redis` | Region: **US-East-1** | Type: **Regional** | TLS: **enabled**.
3. Free tier: 10,000 commands/day, 256 MB.

### Get the URL
Console → your database → **Details** tab:
```
rediss://default:<password>@<endpoint>.upstash.io:6380
```

Set this as `REDIS_URL` in Fly secrets for all three services.

### Usage notes
- Sessions, rate-limit counters, idempotency keys.
- At 10k commands/day free limit: for testing that's ~7 req/min continuously; upgrade to Pay-As-You-Go ($0.2/100k) if you exceed it.

---

## 3. CloudAMQP — RabbitMQ

### Sign up
1. Go to [cloudamqp.com](https://cloudamqp.com) → **Get a managed RabbitMQ instance** → plan **Little Lemur (Free)**.
2. Name: `colab-dev` | Region: **Amazon Web Services / US-East-1**.

### Get the AMQP URL
Dashboard → your instance → **Details**:
```
amqps://<user>:<password>@<host>.cloudamqp.com/<vhost>
```

Set this as `RABBITMQ_URL` in Fly secrets.

### Free tier limits
- 1 M messages/month, 1 concurrent connection, 1 queue.
- For Stage 3 testing that's sufficient. Upgrade to **Tough Tiger** ($19/mo) for production.

---

## 4. Cloudflare R2 (Object Storage)

### Create bucket
1. Log into [Cloudflare dashboard](https://dash.cloudflare.com) → **R2** (left nav).
2. Create bucket: `colab-portfolio-prod` | Location: **Eastern North America (ENAM)**.
3. Repeat for: `colab-chat-files-prod`, `colab-mockup-assets-prod`.

### Get S3-compatible credentials
R2 → **Manage R2 API tokens** → **Create API token**:
- Permissions: **Object Read & Write**
- Scope: specific bucket or all buckets

You'll receive:
- `Access Key ID` → `R2_ACCESS_KEY_ID`
- `Secret Access Key` → `R2_SECRET_ACCESS_KEY`
- Endpoint: `https://<account-id>.r2.cloudflarestorage.com` → `R2_ENDPOINT`

### SDK configuration
R2 is S3-compatible. In your services, use boto3/aiobotocore with:
```python
import boto3
s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
```

### Free tier limits
- 10 GB storage, 1M Class A ops/month, 10M Class B ops/month, no egress fees.

---

## 5. Resend (Transactional Email)

Replaces AWS SES sandbox for Stage 3.

1. Sign up at [resend.com](https://resend.com) (free: 100 emails/day, 3,000/month).
2. Add and verify domain `colabclub.net` (add DNS TXT + DKIM records).
3. Create API key → set as `RESEND_API_KEY` in auth-svc Fly secrets.
4. Update `SES_FROM_ADDRESS` → `no-reply@colabclub.net`.

In auth-svc, swap the email sender to use Resend's API (HTTP POST to `https://api.resend.com/emails`).
