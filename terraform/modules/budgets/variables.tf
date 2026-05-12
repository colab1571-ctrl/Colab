variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "daily_limit_usd" {
  type        = number
  description = "Daily cost budget limit in USD. Alerts at 80% and 100% of this amount."
}

variable "alert_email" {
  type        = string
  description = "Email address to receive budget alert notifications."
  default     = ""
}

variable "alert_sns_topic_arn" {
  type        = string
  description = "SNS topic ARN to receive budget alert notifications. Optional — use email or SNS or both."
  default     = ""
}
