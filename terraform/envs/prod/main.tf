terraform {
  required_version = ">= 1.7"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.40" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
    helm   = { source = "hashicorp/helm", version = "~> 2.13" }
  }
  # backend "s3" block — fill in after bootstrap.sh:
  # backend "s3" {
  #   bucket         = "colab-tfstate-<acct>-us-east-1"
  #   key            = "envs/prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "colab-tfstate-lock"
  #   encrypt        = true
  # }
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
  cidr       = "10.40.0.0/16"
  azs        = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  single_nat = false
  enable_flow_logs = true
  enable_vpc_endpoints = true
}

module "eks" {
  source       = "../../modules/eks"
  env          = var.env
  vpc_id       = module.vpc.vpc_id
  subnet_ids   = module.vpc.private_subnet_ids
  cluster_version = "1.30"
  node_groups = {
    system = {
      instance_types = ["m6i.large"]
      desired_size   = 3
      min_size       = 3
      max_size       = 6
      taints         = [{ key = "CriticalAddonsOnly", value = "true", effect = "NO_SCHEDULE" }]
    }
    app = {
      instance_types = ["m6i.xlarge"]
      desired_size   = 6
      min_size       = 3
      max_size       = 30
    }
    spot = {
      instance_types = ["m6i.large", "m6i.xlarge", "m6a.large", "m6a.xlarge"]
      capacity_type  = "SPOT"
      desired_size   = 2
      min_size       = 0
      max_size       = 20
    }
  }
}

module "rds" {
  source                  = "../../modules/rds"
  env                     = var.env
  vpc_id                  = module.vpc.vpc_id
  subnet_ids              = module.vpc.isolated_subnet_ids
  instance_class          = "db.m6g.xlarge"
  allocated_storage       = 500
  multi_az                = true
  deletion_protection     = true
  backup_retention_period = 14
  read_replica_count      = 1
  allowed_sg_ids          = [module.eks.node_security_group_id]
}

module "redis" {
  source                = "../../modules/redis"
  env                   = var.env
  vpc_id                = module.vpc.vpc_id
  subnet_ids            = module.vpc.isolated_subnet_ids
  node_type             = "cache.m6g.large"
  cluster_mode_enabled  = true
  num_shards            = 2
  replicas_per_shard    = 1
  allowed_sg_ids        = [module.eks.node_security_group_id]
}

module "s3" {
  source              = "../../modules/s3"
  env                 = var.env
  cloudfront_acm_arn  = module.acm.certificate_arn
  cloudfront_aliases  = {
    portfolio     = "media.${var.apex_domain}"
    chat_files    = "files.${var.apex_domain}"
    mockup_assets = "mockups.${var.apex_domain}"
    web_static    = var.apex_domain
  }
  enable_replication  = true
  audit_object_lock   = true
  enable_waf          = true
}

module "mq" {
  source            = "../../modules/mq"
  env               = var.env
  vpc_id            = module.vpc.vpc_id
  subnet_ids        = module.vpc.isolated_subnet_ids
  instance_type     = "mq.m5.large"
  deployment_mode   = "CLUSTER_MULTI_AZ"
  allowed_sg_ids    = [module.eks.node_security_group_id]
}

module "ses" {
  source           = "../../modules/ses"
  env              = var.env
  domain           = var.email_domain
  route53_zone_id  = module.dns.zone_id
  dmarc_rua_email  = "dmarc@${var.email_domain}"
}

module "sns_mobile" {
  source                       = "../../modules/sns-mobile"
  env                          = var.env
  apns_credentials_secret_arn  = module.secrets.shared_secret_arns["apns"]
  fcm_credentials_secret_arn   = module.secrets.shared_secret_arns["fcm"]
  apns_sandbox                 = false
}

module "secrets" {
  source   = "../../modules/secrets"
  env      = var.env
  services = local.services
  shared_secrets = {
    apns        = null
    fcm         = null
    jwt         = null
  }
  recovery_window_in_days = 30
}

module "iam_irsa" {
  source       = "../../modules/iam-irsa"
  env          = var.env
  cluster_name = module.eks.cluster_name
  oidc_arn     = module.eks.oidc_provider_arn
  oidc_url     = module.eks.oidc_provider_url
  services     = local.services
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
  source       = "../../modules/github-oidc"
  env          = var.env
  github_repo  = "colab1571-ctrl/Colab"
  allowed_refs = ["refs/heads/main"]
}

module "budgets" {
  source          = "../../modules/budgets"
  env             = var.env
  daily_limit_usd = 200
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
