# 001 — Infrastructure Bootstrap · Implementation Plan

> Status: **PLAN — Phase 4 (P0)**. Single consolidated plan (research + data model + contracts + tasks folded in).
> Scope: Provision the AWS footprint + IaC + deploy pipeline that every Phase ≥1 service consumes.
> Region: `us-east-1` primary. Envs: `dev`, `staging`, `prod`. Project tag: `Project=colab`.

---

## 1. Mission Recap

Stand up the immutable, IaC-managed AWS substrate (VPC, EKS, RDS Postgres 16+PostGIS+pgvector, ElastiCache Redis, S3+CloudFront, Amazon MQ for RabbitMQ, SES, SNS Mobile Push, Secrets Manager, IRSA, Route 53, ACM, GitHub OIDC) on which the 12+ FastAPI microservices, three Next.js web apps, and the RN/Expo client deploy. The bootstrap output is a reproducible `terraform apply` per env, a working `kubectl` against EKS, a base Helm chart (`charts/svc/`) every microservice consumes, and an OIDC-only GitHub Actions deploy path with **no static AWS keys in production**. Multi-AZ + replica posture supports the 99.9% availability target.

---

## 2. Research Findings

> Each row = chosen version (locked for this milestone) + single most important config knob + the failure mode we're explicitly avoiding. Where a URL is cited it is high-confidence canonical; otherwise navigate via the provider name.

### 2.1 Terraform AWS provider
- **Version**: `hashicorp/aws ~> 5.40` (already pinned in `envs/dev/main.tf`). Terraform CLI `>= 1.7`.
- **Knob**: `provider.default_tags` — every resource auto-tagged `Project=colab Env=<env> ManagedBy=terraform`. We must NOT override tags inside modules (causes drift).
- **Failure mode**: Forgetting to set `force_destroy=false` on stateful buckets/tables → accidental nuke on `terraform destroy`. Default to protective settings; only the tfstate bootstrap S3 bucket has versioning + retain.
- Ref: registry.terraform.io/providers/hashicorp/aws/latest

### 2.2 EKS module pattern
- **Version**: `terraform-aws-modules/eks/aws ~> 20.x` (clean break from v19 IAM patterns — uses `aws_eks_access_entry` instead of `aws-auth` ConfigMap).
- **Knob**: `enable_cluster_creator_admin_permissions = true` during bootstrap (otherwise you lock yourself out). After bootstrap, switch to access entries for human + role principals.
- **Failure mode**: Forgetting to wire IRSA OIDC provider before the addons that need it (`aws-ebs-csi-driver`, `aws-load-balancer-controller`) — those addons silently fail PV creation / ingress provisioning.
- Ref: registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest

### 2.3 RDS Postgres 16 + PostGIS + pgvector
- **Engine**: `aws_db_instance` engine `postgres`, `engine_version = "16.4"` (PostGIS 3.4 + pgvector 0.7 ship in 16.x parameter group); apply group `default.postgres16` overridden by a custom group enabling `shared_preload_libraries = pg_stat_statements,pgvector` (note: pgvector is per-DB extension, not preload; preload only needed for monitoring extensions).
- **Knob**: `parameter_group` must set `rds.force_ssl=1`. **Extensions are NOT created by Terraform** — provisioner runs `CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS vector;` post-create via a one-shot job in EKS (idempotent).
- **Failure mode**: Picking a `db.t4g.*` instance type for prod — pgvector ANN index build is CPU-bound; t-class throttles silently. Use `db.m6g.large` minimum for prod.
- Multi-AZ in prod, single-AZ in dev. `backup_retention_period=7`, `delete_automated_backups=false`, `deletion_protection=true` in prod.

### 2.4 ElastiCache Redis (cluster mode)
- **Engine**: `aws_elasticache_replication_group`, `engine = "redis"`, `engine_version = "7.1"`, `cluster_mode` enabled in prod (`num_node_groups=2`, `replicas_per_node_group=1`).
- **Knob**: `transit_encryption_enabled = true`, `at_rest_encryption_enabled = true`, `auth_token` set from `random_password` → Secrets Manager. Client must use `rediss://` URI.
- **Failure mode**: Mixing cluster-mode-enabled URL into a non-cluster-aware client (default `redis-py` works with cluster only via `RedisCluster` class). Document the URL distinction in the service's README.
- Dev: single-node `cache.t4g.micro` (cluster mode disabled — fine for dev).

### 2.5 Amazon MQ for RabbitMQ
- **Engine**: `aws_mq_broker`, `engine_type = "RabbitMQ"`, `engine_version = "3.13"`.
- **Knob**: `deployment_mode = "CLUSTER_MULTI_AZ"` in prod (3-node cluster, mirrored queues), `SINGLE_INSTANCE` in dev/staging. **`publicly_accessible = false`** (must be VPC-only). Credentials via Secrets Manager rotation.
- **Failure mode**: Maintenance window patching reboots brokers — a `SINGLE_INSTANCE` broker drops AMQP connections; Celery retries handle it but ensure `task_acks_late=True` and `task_reject_on_worker_lost=True` in worker config.
- AMQP port `5671` (TLS). Web console on `15671`.

### 2.6 SES (transactional email)
- **Component**: `aws_sesv2_email_identity` for domain + DKIM + SPF + DMARC TXT records via Route 53.
- **Knob**: Production access (out of sandbox) requires AWS support ticket — **request early**, takes 24h. Configuration set with `aws_sesv2_configuration_set` for bounce/complaint SNS topic → `notification-svc`.
- **Failure mode**: Forgetting the DMARC `p=none; rua=mailto:dmarc@<domain>` record → ISPs silently drop. Verify via `mail-tester.com` post-apply.

