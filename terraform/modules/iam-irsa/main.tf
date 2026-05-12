terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  # OIDC URL without https:// — single most common IRSA bug (§2.9)
  oidc_url_bare = replace(var.oidc_url, "https://", "")

  # Namespace where pods run
  k8s_namespace = "colab-${var.env}"

  # Per-service additional S3/SNS permissions
  # Services not listed get only Secrets Manager access.
  service_extra_policies = {
    "media-svc" = {
      s3_write = ["portfolio", "chat_files", "mockup_assets"]
      s3_read  = []
      sns      = false
    }
    "ai-orchestrator-svc" = {
      s3_write = ["mockup_assets"]
      s3_read  = []
      sns      = false
    }
    "collab-svc" = {
      s3_write = ["chat_files", "audit_logs"]
      s3_read  = []
      sns      = false
    }
    "analytics-svc" = {
      s3_write = []
      s3_read  = ["audit_logs"]
      sns      = false
    }
    "admin-svc" = {
      s3_write = []
      s3_read  = ["portfolio", "chat_files", "audit_logs", "mockup_assets", "web_static"]
      sns      = false
    }
    "notification-svc" = {
      s3_write = []
      s3_read  = []
      sns      = true
    }
  }
}

# ── OIDC Trust Policy per service ─────────────────────────────────────────────
data "aws_iam_policy_document" "trust" {
  for_each = toset(var.services)

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url_bare}:sub"
      values   = ["system:serviceaccount:${local.k8s_namespace}:${each.value}-sa"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url_bare}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

# ── IAM Roles ─────────────────────────────────────────────────────────────────
resource "aws_iam_role" "service" {
  for_each = toset(var.services)

  name               = "colab-${var.env}-${each.value}"
  description        = "IRSA role for ${each.value} in colab-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.trust[each.value].json
}

# ── Base Policy: Secrets Manager read for own + shared secrets ────────────────
resource "aws_iam_role_policy" "secrets_read" {
  for_each = toset(var.services)

  name = "secrets-read"
  role = aws_iam_role.service[each.value].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "SecretsManagerRead"
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = [
        "arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:colab/${var.env}/${each.value}/*",
        "arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:colab/${var.env}/shared/*"
      ]
    }]
  })
}

# ── S3 Write Policy (per service) ─────────────────────────────────────────────
resource "aws_iam_role_policy" "s3_write" {
  for_each = {
    for svc, cfg in local.service_extra_policies :
    svc => cfg
    if contains(var.services, svc) && length(cfg.s3_write) > 0 && length(var.s3_bucket_arns) > 0
  }

  name = "s3-write"
  role = aws_iam_role.service[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "S3Write"
      Effect = "Allow"
      Action = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ]
      Resource = flatten([
        for bucket_key in each.value.s3_write : [
          lookup(var.s3_bucket_arns, bucket_key, "arn:aws:s3:::placeholder"),
          "${lookup(var.s3_bucket_arns, bucket_key, "arn:aws:s3:::placeholder")}/*"
        ]
      ])
    }]
  })
}

# ── S3 Read Policy (per service) ──────────────────────────────────────────────
resource "aws_iam_role_policy" "s3_read" {
  for_each = {
    for svc, cfg in local.service_extra_policies :
    svc => cfg
    if contains(var.services, svc) && length(cfg.s3_read) > 0 && length(var.s3_bucket_arns) > 0
  }

  name = "s3-read"
  role = aws_iam_role.service[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "S3Read"
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:ListBucket"
      ]
      Resource = flatten([
        for bucket_key in each.value.s3_read : [
          lookup(var.s3_bucket_arns, bucket_key, "arn:aws:s3:::placeholder"),
          "${lookup(var.s3_bucket_arns, bucket_key, "arn:aws:s3:::placeholder")}/*"
        ]
      ])
    }]
  })
}

# ── SNS Publish Policy (notification-svc) ─────────────────────────────────────
resource "aws_iam_role_policy" "sns_publish" {
  for_each = {
    for svc, cfg in local.service_extra_policies :
    svc => cfg
    if contains(var.services, svc) && cfg.sns
  }

  name = "sns-mobile-publish"
  role = aws_iam_role.service[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SNSMobilePush"
        Effect = "Allow"
        Action = [
          "sns:CreatePlatformEndpoint",
          "sns:DeleteEndpoint",
          "sns:GetEndpointAttributes",
          "sns:SetEndpointAttributes",
          "sns:Publish",
          "sns:ListEndpointsByPlatformApplication"
        ]
        Resource = length(var.sns_platform_app_arns) > 0 ? concat(
          var.sns_platform_app_arns,
          [
            "arn:aws:sns:${local.region}:${local.account_id}:endpoint/APNS*",
            "arn:aws:sns:${local.region}:${local.account_id}:endpoint/GCM*",
          ]
        ) : ["arn:aws:sns:${local.region}:${local.account_id}:*"]
      }
    ]
  })
}
