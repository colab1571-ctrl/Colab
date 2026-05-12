variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "domain" {
  type        = string
  description = "Domain to verify in SES (e.g. dev.colab.app or colab.app for prod)."
}

variable "route53_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID to create DKIM, SPF, and DMARC records."
}

variable "dmarc_rua_email" {
  type        = string
  description = "Email address for DMARC aggregate report (rua). E.g. dmarc@colab.app."
}
