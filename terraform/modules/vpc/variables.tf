variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "cidr" {
  type        = string
  description = "VPC CIDR (must be /16)."
}

variable "azs" {
  type        = list(string)
  description = "Availability zones to span."
}

variable "single_nat" {
  type        = bool
  description = "If true, use a single NAT GW (dev cost optimization). False = one per AZ."
  default     = false
}

variable "enable_flow_logs" {
  type        = bool
  description = "Enable VPC flow logs to CloudWatch."
  default     = false
}

variable "enable_vpc_endpoints" {
  type        = bool
  description = "Provision interface endpoints for AWS APIs (prod cost optimization)."
  default     = false
}
