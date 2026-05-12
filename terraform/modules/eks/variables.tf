variable "env" {
  type        = string
  description = "Environment slug."
}

variable "vpc_id" {
  type        = string
  description = "VPC id from the vpc module."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for nodes."
}

variable "cluster_version" {
  type        = string
  description = "EKS Kubernetes version."
  default     = "1.30"
}

variable "node_groups" {
  type = map(object({
    instance_types = list(string)
    desired_size   = number
    min_size       = number
    max_size       = number
    capacity_type  = optional(string, "ON_DEMAND")
    taints = optional(list(object({
      key    = string
      value  = string
      effect = string
    })), [])
  }))
  description = "Managed node groups keyed by logical name."
}
