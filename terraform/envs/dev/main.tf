terraform {
  required_version = ">= 1.7"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.40" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
    helm   = { source = "hashicorp/helm", version = "~> 2.13" }
  }
  # backend "s3" block filled in by bootstrap.sh output
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = "colab"
      Env       = var.env
      ManagedBy = "terraform"
    }
  }
}

module "vpc" {
  source     = "../../modules/vpc"
  env        = var.env
  cidr       = "10.20.0.0/16"
  azs        = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  single_nat = true
}

module "eks" {
  source     = "../../modules/eks"
  env        = var.env
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
  node_groups = {
    system = {
      instance_types = ["t3.medium"]
      desired_size   = 2
      min_size       = 2
      max_size       = 4
      taints         = [{ key = "CriticalAddonsOnly", value = "true", effect = "NO_SCHEDULE" }]
    }
    app = {
      instance_types = ["t3.large"]
      desired_size   = 2
      min_size       = 1
      max_size       = 6
    }
  }
}

module "rds" {
  source            = "../../modules/rds"
  env               = var.env
  vpc_id            = module.vpc.vpc_id
  subnet_ids        = module.vpc.isolated_subnet_ids
  extensions        = ["postgis", "vector"]
  allowed_sg_ids    = [module.eks.node_security_group_id]
}

module "redis" {
  source               = "../../modules/redis"
  env                  = var.env
  vpc_id               = module.vpc.vpc_id
  subnet_ids           = module.vpc.isolated_subnet_ids
  cluster_mode_enabled = false
  num_shards           = 1
  replicas_per_shard   = 0
  allowed_sg_ids       = [module.eks.node_security_group_id]
}

module "s3" {
  source = "../../modules/s3"
  env    = var.env
}

module "mq" {
  source          = "../../modules/mq"
  env             = var.env
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.isolated_subnet_ids
  instance_type   = "mq.t3.micro"
  deployment_mode = "SINGLE_INSTANCE"
  allowed_sg_ids  = [module.eks.node_security_group_id]
}

module "ses" {
  source          = "../../modules/ses"
  env             = var.env
  domain          = var.email_domain
  route53_zone_id = module.dns.zone_id
  dmarc_rua_email = "dmarc@${var.email_domain}"
}

module "sns_mobile" {
  source                      = "../../modules/sns-mobile"
  env                         = var.env
  apns_credentials_secret_arn = module.secrets.shared_secret_arns["apns"]
  fcm_credentials_secret_arn  = module.secrets.shared_secret_arns["fcm"]
  apns_sandbox                = true
}

module "secrets" {
  source   = "../../modules/secrets"
  env      = var.env
  services = local.services
  shared_secrets = {
    apns = null
    fcm  = null
    jwt  = null
  }
}

module "iam_irsa" {
  source         = "../../modules/iam-irsa"
  env            = var.env
  cluster_name   = module.eks.cluster_name
  oidc_arn       = module.eks.oidc_provider_arn
  oidc_url       = module.eks.oidc_provider_url
  services       = local.services
  s3_bucket_arns = module.s3.bucket_arns
}

module "dns" {
  source = "../../modules/dns"
  env    = var.env
  apex   = var.apex_domain
}

module "acm" {
  source  = "../../modules/acm"
  env     = var.env
  apex    = var.apex_domain
  zone_id = module.dns.zone_id
}

module "github_oidc" {
  source      = "../../modules/github-oidc"
  env         = var.env
  github_repo = "colab1571-ctrl/Colab"
  # Dev: allow any ref so feature branches can plan/apply
  allowed_refs = ["refs/heads/*"]
}

module "budgets" {
  source          = "../../modules/budgets"
  env             = var.env
  daily_limit_usd = 50
  alert_email     = var.budget_alert_email
}

locals {
  services = [
    "gateway", "auth-svc", "profile-svc", "identity-svc", "discovery-svc",
    "matching-svc", "invite-svc", "collab-svc", "chat-svc", "media-svc",
    "ai-orchestrator-svc", "moderation-svc", "notification-svc",
    "billing-svc", "support-svc", "analytics-svc", "admin-svc",
    "geo-svc", "meeting-svc"
  ]
}
