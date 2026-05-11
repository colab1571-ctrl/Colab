terraform {
  required_version = ">= 1.7"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.40" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
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

# Scaffolds — each module gets a focused body in Phase 7 P0.
module "vpc" {
  source = "../../modules/vpc"
  env    = var.env
  cidr   = "10.20.0.0/16"
  azs    = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
}

module "eks" {
  source = "../../modules/eks"
  env    = var.env
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
}

module "rds" {
  source = "../../modules/rds"
  env    = var.env
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
  extensions = ["postgis", "vector"]   # pgvector + PostGIS
}

module "redis" {
  source = "../../modules/redis"
  env    = var.env
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
}

module "s3" {
  source = "../../modules/s3"
  env    = var.env
}

module "mq" {
  source = "../../modules/mq"
  env    = var.env
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
}

module "ses" {
  source = "../../modules/ses"
  env    = var.env
  domain = var.email_domain
}

module "sns_mobile" {
  source = "../../modules/sns-mobile"
  env    = var.env
}

module "secrets" {
  source = "../../modules/secrets"
  env    = var.env
}

module "iam_irsa" {
  source       = "../../modules/iam-irsa"
  env          = var.env
  cluster_name = module.eks.cluster_name
  oidc_arn     = module.eks.oidc_provider_arn
  oidc_url     = module.eks.oidc_provider_url
}

module "dns" {
  source = "../../modules/dns"
  env    = var.env
  apex   = var.apex_domain
}

module "acm" {
  source = "../../modules/acm"
  env    = var.env
  apex   = var.apex_domain
  zone_id = module.dns.zone_id
}

module "github_oidc" {
  source = "../../modules/github-oidc"
  env    = var.env
  github_repo = "colab1571-ctrl/Colab"
}
