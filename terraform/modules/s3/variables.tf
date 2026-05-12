variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "cloudfront_acm_arn" {
  type        = string
  description = "ACM certificate ARN in us-east-1 for CloudFront distributions."
  default     = ""
}

variable "cloudfront_aliases" {
  type        = map(string)
  description = "Map of bucket-key to FQDN alias for CloudFront. Keys: portfolio, chat_files, mockup_assets, web_static."
  default     = {}
}

variable "enable_replication" {
  type        = bool
  description = "Enable cross-region replication of audit-logs to us-west-2."
  default     = false
}

variable "audit_object_lock" {
  type        = bool
  description = "Enable S3 Object Lock (COMPLIANCE mode, 3-year retention) on audit-logs bucket."
  default     = false
}

variable "enable_waf" {
  type        = bool
  description = "Attach an AWS WAF web ACL to CloudFront distributions."
  default     = false
}
