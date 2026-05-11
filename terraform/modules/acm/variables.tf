variable "env" {
  type        = string
  description = "Environment slug."
}

variable "apex" {
  type        = string
  description = "Apex domain to certify (cert covers apex + *.apex)."
}

variable "zone_id" {
  type        = string
  description = "Route 53 hosted zone ID for DNS validation."
}
