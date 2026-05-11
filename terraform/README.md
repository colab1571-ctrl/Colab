# Terraform — Colab AWS Infrastructure

Provisioned: VPC, EKS, RDS Postgres (with PostGIS + pgvector), ElastiCache Redis, S3 buckets, Amazon MQ for RabbitMQ, SES, SNS Mobile Push, Secrets Manager, IAM roles for IRSA, Route 53, ACM.

## Layout

```
terraform/
├── bootstrap.sh          # One-time: creates remote state bucket + DynamoDB lock
├── envs/
│   ├── dev/
│   ├── staging/
│   └── prod/
└── modules/
    ├── vpc/              # VPC + subnets + NAT + route tables
    ├── eks/              # EKS cluster + node group + add-ons
    ├── rds/              # RDS Postgres + PostGIS + pgvector extensions
    ├── redis/            # ElastiCache Redis cluster mode
    ├── s3/               # All S3 buckets with policies + CORS + versioning
    ├── mq/               # Amazon MQ for RabbitMQ
    ├── ses/              # SES verified domain + DKIM + SPF + DMARC
    ├── sns-mobile/       # APNs + FCM platform applications
    ├── secrets/          # Secrets Manager + Parameter Store entries
    ├── iam-irsa/         # IRSA role for each microservice
    ├── dns/              # Route 53 hosted zones + records
    ├── acm/              # ACM cert wildcard + apex
    └── github-oidc/      # GitHub Actions OIDC trust + deploy role
```

## Prerequisites

- AWS CLI v2 configured with admin credentials (`aws configure --profile colab-admin`)
- Terraform >= 1.7
- An S3 bucket name globally unique for remote state (the bootstrap script generates one)

## First-time bootstrap

```bash
cd terraform
./bootstrap.sh             # creates state bucket + lock table
cd envs/dev
terraform init
terraform plan
terraform apply
```

## Adding a new environment

Copy `envs/dev/` to `envs/<env>/`, edit `terraform.tfvars`, re-run `terraform init && apply`.

## Module surface (high level — generated in Phase 3b artifacts; full bodies follow during Phase 7 P0)

The Phase 3b checkpoint ships **module scaffolds and an env stub** so that Phase 7 P0 (Infrastructure Bootstrap) is a pure "fill in the resources" task. The skeleton is sufficient to plan + apply an empty graph immediately for state-bucket validation.
