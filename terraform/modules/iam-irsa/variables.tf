variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name (used for naming conventions only)."
}

variable "oidc_arn" {
  type        = string
  description = "ARN of the EKS OIDC provider (from eks module output oidc_provider_arn)."
}

variable "oidc_url" {
  type        = string
  description = "URL of the EKS OIDC provider without https:// prefix (from eks module output oidc_provider_url)."
}

variable "services" {
  type        = list(string)
  description = "List of microservice names. One IAM role is created per service."
  default     = []
}

variable "s3_bucket_arns" {
  type        = map(string)
  description = "Map of bucket-key to ARN from the s3 module (portfolio, chat_files, audit_logs, mockup_assets, web_static)."
  default     = {}
}

variable "sns_platform_app_arns" {
  type        = list(string)
  description = "ARNs of SNS platform applications for notification-svc permissions."
  default     = []
}
