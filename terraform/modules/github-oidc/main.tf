terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── OIDC Provider (singleton per account) ────────────────────────────────────
# Guard with a data source lookup; if the provider already exists, import it.
# Terraform will error if you try to create a duplicate — use `terraform import`
# aws_iam_openid_connect_provider.github <arn> on first apply if already present.

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]

  # GitHub's well-known thumbprint (ref: §2.12)
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = { Name = "github-actions-oidc" }
}

# ── Trust Policy ──────────────────────────────────────────────────────────────
locals {
  # Build sub claim values: repo:<org/repo>:ref:<ref> for each allowed ref
  # Dev gets a wildcard; staging/prod are locked to specific refs.
  sub_claims = [
    for ref in var.allowed_refs : "repo:${var.github_repo}:ref:${ref}"
  ]
}

data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.sub_claims
    }
  }
}

# ── Deploy Role ───────────────────────────────────────────────────────────────
resource "aws_iam_role" "deploy" {
  name               = "colab-github-deploy-${var.env}"
  description        = "GitHub Actions OIDC deploy role for colab-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.trust.json

  max_session_duration = 3600
}

# ── Dev: AdministratorAccess (pragmatic for bootstrap) ───────────────────────
# TRADEOFF: Granting AdministratorAccess for the dev deploy role is intentional
# for the bootstrap phase. It avoids policy-gap iteration when setting up
# greenfield infrastructure across 15+ AWS service domains. This role can only
# be assumed by a GitHub Actions runner from the specified branch/ref, and the
# assume-role event is logged in CloudTrail.
# BEFORE PRODUCTION USE: Replace with the tighter inline policy below or a
# customer-managed policy scoped to only the resources this repo manages.
# Tracked as a security finding in the project backlog.

