terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

# ── Per-Service Secrets ───────────────────────────────────────────────────────
# Pattern: colab/<env>/<svc>/env — JSON blob of env-var name → value.
# Initial value is an empty JSON object {}. Actual values are written by:
#   1. scripts/seed_vendor_secrets.sh (vendor API keys)
#   2. Application startup rotation Lambdas (RDS/MQ passwords)
#   3. ESO ExternalSecret controller (reads and injects to pods)

resource "aws_secretsmanager_secret" "service" {
  for_each = toset(var.services)

  name                    = "colab/${var.env}/${each.value}/env"
  description             = "Application environment vars for ${each.value} in colab-${var.env}"
  recovery_window_in_days = var.recovery_window_in_days

  tags = { Name = "colab-${var.env}-${each.value}-env" }
}

resource "aws_secretsmanager_secret_version" "service" {
  for_each = toset(var.services)

  secret_id     = aws_secretsmanager_secret.service[each.value].id
  secret_string = "{}"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ── Shared Secrets ─────────────────────────────────────────────────────────────
# Pattern: colab/<env>/shared/<name>
# Shared secrets include: apns, fcm, jwt, rds-url, redis-url, mq-url.
# The rds-master and mq-master secrets are created by the rds + mq modules respectively.

resource "aws_secretsmanager_secret" "shared" {
  for_each = var.shared_secrets

  name                    = "colab/${var.env}/shared/${each.key}"
  description             = "Shared secret '${each.key}' for colab-${var.env}"
  recovery_window_in_days = var.recovery_window_in_days

  tags = { Name = "colab-${var.env}-shared-${each.key}" }
}

resource "aws_secretsmanager_secret_version" "shared" {
  for_each = var.shared_secrets

  secret_id     = aws_secretsmanager_secret.shared[each.key].id
  secret_string = each.value != null ? jsonencode(each.value) : "{}"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ── NOTE: T-N-03 — Rotation Lambda hookups ───────────────────────────────────
# Rotation for colab/<env>/shared/rds-master is managed in the rds module via
# aws_db_instance.manage_master_user_password (AWS-native rotation).
# Rotation for colab/<env>/shared/mq-master is out of scope for this milestone
# (AWS MQ does not provide a native managed rotation Lambda; custom Lambda would
# be required). Document this gap in the runbook; manual rotation via the
# seed_vendor_secrets.sh script is acceptable until Phase 2.
