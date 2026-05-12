variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID in which to place the replication group and security group."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Isolated subnet IDs for the ElastiCache subnet group."
}

variable "node_type" {
  type        = string
  description = "ElastiCache node type (e.g. cache.t4g.micro, cache.m6g.large)."
  default     = "cache.t4g.micro"
}

variable "cluster_mode_enabled" {
  type        = bool
  description = "Enable Redis cluster mode (multiple shards). Required for prod scale."
  default     = false
}

variable "num_shards" {
  type        = number
  description = "Number of shards (node groups). Used only when cluster_mode_enabled=true."
  default     = 1
}

variable "replicas_per_shard" {
  type        = number
  description = "Number of replica nodes per shard."
  default     = 0
}

variable "allowed_sg_ids" {
  type        = list(string)
  description = "Security group IDs allowed ingress on port 6379 (e.g. EKS node SG)."
  default     = []
}

variable "engine_version" {
  type        = string
  description = "Redis engine version."
  default     = "7.1"
}
