variable "aws_region" {
  type        = string
  description = "Primary AWS region for prod stack."
  default     = "us-east-1"
}

variable "env" {
  type        = string
  description = "Environment slug."
  default     = "prod"
}

variable "apex_domain" {
  type        = string
  description = "Apex domain (e.g., colab.test). Used by DNS/ACM/SES/Ingress."
}

variable "email_domain" {
  type        = string
  description = "Domain used by SES for sender identity. Typically apex or a subdomain."
}

variable "budget_alert_email" {
  type        = string
  description = "Email address for AWS Budgets cost alerts."
  default     = ""
}