### 2.7 SNS Mobile Push
- **Component**: `aws_sns_platform_application` × 2 (APNs + FCM). `aws_sns_topic` per env for fan-out; per-device endpoints created at runtime by `notification-svc`.
- **Knob**: APNs uses token-based auth (`.p8` from Apple) — store the private key in Secrets Manager (NOT a Terraform variable). Pass the `secrets_manager_secret_arn` to the platform application via a data source.
- **Failure mode**: Hardcoding the `.p8` in tfvars → key leaks to plan output and tfstate. Use `aws_secretsmanager_secret_version` + `jsondecode` data source.

### 2.8 Secrets Manager
- **Pattern**: One secret per service per env, named `colab/<env>/<service>/env` (JSON blob). Rotation on RDS + MQ master passwords via the AWS-managed rotation Lambda.
- **Knob**: `recovery_window_in_days = 7` in dev (faster cleanup), `30` in prod (audit-safe).
- **Failure mode**: Secrets-store-csi-driver vs External Secrets Operator — pick **External Secrets Operator (ESO)** for cleaner k8s-native sync to `Secret` objects and Helm-chart simplicity. ESO version `0.9.x`.

### 2.9 IRSA (IAM Roles for Service Accounts)
- **Pattern**: One IAM role per microservice, trust policy bound to `system:serviceaccount:colab-<env>:<svc>-sa`. Policy attaches `secretsmanager:GetSecretValue` scoped to the service's secret ARN + service-specific S3 / SNS / SES permissions.
- **Knob**: The trust policy's `Condition.StringEquals` must match the OIDC provider URL **without** the `https://` prefix. Single most common copy-paste bug.
- **Failure mode**: Granting `secretsmanager:GetSecretValue` with `Resource: "*"` — auditors fail you. Always scope to the exact secret ARN.

### 2.10 ACM
- **Component**: `aws_acm_certificate` with `validation_method = "DNS"`, wildcard `*.<domain>` + apex SAN. Auto-validated via Route 53 records emitted by `aws_acm_certificate_validation`.
- **Knob**: For CloudFront distributions, certs MUST live in `us-east-1` regardless of the resource's region. Our primary is us-east-1 so this aligns; but if we ever expand to ap-south-1, the CloudFront cert still stays here.
- **Failure mode**: Issuing a cert and forgetting the DNS validation record → cert stays `PENDING_VALIDATION` indefinitely; downstream ALB/CloudFront blocks.

### 2.11 Route 53
- **Component**: One public hosted zone for `<apex_domain>`. Records created by sub-modules (ACM validation, SES DKIM, ALB aliases for `api.<domain>`, CloudFront alias for `app.<domain>` + `<apex>`).
- **Knob**: Use `external-dns` controller in EKS for service-managed records. Scope its IAM policy to the zone ID, not `*`.
- **Failure mode**: Mixing manual console records with Terraform-managed records → `terraform plan` shows perpetual diff. Document: "all records via Terraform or external-dns; nothing manual".

