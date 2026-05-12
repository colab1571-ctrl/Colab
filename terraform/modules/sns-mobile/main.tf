terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── Read APNs credentials from Secrets Manager (token-based auth) ─────────────
# The .p8 private key, key_id, and team_id must be stored manually in Secrets
# Manager at the ARN provided in var.apns_credentials_secret_arn BEFORE apply.
# T-I-01 (manual step): Upload Apple .p8 + FCM key via scripts/seed_vendor_secrets.sh.

data "aws_secretsmanager_secret_version" "apns" {
  count     = var.apns_credentials_secret_arn != "" ? 1 : 0
  secret_id = var.apns_credentials_secret_arn
}

data "aws_secretsmanager_secret_version" "fcm" {
  count     = var.fcm_credentials_secret_arn != "" ? 1 : 0
  secret_id = var.fcm_credentials_secret_arn
}

locals {
  apns_creds = var.apns_credentials_secret_arn != "" ? jsondecode(data.aws_secretsmanager_secret_version.apns[0].secret_string) : {}
  fcm_creds  = var.fcm_credentials_secret_arn != "" ? jsondecode(data.aws_secretsmanager_secret_version.fcm[0].secret_string) : {}
}

# ── APNs Platform Application ─────────────────────────────────────────────────
resource "aws_sns_platform_application" "apns" {
  count = var.apns_credentials_secret_arn != "" ? 1 : 0

  name     = "colab-${var.env}-apns"
  platform = var.apns_sandbox ? "APNS_SANDBOX" : "APNS"

  # Token-based auth attributes
  platform_credential = lookup(local.apns_creds, "private_key", "")
  platform_principal  = lookup(local.apns_creds, "team_id", "")

  # Apple key metadata passed as additional attributes
  apple_platform_team_id        = lookup(local.apns_creds, "team_id", "")
  apple_platform_bundle_id      = lookup(local.apns_creds, "bundle_id", "com.colabtest.colab")

  failure_feedback_role_arn = aws_iam_role.sns_feedback.arn
  success_feedback_role_arn = aws_iam_role.sns_feedback.arn
  success_feedback_sample_rate = "5"
}

# ── FCM Platform Application ──────────────────────────────────────────────────
resource "aws_sns_platform_application" "fcm" {
  count = var.fcm_credentials_secret_arn != "" ? 1 : 0

  name     = "colab-${var.env}-fcm"
  platform = "GCM"

  platform_credential = lookup(local.fcm_creds, "server_key", "")

  failure_feedback_role_arn = aws_iam_role.sns_feedback.arn
  success_feedback_role_arn = aws_iam_role.sns_feedback.arn
  success_feedback_sample_rate = "5"
}

# ── SNS Feedback Role (CloudWatch logging) ────────────────────────────────────
resource "aws_iam_role" "sns_feedback" {
  name = "colab-${var.env}-sns-mobile-feedback"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "sns.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "sns_feedback" {
  role       = aws_iam_role.sns_feedback.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonSNSRole"
}

# ── IAM Publisher Role for notification-svc ───────────────────────────────────
resource "aws_iam_role" "publisher" {
  name = "colab-${var.env}-notification-svc-sns-publisher"
  description = "IAM role for notification-svc to publish SNS mobile push messages"

  # This role is assumed via IRSA — the iam-irsa module creates the pod-level role.
  # This role carries the SNS resource-level permissions for platform applications.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect  = "Allow"
      Action  = "sts:AssumeRole"
      Principal = {
        AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
      }
    }]
  })
}

resource "aws_iam_role_policy" "publisher" {
  role = aws_iam_role.publisher.id
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
        Resource = compact([
          var.apns_credentials_secret_arn != "" ? aws_sns_platform_application.apns[0].arn : null,
          var.fcm_credentials_secret_arn != "" ? aws_sns_platform_application.fcm[0].arn : null,
          "arn:aws:sns:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:endpoint/APNS*",
          "arn:aws:sns:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:endpoint/GCM*",
        ])
      }
    ]
  })
}
