terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

locals {
  # Notification targets — at least one of email or SNS must be set
  email_notifications = var.alert_email != "" ? [{
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }, {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }] : []

  sns_notifications = var.alert_sns_topic_arn != "" ? [{
    comparison_operator     = "GREATER_THAN"
    threshold               = 80
    threshold_type          = "PERCENTAGE"
    notification_type       = "ACTUAL"
    subscriber_sns_topic_arns = [var.alert_sns_topic_arn]
  }, {
    comparison_operator     = "GREATER_THAN"
    threshold               = 100
    threshold_type          = "PERCENTAGE"
    notification_type       = "ACTUAL"
    subscriber_sns_topic_arns = [var.alert_sns_topic_arn]
  }] : []
}

# ── Daily Cost Budget ─────────────────────────────────────────────────────────
resource "aws_budgets_budget" "daily" {
  name              = "colab-${var.env}-daily"
  budget_type       = "COST"
  limit_amount      = tostring(var.daily_limit_usd)
  limit_unit        = "USD"
  time_unit         = "DAILY"
  time_period_start = "2024-01-01_00:00"

  dynamic "notification" {
    for_each = local.email_notifications
    content {
      comparison_operator        = notification.value.comparison_operator
      threshold                  = notification.value.threshold
      threshold_type             = notification.value.threshold_type
      notification_type          = notification.value.notification_type
      subscriber_email_addresses = notification.value.subscriber_email_addresses
    }
  }

  dynamic "notification" {
    for_each = local.sns_notifications
    content {
      comparison_operator       = notification.value.comparison_operator
      threshold                 = notification.value.threshold
      threshold_type            = notification.value.threshold_type
      notification_type         = notification.value.notification_type
      subscriber_sns_topic_arns = notification.value.subscriber_sns_topic_arns
    }
  }
}

# ── Forecasted Budget Alert (80% of monthly equivalent) ───────────────────────
resource "aws_budgets_budget" "monthly_forecast" {
  name              = "colab-${var.env}-monthly-forecast"
  budget_type       = "COST"
  limit_amount      = tostring(var.daily_limit_usd * 30)
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2024-01-01_00:00"

  dynamic "notification" {
    for_each = local.email_notifications
    content {
      comparison_operator        = notification.value.comparison_operator
      threshold                  = notification.value.threshold
      threshold_type             = notification.value.threshold_type
      notification_type          = "FORECASTED"
      subscriber_email_addresses = notification.value.subscriber_email_addresses
    }
  }

  dynamic "notification" {
    for_each = local.sns_notifications
    content {
      comparison_operator       = notification.value.comparison_operator
      threshold                 = notification.value.threshold
      threshold_type            = notification.value.threshold_type
      notification_type         = "FORECASTED"
      subscriber_sns_topic_arns = notification.value.subscriber_sns_topic_arns
    }
  }
}