resource "aws_iam_role_policy_attachment" "admin" {
  count = var.env == "dev" ? 1 : 0

  role       = aws_iam_role.deploy.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# ── Staging/Prod: Tighter inline policy ──────────────────────────────────────
data "aws_iam_policy_document" "deploy_policy" {
  # Terraform state access
  statement {
    sid    = "TerraformState"
    effect = "Allow"
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
      "s3:ListBucket", "s3:GetBucketVersioning"
    ]
    resources = [
      "arn:aws:s3:::colab-tfstate-*",
      "arn:aws:s3:::colab-tfstate-*/*"
    ]
  }

  statement {
    sid    = "TerraformLock"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem", "dynamodb:PutItem",
      "dynamodb:DeleteItem", "dynamodb:DescribeTable"
    ]
    resources = [
      "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/colab-tfstate-lock"
    ]
  }

  # EC2 / VPC describe + manage
  statement {
    sid    = "VPCManage"
    effect = "Allow"
    actions = [
      "ec2:Describe*", "ec2:Create*", "ec2:Delete*",
      "ec2:Attach*", "ec2:Detach*", "ec2:Modify*",
      "ec2:Associate*", "ec2:Disassociate*",
      "ec2:Allocate*", "ec2:Release*",
      "ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress",
      "ec2:AuthorizeSecurityGroupEgress", "ec2:RevokeSecurityGroupEgress"
    ]
    resources = ["*"]
  }

  # EKS
  statement {
    sid    = "EKSManage"
    effect = "Allow"
    actions = [
      "eks:Describe*", "eks:List*",
      "eks:CreateCluster", "eks:DeleteCluster", "eks:UpdateClusterConfig",
      "eks:UpdateClusterVersion", "eks:CreateNodegroup", "eks:DeleteNodegroup",
      "eks:UpdateNodegroupConfig", "eks:CreateAddon", "eks:DeleteAddon",
      "eks:UpdateAddon", "eks:TagResource", "eks:UntagResource",
      "eks:CreateAccessEntry", "eks:DeleteAccessEntry", "eks:AssociateAccessPolicy"
    ]
    resources = ["*"]
  }

  # RDS
  statement {
    sid    = "RDSManage"
    effect = "Allow"
    actions = [
      "rds:Describe*", "rds:List*",
      "rds:Create*", "rds:Delete*", "rds:Modify*",
      "rds:Add*", "rds:Remove*", "rds:Restore*"
    ]
    resources = ["*"]
  }

  # ElastiCache
  statement {
    sid    = "ElastiCacheManage"
    effect = "Allow"
    actions = [
      "elasticache:Describe*", "elasticache:List*",
      "elasticache:Create*", "elasticache:Delete*", "elasticache:Modify*",
      "elasticache:Add*", "elasticache:Remove*"
    ]
    resources = ["*"]
  }

  # Amazon MQ
  statement {
    sid    = "MQManage"
    effect = "Allow"
    actions = [
      "mq:Describe*", "mq:List*",
      "mq:CreateBroker", "mq:DeleteBroker", "mq:UpdateBroker",
      "mq:CreateConfiguration", "mq:UpdateConfiguration",
      "mq:CreateUser", "mq:DeleteUser", "mq:UpdateUser"
    ]
    resources = ["*"]
  }

  # S3 + CloudFront
  statement {
    sid    = "S3CloudFront"
    effect = "Allow"
    actions = [
      "s3:*",
      "cloudfront:Describe*", "cloudfront:Get*", "cloudfront:List*",
      "cloudfront:Create*", "cloudfront:Delete*", "cloudfront:Update*",
      "cloudfront:TagResource", "cloudfront:UntagResource"
    ]
    resources = ["*"]
  }

  # SES
  statement {
    sid    = "SESManage"
    effect = "Allow"
    actions = [
      "ses:*", "sesv2:*"
    ]
    resources = ["*"]
  }

  # SNS
  statement {
    sid    = "SNSManage"
    effect = "Allow"
    actions = [
      "sns:*"
    ]
    resources = ["*"]
  }

  # Secrets Manager
  statement {
    sid    = "SecretsManage"
    effect = "Allow"
    actions = [
      "secretsmanager:Describe*", "secretsmanager:List*",
      "secretsmanager:Create*", "secretsmanager:Delete*",
      "secretsmanager:Update*", "secretsmanager:Put*",
      "secretsmanager:Restore*", "secretsmanager:Tag*",
      "secretsmanager:GetSecretValue", "secretsmanager:GetResourcePolicy",
      "secretsmanager:PutResourcePolicy", "secretsmanager:ValidateResourcePolicy"
    ]
    resources = [
      "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:colab/*"
    ]
  }

  # IAM (scoped to colab- prefixed resources)
  statement {
    sid    = "IAMManage"
    effect = "Allow"
    actions = [
      "iam:Get*", "iam:List*",
      "iam:Create*", "iam:Delete*", "iam:Update*",
      "iam:Put*", "iam:Attach*", "iam:Detach*",
      "iam:Add*", "iam:Remove*", "iam:Tag*", "iam:Untag*",
      "iam:PassRole"
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/colab-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/colab-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:instance-profile/colab-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/*"
    ]
  }

  # Route 53
  statement {
    sid    = "Route53Manage"
    effect = "Allow"
    actions = [
      "route53:Get*", "route53:List*",
      "route53:Create*", "route53:Delete*", "route53:Update*",
      "route53:Change*", "route53:Associate*", "route53:Disassociate*"
    ]
    resources = ["*"]
  }

  # ACM
  statement {
    sid    = "ACMManage"
    effect = "Allow"
    actions = [
      "acm:Describe*", "acm:List*", "acm:Get*",
      "acm:Request*", "acm:Delete*", "acm:Add*",
      "acm:Remove*", "acm:Export*"
    ]
    resources = ["*"]
  }

  # WAFv2
  statement {
    sid    = "WAFManage"
    effect = "Allow"
    actions = [
      "wafv2:Get*", "wafv2:List*", "wafv2:Describe*",
      "wafv2:Create*", "wafv2:Delete*", "wafv2:Update*",
      "wafv2:Associate*", "wafv2:Disassociate*",
      "wafv2:Put*", "wafv2:Tag*", "wafv2:Untag*"
    ]
    resources = ["*"]
  }

  # CloudWatch logs + budgets
  statement {
    sid    = "ObsManage"
    effect = "Allow"
    actions = [
      "logs:*",
      "cloudwatch:*",
      "budgets:*"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  count = var.env != "dev" ? 1 : 0

  name   = "colab-${var.env}-deploy-policy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_policy.json
}

# Additional managed policies (caller-provided)
resource "aws_iam_role_policy_attachment" "extra" {
  for_each = toset(var.deploy_policy_arns)

  role       = aws_iam_role.deploy.name
  policy_arn = each.value
}

# ECR push (all envs — needed for CI image builds)
resource "aws_iam_role_policy_attachment" "ecr_push" {
  role       = aws_iam_role.deploy.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}
