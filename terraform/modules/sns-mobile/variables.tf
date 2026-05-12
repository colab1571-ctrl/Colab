variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "apns_credentials_secret_arn" {
  type        = string
  description = "Secrets Manager ARN containing APNs token-based auth credentials (team_id, key_id, private_key). Populated manually before apply."
  default     = ""
}

variable "fcm_credentials_secret_arn" {
  type        = string
  description = "Secrets Manager ARN containing the FCM/Firebase server key JSON. Populated manually before apply."
  default     = ""
}

variable "apns_sandbox" {
  type        = bool
  description = "Use APNs sandbox endpoint (true for dev/staging). False = production APNs."
  default     = true
}
