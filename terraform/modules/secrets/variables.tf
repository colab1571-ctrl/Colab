variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "services" {
  type        = list(string)
  description = "List of microservice names. One Secrets Manager entry is created per service at colab/<env>/<svc>/env."
  default     = []
}

variable "shared_secrets" {
  type        = map(any)
  description = "Map of shared secret name to initial value (null = empty placeholder). Created at colab/<env>/shared/<name>. Keys: apns, fcm, jwt (and any others)."
  default     = {}
}

variable "recovery_window_in_days" {
  type        = number
  description = "Number of days before a deleted secret is permanently removed. Use 7 for dev, 30 for prod."
  default     = 7
}
