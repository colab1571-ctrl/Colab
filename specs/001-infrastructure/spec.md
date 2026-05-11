# 001 — Infrastructure Bootstrap

**Phase**: P0 — Infrastructure. **Owners**: platform.
**Mission**: Provision the AWS footprint (VPC, EKS, RDS, Redis, S3, MQ, SES, Secrets Manager, IAM, Route 53, ACM, GitHub OIDC) that every downstream service deploys onto. Establish the IaC + deploy pipeline that all other phases consume.

## In scope (from master §0 Architecture + §7 phase order)

- Terraform modules: `vpc`, `eks`, `rds`, `redis`, `s3`, `mq`, `ses`, `sns-mobile`, `secrets`, `iam-irsa`, `dns`, `acm`, `github-oidc` (skeletons exist; this phase fills bodies + applies).
- Postgres extensions: `postgis`, `vector` (pgvector).
- ElastiCache Redis: cluster mode, in-VPC, TLS in transit.
- S3 buckets: `colab-portfolio-<env>`, `colab-chat-files-<env>`, `colab-audit-logs-<env>`, `colab-mockup-assets-<env>`, `colab-web-static-<env>`. Versioning on all; CloudFront in front of portfolio + chat-files + mockup-assets + web-static.
- Amazon MQ for RabbitMQ: single-instance dev/staging, mirrored cluster prod.
- SES: domain identity + DKIM + SPF + DMARC for `<email-domain>`.
- SNS Mobile Push: APNs + FCM platform applications (credentials from §4/§6 INFRA.md).
- Secrets Manager: every env-var from `.env.example` mirrored as a SecretsManager entry (single per-service secret object).
- IRSA roles: one per microservice (auth-svc, profile-svc, …), scoped to read its own secret.
- Route 53 hosted zone + ACM wildcard cert.
- GitHub OIDC trust + `colab-github-deploy-<env>` role.

## Dependencies

- **External (manual sign-up first per `docs/INFRA.md`)**: AWS root + domain + GitHub Actions OIDC config.

## Owned entities (none)

This is infrastructure-only. No domain entities.

## API surface (none)

This is infrastructure. The "API" is `terraform plan` / `terraform apply` and the resulting AWS Console resources.

## Acceptance criteria

- `terraform/bootstrap.sh` idempotently provisions the remote state.
- `terraform -chdir=terraform/envs/dev plan` runs clean (no diff after apply).
- `kubectl get nodes` returns ≥3 healthy nodes in the EKS cluster.
- `psql $DATABASE_URL -c "CREATE EXTENSION postgis; CREATE EXTENSION vector;"` succeeds.
- `aws secretsmanager list-secrets` shows secret objects for each service.
- A test workload deploy via Helm proves IRSA-bound pod-to-Secret read works.
- GitHub Actions can assume the deploy role via OIDC (smoke `aws sts get-caller-identity` in a workflow).

## NFRs

- RDS Multi-AZ enabled in `prod`.
- RDS automated backups: 7d retention, daily snapshot.
- Redis primary + replica in `prod`.
- All resources tagged `Project=colab`, `Env=<env>`.
- Terraform state in S3 + DynamoDB lock; mandatory.

## Open

- India data localization specifics (DPDP). Likely satisfied via processor agreements + audit log; if region-replication is later required, an India ap-south-1 stack lands as a second env.
