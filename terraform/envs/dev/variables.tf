variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "env" {
  type    = string
  default = "dev"
}

variable "apex_domain" {
  type        = string
  description = "Apex domain (e.g., example.com). Hosted zone created if absent."
}

variable "email_domain" {
  type        = string
  description = "Domain used for SES (typically same as apex)."
}