### 2.12 GitHub OIDC
- **Component**: `aws_iam_openid_connect_provider` with `url = "https://token.actions.githubusercontent.com"`, `thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]` (GitHub's well-known thumbprint).
- **Knob**: Trust policy must restrict `sub` to `repo:colab1571-ctrl/Colab:ref:refs/heads/main` for prod role, broader for dev role (`repo:colab1571-ctrl/Colab:*`).
- **Failure mode**: Wildcarding `sub` to `repo:colab1571-ctrl/Colab:*` for the **prod** deploy role → any feature branch can deploy to prod. Lock to specific refs + environments.

---

## 3. Infrastructure Inventory (per env sizing)

> All resources tagged `Project=colab Env=<env> ManagedBy=terraform`. Sizes are minimums; HPA + RDS storage autoscaling handle ramp.

| Resource | Module | dev | staging | prod |
|---|---|---|---|---|
| VPC CIDR | `vpc` | 10.20.0.0/16 | 10.30.0.0/16 | 10.40.0.0/16 |
| AZs | `vpc` | 2 (a,b) | 3 (a,b,c) | 3 (a,b,c) |
| NAT Gateways | `vpc` | 1 (single-AZ, cost) | 3 (one/AZ) | 3 (one/AZ) |
| EKS control plane | `eks` | 1.30 | 1.30 | 1.30 |
| EKS node group (system) | `eks` | 2× t3.medium | 3× t3.large | 3× m6i.large |
| EKS node group (app) | `eks` | 2× t3.large (on-demand) | 3× m6i.large + spot | 6× m6i.xlarge + spot pool |
| RDS Postgres 16 | `rds` | db.t4g.medium, 50GB gp3, single-AZ | db.m6g.large, 100GB gp3, Multi-AZ | db.m6g.xlarge, 500GB gp3, Multi-AZ, RR×1 |
| RDS backup retention | `rds` | 1d | 7d | 14d |
| ElastiCache Redis | `redis` | 1× cache.t4g.micro (cluster off) | 1 shard × (primary+replica) cache.t4g.small | 2 shards × (primary+replica) cache.m6g.large, cluster mode ON |
| Amazon MQ (RabbitMQ 3.13) | `mq` | mq.t3.micro SINGLE_INSTANCE | mq.m5.large SINGLE_INSTANCE | mq.m5.large CLUSTER_MULTI_AZ (3 nodes) |
| S3 buckets ×5 | `s3` | per-env suffix, versioning ON | same | same + replication to us-west-2 (audit-logs only) |
| CloudFront distributions ×4 | `s3` | OAC + ACM | same | same + WAF |
| SES domain identity | `ses` | dev subdomain | staging subdomain | apex |
| SNS platform apps (APNs/FCM) | `sns-mobile` | sandbox | sandbox | production |
| Secrets Manager entries | `secrets` | ~20 per env | ~20 | ~20 |
| IRSA roles (one per svc) | `iam-irsa` | 19 | 19 | 19 |
| Route 53 hosted zone | `dns` | shared (single zone, sub-records per env) | — | — |
| ACM cert | `acm` | `*.<apex>` + apex (us-east-1) | — | — |
| GitHub OIDC role | `github-oidc` | `colab-github-deploy-dev` | `…-staging` | `…-prod` |

### S3 bucket inventory (each env)
- `colab-portfolio-<env>` — user portfolio uploads (10MB image / 30MB audio / 100MB video). CloudFront fronted (signed URLs).
- `colab-chat-files-<env>` — in-chat attachments. CloudFront fronted (signed URLs, short TTL).
- `colab-audit-logs-<env>` — moderation actions, DSR exports, Recall.ai transcripts. **No CloudFront**, object-lock in compliance mode (prod only) 3-year retention.
- `colab-mockup-assets-<env>` — AI-generated mockups, watermarked. CloudFront fronted, short signed-URL TTL.
- `colab-web-static-<env>` — Next.js static assets, marketing site. CloudFront fronted, public-read via OAC.

---

## 4. Module Boundaries

> Each module has a single responsibility statement. Inputs declared in `variables.tf`; outputs declared in `outputs.tf`. Located at `terraform/modules/<name>/`.

### 4.1 `vpc`
**Responsibility**: Network primitives — VPC, subnets, route tables, NAT, IGW, flow logs.
- **Inputs**: `env`, `cidr`, `azs` (list), `single_nat` (bool, dev=true)
- **Outputs**: `vpc_id`, `public_subnet_ids`, `private_subnet_ids`, `isolated_subnet_ids`, `default_security_group_id`

### 4.2 `eks`
**Responsibility**: EKS cluster, managed node groups, OIDC provider, core addons.
- **Inputs**: `env`, `vpc_id`, `subnet_ids`, `cluster_version` (default "1.30"), `node_groups` (map)
- **Outputs**: `cluster_name`, `cluster_endpoint`, `cluster_ca`, `oidc_provider_arn`, `oidc_provider_url`, `node_role_arn`

### 4.3 `rds`
**Responsibility**: Postgres 16 instance + parameter group + subnet group + security group + master secret. Does NOT create databases or extensions (handled by a k8s post-install job).
- **Inputs**: `env`, `vpc_id`, `subnet_ids`, `instance_class`, `allocated_storage`, `multi_az`, `extensions` (informational only, for documentation), `allowed_sg_ids`
- **Outputs**: `endpoint`, `port`, `master_secret_arn`, `security_group_id`, `db_name`

### 4.4 `redis`
**Responsibility**: ElastiCache replication group, subnet group, security group, parameter group (cluster mode toggle), auth-token secret.
- **Inputs**: `env`, `vpc_id`, `subnet_ids`, `node_type`, `cluster_mode_enabled` (bool), `num_shards`, `replicas_per_shard`, `allowed_sg_ids`
- **Outputs**: `primary_endpoint`, `reader_endpoint`, `configuration_endpoint`, `auth_secret_arn`, `security_group_id`

### 4.5 `s3`
**Responsibility**: The 5 buckets per env + lifecycle rules + CloudFront distributions for the 4 public-facing ones + OAC + bucket policies.
- **Inputs**: `env`, `cloudfront_acm_arn`, `cloudfront_aliases` (map: bucket-key → fqdn)
- **Outputs**: `bucket_arns` (map), `bucket_names` (map), `cloudfront_domain_names` (map), `cloudfront_distribution_ids` (map)

### 4.6 `mq`
**Responsibility**: Amazon MQ broker (RabbitMQ), subnet selection, security group, master-user secret, optional cluster mode.
- **Inputs**: `env`, `vpc_id`, `subnet_ids`, `instance_type`, `deployment_mode`, `allowed_sg_ids`
- **Outputs**: `amqp_endpoint`, `console_url`, `user_secret_arn`, `security_group_id`

### 4.7 `ses`
**Responsibility**: SES v2 domain identity, DKIM, configuration set, bounce/complaint SNS topic, Route 53 records (DKIM, SPF, DMARC).
- **Inputs**: `env`, `domain`, `route53_zone_id`, `dmarc_rua_email`
- **Outputs**: `identity_arn`, `configuration_set_name`, `bounce_topic_arn`, `complaint_topic_arn`

### 4.8 `sns-mobile`
**Responsibility**: SNS platform applications for APNs + FCM, IAM role for `notification-svc` to publish.
- **Inputs**: `env`, `apns_credentials_secret_arn`, `fcm_credentials_secret_arn`, `apns_sandbox` (bool)
- **Outputs**: `apns_platform_app_arn`, `fcm_platform_app_arn`, `publisher_role_arn`

### 4.9 `secrets`
**Responsibility**: Secrets Manager entries — one per service per env, plus shared (RDS master, MQ master, Redis auth, JWT). Defines schema; values populated by post-apply scripts or rotation Lambdas.
- **Inputs**: `env`, `services` (list of service names), `shared_secrets` (map of name → initial JSON or null)
- **Outputs**: `service_secret_arns` (map), `shared_secret_arns` (map)

### 4.10 `iam-irsa`
**Responsibility**: One IAM role per microservice with OIDC trust + scoped policy (Secrets Manager read + service-specific resource access). Outputs role ARN for Helm values injection.
- **Inputs**: `env`, `cluster_name`, `oidc_arn`, `oidc_url`, `service_policies` (map: svc → policy doc/refs to s3 bucket arns / sns arns / etc.)
- **Outputs**: `service_role_arns` (map: svc-name → role-arn)

### 4.11 `dns`
**Responsibility**: Route 53 public hosted zone, baseline records (apex, www CNAME).
- **Inputs**: `apex`
- **Outputs**: `zone_id`, `name_servers`

### 4.12 `acm`
**Responsibility**: Wildcard + apex cert in us-east-1, DNS-validated via Route 53.
- **Inputs**: `apex`, `zone_id`
- **Outputs**: `certificate_arn`, `certificate_domain_validation_options`

### 4.13 `github-oidc`
**Responsibility**: OIDC provider (singleton per account, guarded by data source), deploy roles per env with scoped sub claim.
- **Inputs**: `env`, `github_repo`, `allowed_refs` (list), `deploy_policy_arns` (list)
- **Outputs**: `deploy_role_arn`, `oidc_provider_arn`

---

## 5. Networking

### 5.1 CIDR layout (dev shown; staging/prod analogous)
- VPC: `10.20.0.0/16` (65536 IPs)
- **Public subnets** (NAT, ALBs, NLBs): `10.20.0.0/20`, `10.20.16.0/20`, `10.20.32.0/20` — one per AZ
- **Private subnets** (EKS nodes, ALB targets, EKS pod IPs via VPC CNI): `10.20.64.0/19`, `10.20.96.0/19`, `10.20.128.0/19` — large for pod density
- **Isolated subnets** (RDS, ElastiCache, MQ): `10.20.192.0/22`, `10.20.196.0/22`, `10.20.200.0/22` — no NAT egress

### 5.2 NAT strategy
- **dev**: single NAT Gateway in AZ-a, all private subnets route 0.0.0.0/0 there (saves ~$60/mo; tolerable since dev has no SLA).
- **staging + prod**: one NAT GW per AZ (HA, no cross-AZ NAT charges).

### 5.3 Security groups
- `sg-eks-nodes` — egress all; ingress from cluster SG only.
- `sg-rds` — ingress 5432 from `sg-eks-nodes` only.
- `sg-redis` — ingress 6379 from `sg-eks-nodes` only.
- `sg-mq` — ingress 5671 + 15671 from `sg-eks-nodes` only.
- `sg-alb-public` — ingress 80/443 from `0.0.0.0/0`; targets EKS nodes on node ports.

### 5.4 VPC endpoints (prod only — cost optimization)
- Gateway endpoints: S3, DynamoDB (free)
- Interface endpoints: Secrets Manager, ECR API, ECR DKR, STS, Logs, SNS, SQS (cuts NAT egress for AWS-API traffic)

---

## 6. EKS Specifics

### 6.1 Version
- **Kubernetes**: `1.30` (latest GA at planning time; supported until ~Sep 2025 by AWS — bump before then). Cluster autoscaler / Karpenter chosen later in P1.
- **AMI**: AL2023 EKS-optimized (default for v1.30 node groups).

### 6.2 Addon list (managed via Terraform `aws_eks_addon`)
| Addon | Version (auto-resolved) | IRSA needed | Notes |
|---|---|---|---|
| `vpc-cni` | latest compatible | yes | Pod IPs from VPC; needed for security-group-per-pod later |
| `coredns` | latest compatible | no | Default DNS |
| `kube-proxy` | latest compatible | no | — |
| `aws-ebs-csi-driver` | latest compatible | yes | Required for any PV (RDS uses no PV but cert-manager + observability stacks do) |
| `aws-load-balancer-controller` | Helm chart `1.8.x` | yes | ALB Ingress + NLB Service provisioning |
| `external-dns` | Helm chart `1.14.x` | yes | Route 53 record sync for ingresses |
| `cert-manager` | Helm chart `1.15.x` | no | TLS for internal service-mesh later; ACM-cert primary path for public |
| `external-secrets-operator` | Helm chart `0.9.x` | yes | Syncs Secrets Manager → `Secret` objects per pod |
| `metrics-server` | Helm chart `3.12.x` | no | HPA |

### 6.3 Node group sizing
- See §3 inventory. `system` node group taints `CriticalAddonsOnly=true:NoSchedule` so only addons schedule there. `app` node group untainted.
- Prod adds a `spot` node group with `m6i.large` / `m6i.xlarge` mix for non-stateful Celery workers.

### 6.4 IRSA wiring pattern
Per service:
1. `iam-irsa` module emits role ARN `arn:aws:iam::<acct>:role/colab-<env>-<svc>`.
2. Helm chart `charts/svc/` exposes `serviceAccount.annotations."eks.amazonaws.com/role-arn"` value; values file per service supplies the ARN.
3. Pod's SA annotation triggers AWS pod identity webhook → injects `AWS_ROLE_ARN` + `AWS_WEB_IDENTITY_TOKEN_FILE`.
4. App code uses `boto3.Session()` — picks up the token transparently.
5. ESO `ClusterSecretStore` uses a cluster-wide IRSA role to read Secrets Manager; per-service `ExternalSecret` references `colab/<env>/<svc>/env` and writes a k8s `Secret`. Pod mounts as env vars.

---

## 7. Helm Chart Base (`charts/svc/`)

> Path lives in the **main repo** (not in `terraform/`), at `charts/svc/`. Every microservice's per-service chart (`charts/auth-svc/`, etc.) `dependencies:` on this base chart with `alias: svc`. Per-service charts are just a `values.yaml` override.

### Values exposed
| Key | Type | Purpose |
|---|---|---|
| `image.repository` | string | ECR repo URI |
| `image.tag` | string | Git SHA |
| `image.pullPolicy` | string | `IfNotPresent` (default) |
| `replicas` | int | Default 2 (3 in prod) |
| `resources.requests.cpu/memory` | string | Defaults: 100m / 256Mi |
| `resources.limits.cpu/memory` | string | Defaults: 1000m / 1Gi |
| `serviceAccount.create` | bool | true |
| `serviceAccount.name` | string | `<svc>-sa` |
| `serviceAccount.annotations` | map | IRSA role ARN injected here |
| `env` | map[string]string | Non-secret env vars |
| `envFromSecret` | string | Name of k8s Secret produced by ESO (e.g. `auth-svc-env`) |
| `externalSecret.refreshInterval` | string | `1h` |
| `externalSecret.secretStoreRef` | string | `colab-cluster-store` |
| `externalSecret.remoteRef` | string | `colab/<env>/<svc>/env` |
| `service.port` | int | 8000 (FastAPI default) |
| `service.type` | string | `ClusterIP` |
| `ingress.enabled` | bool | false (gateway-svc only true) |
| `ingress.host` | string | `api.<domain>` |
| `ingress.className` | string | `alb` |
| `ingress.annotations` | map | ACM cert, group name, scheme |
| `hpa.enabled` | bool | true |
| `hpa.minReplicas` | int | 2 |
| `hpa.maxReplicas` | int | 10 |
| `hpa.targetCPUUtilization` | int | 70 |
| `probes.liveness.path` | string | `/healthz` |
| `probes.readiness.path` | string | `/ready` |
| `podDisruptionBudget.minAvailable` | int | 1 |
| `topologySpreadConstraints` | list | Spread across AZs |

### Templates
- `deployment.yaml` — single Deployment, env from `envFromSecret`, IRSA SA annotation
- `service.yaml` — ClusterIP
- `serviceaccount.yaml` — annotated for IRSA
- `externalsecret.yaml` — ESO custom resource referencing Secrets Manager
- `ingress.yaml` — conditional, ALB
- `hpa.yaml` — conditional
- `pdb.yaml` — always
- `_helpers.tpl` — name + labels (Project=colab, app=<svc>, env=<env>)

---

## 8. Secrets Pattern

### 8.1 Naming
- **Service secrets**: `colab/<env>/<service>/env` — JSON map of env-var names → values.
  - Example: `colab/prod/auth-svc/env` = `{"JWT_SECRET":"...","DATABASE_URL":"...","REDIS_URL":"..."}`
- **Shared secrets**: `colab/<env>/shared/<name>` (e.g. `colab/prod/shared/rds-master`, `colab/prod/shared/redis-auth`, `colab/prod/shared/mq-master`).

### 8.2 Mapping from `.env.example` → secret path

| `.env` var | Secret path | Owner service(s) |
|---|---|---|
| `DATABASE_URL`, `DATABASE_REPLICA_URL` | `colab/<env>/shared/rds-url` | all data-plane services |
| `REDIS_URL` | `colab/<env>/shared/redis-url` | all services |
| `RABBITMQ_URL` | `colab/<env>/shared/mq-url` | celery workers, notification-svc, ai-orchestrator-svc |
| `JWT_SECRET` | `colab/<env>/auth-svc/env` | auth-svc, gateway |
| `APPLE_PRIVATE_KEY` + APPLE_* | `colab/<env>/auth-svc/env` | auth-svc, notification-svc (push) |
| `GOOGLE_*` | `colab/<env>/auth-svc/env` + `colab/<env>/meeting-svc/env` | auth-svc, meeting-svc |
| `PERSONA_*` | `colab/<env>/identity-svc/env` | identity-svc |
| `STRIPE_*` | `colab/<env>/billing-svc/env` | billing-svc |
| `REVENUECAT_*` | `colab/<env>/billing-svc/env` | billing-svc |
| `OPENAI_*` | `colab/<env>/ai-orchestrator-svc/env` + `colab/<env>/matching-svc/env` + `colab/<env>/moderation-svc/env` + `colab/<env>/support-svc/env` | multiple |
| `REPLICATE_*` | `colab/<env>/ai-orchestrator-svc/env` | ai-orchestrator-svc |
| `RECALL_*` | `colab/<env>/meeting-svc/env` | meeting-svc |
| `MAPBOX_SECRET_TOKEN` | `colab/<env>/geo-svc/env` | geo-svc |
| `SENTRY_DSN_*` | `colab/<env>/<svc>/env` (per-svc DSN where applicable) | all |
| `POSTHOG_API_KEY_*` | `colab/<env>/analytics-svc/env` | analytics-svc, clients (public key) |
| `META_*`, `SPOTIFY_*`, `YOUTUBE_API_KEY` | `colab/<env>/profile-svc/env` | profile-svc |
| `SNS_APNS_ARN`, `SNS_FCM_ARN` | not-secret → Helm value | notification-svc |
| `CLOUDFRONT_DISTRIBUTION_ID`, bucket names | not-secret → Helm value | media-svc, gateway |

### 8.3 IRSA policy template (per service)
```hcl
data "aws_iam_policy_document" "svc_policy" {
  statement {
    actions = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [
      "arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:colab/${var.env}/${var.service}/*",
      "arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:colab/${var.env}/shared/*"
    ]
  }
  # Plus service-specific blocks: S3, SNS, SES, etc.
}
```

---

## 9. Implementation Task List

> Format: `id | title | outcome (Done evidence) | est_hours | blocks | blocked_by`. Grouped by module/cross-cutting. Aim 1–4h each.

### Group A — Bootstrap (cross-cutting)
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-A-01 | Run `bootstrap.sh` for state bucket + lock table | `aws s3 ls colab-tfstate-<acct>-us-east-1` returns; DynamoDB `colab-tfstate-lock` exists | 1 | all | manual: AWS root + IAM admin |
| T-A-02 | Pin Terraform `backend "s3"` config in `envs/dev/main.tf`, `envs/staging/main.tf`, `envs/prod/main.tf` | `terraform init` succeeds in each env | 1 | all module tasks | T-A-01 |
| T-A-03 | Create `envs/staging/` and `envs/prod/` mirroring `envs/dev/` structure | dirs exist with own `main.tf`, `variables.tf`, `terraform.tfvars` | 1 | staging/prod apply | T-A-02 |
| T-A-04 | Add `pre-commit` config + `tflint` + `terraform fmt` + `terraform validate` to repo root | `pre-commit run --all-files` clean | 2 | clean PRs | — |

### Group B — `vpc` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-B-01 | Implement `vpc` module: VPC, IGW, 3× public + 3× private + 3× isolated subnets | `terraform plan` shows all subnets in `envs/dev` | 3 | eks, rds, redis, mq | T-A-02 |
| T-B-02 | Add NAT GW (single in dev; per-AZ in staging/prod) + route tables | private subnets default-route via NAT | 2 | egress traffic | T-B-01 |
| T-B-03 | Add VPC flow logs to CloudWatch (prod only) | flow log group `vpc-flow-<env>` exists in prod | 1 | audit | T-B-01 |
| T-B-04 | Add VPC interface endpoints (Secrets Manager, ECR, STS, Logs) — prod only | endpoints listed in console; NAT egress drops | 2 | cost | T-B-01 |

### Group C — `eks` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-C-01 | Implement `eks` module using `terraform-aws-modules/eks/aws ~> 20`, cluster v1.30 | `aws eks describe-cluster --name colab-<env>` returns ACTIVE | 4 | all k8s | T-B-01 |
| T-C-02 | Add system + app managed node groups per env sizing | `kubectl get nodes` shows ≥2 in dev, ≥6 in prod | 2 | workloads | T-C-01 |
| T-C-03 | Wire OIDC provider output for IRSA | `aws iam list-open-id-connect-providers` shows EKS issuer | 1 | irsa | T-C-01 |
| T-C-04 | Install core EKS addons via `aws_eks_addon` (vpc-cni, coredns, kube-proxy, ebs-csi) | `kubectl get pods -n kube-system` healthy | 2 | k8s ops | T-C-02 |
| T-C-05 | Install `aws-load-balancer-controller` via Helm (Terraform `helm_release`) | controller deployment Running; test ingress provisions ALB | 3 | ingress | T-C-04, T-J-01 (irsa) |
| T-C-06 | Install `external-dns` via Helm + Route 53 IRSA role | test ingress produces a Route 53 A-record | 2 | ingress | T-C-05, T-K-02 (zone) |
| T-C-07 | Install `cert-manager` via Helm | `kubectl get pods -n cert-manager` healthy | 1 | service certs | T-C-04 |
| T-C-08 | Install `external-secrets-operator` via Helm + cluster role IRSA | `ClusterSecretStore` named `colab-cluster-store` synced | 2 | service secrets | T-C-04, T-J-02 |
| T-C-09 | Install `metrics-server` via Helm | `kubectl top nodes` works | 1 | HPA | T-C-04 |
| T-C-10 | Configure access entries: admin user + GitHub deploy role + developer group | `aws eks list-access-entries` shows all three | 2 | CI deploys | T-C-01, T-M-01 |

### Group D — `rds` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-D-01 | Implement `rds` module: subnet group, parameter group (force_ssl=1), security group, instance Postgres 16.4 | `aws rds describe-db-instances` shows available | 3 | apps needing DB | T-B-01 |
| T-D-02 | Provision master credential in Secrets Manager via `aws_db_instance.manage_master_user_password = true` | secret `rds!cluster-*` exists; readable by IRSA | 1 | apps connect | T-D-01 |
| T-D-03 | Multi-AZ + RR for prod (`apply_immediately = false`, deletion_protection = true) | failover test from console succeeds | 2 | HA | T-D-01 |
| T-D-04 | Write k8s Job manifest in `charts/db-bootstrap/` that runs `CREATE EXTENSION postgis; CREATE EXTENSION vector;` on first deploy | `\dx` in psql shows both extensions | 2 | matching, geo | T-D-01, T-C-08 |
| T-D-05 | Document backup + PITR posture in module README | README exists | 1 | audit | T-D-01 |

### Group E — `redis` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-E-01 | Implement `redis` module: subnet group, parameter group, security group, replication group | `aws elasticache describe-replication-groups` shows available | 3 | session, cache | T-B-01 |
| T-E-02 | Enable transit + at-rest encryption + auth token (random_password → Secrets Manager) | clients must use `rediss://` URI with AUTH | 1 | TLS | T-E-01 |
| T-E-03 | Cluster mode enabled in prod (2 shards × 1 replica) | configuration endpoint exists | 2 | prod scale | T-E-01 |

### Group F — `s3` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-F-01 | Implement 5 buckets per env with versioning, encryption (SSE-S3), public access blocked | `aws s3 ls` shows all 5 | 2 | media, audit | T-A-02 |
| T-F-02 | Bucket lifecycle rules (transition to IA after 90d for chat-files; Glacier for audit-logs after 365d) | rules visible in console | 2 | cost | T-F-01 |
| T-F-03 | Object lock + 3y retention on audit-logs bucket (prod) | `aws s3api get-object-lock-configuration` shows COMPLIANCE | 1 | DSR/legal | T-F-01 |
| T-F-04 | CloudFront distributions for portfolio + chat-files + mockup-assets + web-static, with OAC | distribution domain returns 200 on test object | 4 | client access | T-F-01, T-L-01 (acm) |
| T-F-05 | Cross-region replication of audit-logs bucket to `us-west-2` (prod only) | replication metrics tick | 2 | DR | T-F-01 |

### Group G — `mq` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-G-01 | Implement `mq` broker module (RabbitMQ 3.13, deployment_mode per-env, master in Secrets Manager) | `aws mq describe-broker` shows RUNNING | 3 | Celery, notifications | T-B-01 |
| T-G-02 | Security group restricting 5671/15671 to EKS node SG | `nc -zv <amqp-host> 5671` works from pod, fails from public | 1 | net safety | T-G-01 |

### Group H — `ses` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-H-01 | Implement `ses` module: domain identity, DKIM, Route 53 records, configuration set | `aws sesv2 get-email-identity` returns verified | 2 | transactional email | T-K-02 |
| T-H-02 | Bounce/complaint SNS topic + subscription to notification-svc webhook URL | bounce simulator triggers webhook | 2 | hygiene | T-H-01 |
| T-H-03 | File AWS support ticket to leave SES sandbox (prod) | quota raised to ≥50k/day | 1 | prod email | T-H-01 |

### Group I — `sns-mobile` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-I-01 | Implement `sns-mobile`: APNs + FCM platform applications, pulling credentials from Secrets Manager | platform app ARNs output | 3 | push | manual: Apple .p8 + FCM key in secrets |
| T-I-02 | IAM publisher role for notification-svc | role allows `sns:CreatePlatformEndpoint` + `sns:Publish` | 1 | push | T-I-01, T-J-01 |

### Group J — `iam-irsa` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-J-01 | Implement `iam-irsa` module: helper to mint role per service with OIDC trust | `aws iam list-roles` shows `colab-<env>-<svc>` × 19 | 4 | all svcs | T-C-03 |
| T-J-02 | Cluster-wide ESO role + ClusterSecretStore policy (read all `colab/<env>/*`) | ESO syncs a test secret | 2 | secrets sync | T-J-01 |
| T-J-03 | Per-service policy docs (Secrets read + S3 / SNS / SES as needed) — encoded in module as a `for_each` map | each role has tightly-scoped resource ARNs | 3 | least-privilege | T-J-01 |

### Group K — `dns` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-K-01 | Decide apex domain (NEEDS USER INPUT — see §11) | apex written into `terraform.tfvars` | 0.5 | dns | user |
| T-K-02 | Implement `dns` module: hosted zone + apex A record alias placeholder | `aws route53 list-hosted-zones` shows zone | 1 | acm, ses, ingress | T-K-01 |

### Group L — `acm` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-L-01 | Implement `acm` module: wildcard + apex cert, DNS validation via `dns` module records | `aws acm describe-certificate` shows ISSUED | 2 | CloudFront, ALB | T-K-02 |

### Group M — `github-oidc` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-M-01 | Implement OIDC provider + deploy role per env, scoped sub claim | `aws iam list-open-id-connect-providers` shows GitHub | 2 | CI/CD | T-A-02 |
| T-M-02 | Compose deploy role policy: read tfstate + ECR push + EKS describe + IRSA role passrole + Helm release perms | dry-run `terraform plan` from a CI job succeeds | 3 | CI/CD | T-M-01 |
| T-M-03 | Author baseline GitHub Actions workflow `.github/workflows/terraform.yml` (plan on PR, apply on main to dev only initially) | PR runs plan; merge to main applies to dev | 3 | infra deploys | T-M-02 |

### Group N — `secrets` module
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-N-01 | Implement `secrets` module: per-service secret skeletons + shared (rds, redis, mq) — values placeholders | `aws secretsmanager list-secrets` shows all per env | 2 | apps boot | T-A-02 |
| T-N-02 | Hand-load vendor secrets (OpenAI, Replicate, Stripe, RevenueCat, Persona, etc.) into Secrets Manager via a one-shot script `scripts/seed_vendor_secrets.sh` (reads from local `.env`, writes JSON) | script idempotent; produces `last-written` timestamps | 2 | apps boot | T-N-01 + vendor sign-ups |
| T-N-03 | Enable rotation Lambda for `rds-master` + `mq-master` (managed AWS rotation templates) | `aws secretsmanager describe-secret` shows `RotationEnabled` true | 2 | sec posture | T-N-01, T-D-02, T-G-01 |

### Group O — Helm base chart
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-O-01 | Create `charts/svc/` base chart with templates per §7 | `helm template charts/svc` renders for sample values | 4 | all svc deploys | T-C-08 |
| T-O-02 | Create `charts/_template-service/` (skeleton for `charts/<svc>/`) showing how to consume the base chart | a sample chart `charts/hello-svc/` deploys to dev | 2 | onboarding | T-O-01 |
| T-O-03 | Add `Chart.lock` policy + chart-testing CI check | CI fails on un-bumped chart version | 1 | release hygiene | T-O-01 |

### Group P — Smoke + verification
| id | title | outcome | est_h | blocks | blocked_by |
|---|---|---|---|---|---|
| T-P-01 | Deploy `hello-svc` (FastAPI `/healthz` echo) via Helm to dev with IRSA + ESO + Ingress | curl `https://hello.<apex>/healthz` returns 200; pod reads test secret from Secrets Manager | 3 | proves pipeline | T-J-03, T-N-01, T-O-02 |
| T-P-02 | Run `psql $DATABASE_URL -c "CREATE EXTENSION postgis; CREATE EXTENSION vector;"` from a one-shot k8s Job (db-bootstrap) | `\dx` shows postgis 3.4 + vector 0.7 | 1 | matching/geo | T-D-04 |
| T-P-03 | Run a Celery test task against Amazon MQ from `hello-svc` worker | task completes, broker dashboard shows message processed | 2 | proves MQ | T-G-01, T-P-01 |
| T-P-04 | GitHub Actions workflow: assume OIDC role + `aws sts get-caller-identity` | green check in workflow run | 1 | CI/CD trust | T-M-03 |
| T-P-05 | SES verification: send a test email from a one-shot Job | email arrives + DKIM passes (`mail-tester.com` score ≥9/10) | 1 | email path | T-H-01, T-H-03 |
| T-P-06 | SNS Mobile Push: register a test device endpoint + publish | push lands on test device | 2 | push path | T-I-02, manual: test device |
| T-P-07 | Tag audit: `aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=colab` returns every resource | count matches inventory | 1 | compliance | all infra tasks done |
| T-P-08 | Cost guard: enable AWS Budgets ($50/day dev, $200/day prod) with SNS alert | budget alert fires on test threshold | 1 | financial safety | T-A-01 |

### Total
- **~50 tasks**, ~110 estimated hours of focused work (≈ 2.5–3 engineering weeks for one platform engineer; ≈ 1 week with two and parallelism on independent groups B/F/H/I/J/M/N).

---

## 10. Acceptance Criteria Recap (from feature spec)

| Criterion (feature spec) | Smoke command |
|---|---|
| `terraform/bootstrap.sh` idempotently provisions remote state | `bash terraform/bootstrap.sh` → second run prints "Bucket exists." + "Lock table exists." |
| `terraform -chdir=terraform/envs/dev plan` runs clean (no diff after apply) | `terraform -chdir=terraform/envs/dev apply -auto-approve && terraform -chdir=terraform/envs/dev plan -detailed-exitcode` → exit 0 |
| `kubectl get nodes` returns ≥3 healthy nodes in EKS | `aws eks update-kubeconfig --name colab-dev && kubectl get nodes -o wide \| grep Ready` |
| Postgres extensions installed | `kubectl run --rm -it pg --image=postgres:16 -- psql "$DATABASE_URL" -c '\dx'` shows postgis + vector |
| Secrets Manager populated | `aws secretsmanager list-secrets --query 'SecretList[].Name' --output table \| grep colab/dev` lists all per-service secrets |
| IRSA-bound pod can read its Secret | `kubectl logs deploy/hello-svc \| grep "loaded secret OK"` |
| GitHub Actions OIDC works | The "OIDC smoke" workflow's `aws sts get-caller-identity` step is green |
| All resources tagged | `aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=colab --query 'ResourceTagMappingList[].ResourceARN' --output text \| wc -l` ≥ inventory count |
| Multi-AZ RDS in prod | `aws rds describe-db-instances --db-instance-identifier colab-prod --query 'DBInstances[0].MultiAZ'` → `true` |
| Redis primary + replica in prod | `aws elasticache describe-replication-groups --replication-group-id colab-prod --query 'ReplicationGroups[0].NodeGroups[].NodeGroupMembers[].CurrentRole'` → both `primary` + `replica` present |
| RDS automated backups 7d | `aws rds describe-db-instances ... --query '...BackupRetentionPeriod'` ≥ 7 |
| Terraform state in S3 + DynamoDB lock | `aws s3 ls s3://colab-tfstate-<acct>-us-east-1/envs/dev/` shows `terraform.tfstate`; lock table has zero residual rows after apply |

---

## 11. Open Risks / NEEDS USER INPUT

1. **Apex domain name not yet chosen** (placeholder `example.com` in `.env.example`). Blocks T-K-01 onward (DNS, ACM, SES, ALB ingresses, CloudFront aliases). **Ask user before P0 apply.** Until then, dev can run with a `.dev.internal` private zone but cannot validate ACM cert.
2. **Apple Developer + Google Play accounts not yet created** (manual KYC, days of lead time). Blocks T-I-01 (SNS platform applications need APNs `.p8` + FCM server key in Secrets Manager). Push path untestable until accounts exist.
3. **SES sandbox exit** (T-H-03) requires AWS support ticket; 24–48h SLA. Open early.
4. **India DPDP localization** — master §0 marks this for Phase 5. If a region-replication answer lands as "yes, ap-south-1", we add a second env stack later; no blockers for P0.
5. **Stripe + RevenueCat KYC** must complete before billing-svc gets meaningful secrets. Doesn't block infra but blocks Phase 12 (Payments).
6. **AWS account budget** — recommend setting AWS Budgets to hard-stop at $X (user discretion) before applying prod stack; an unattended `m6i.xlarge` + `db.m6g.xlarge` + Multi-AZ accumulates ~$700–900/mo even idle.
7. **DMCA agent registration** (master §0) — explicitly deferred. Tracked for legal, not infra-blocking.
8. **GitHub branch protection on `main`** (per INFRA.md §3) — must be set in the GitHub UI; Terraform doesn't manage GitHub repo settings in this scope.

---

> **Ready for Phase 7 RALPH execution on P0.** Once T-K-01 (apex domain) and the vendor account sign-ups (Apple, Google Play, AWS support ticket for SES) are unblocked, the task graph above can be fanned out across independent groups: B/F/H/M/N start in parallel after T-A-02; C depends on B; D, E, G all depend only on B; J depends on C; O depends on C+J+N; P (smoke) is the final fan-in.
