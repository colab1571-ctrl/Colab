variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID in which to place the RDS instance and security group."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Isolated subnet IDs for the DB subnet group (no NAT egress)."
}

variable "instance_class" {
  type        = string
  description = "RDS instance class (e.g. db.t4g.medium, db.m6g.large)."
  default     = "db.t4g.medium"
}

variable "allocated_storage" {
  type        = number
  description = "Initial storage in GiB."
  default     = 50
}

variable "multi_az" {
  type        = bool
  description = "Enable Multi-AZ standby (true for staging/prod). Also governs backup_retention_period default."
  default     = false
}

variable "deletion_protection" {
  type        = bool
  description = "Enable deletion protection. Defaults true when multi_az=true."
  default     = false
}

variable "backup_retention_period" {
  type        = number
  description = "Automated backup retention in days. Default 1 (dev); set 7+ for staging/prod."
  default     = 1
}

variable "read_replica_count" {
  type        = number
  description = "Number of read replicas to create (prod only). 0 = none."
  default     = 0
}

variable "allowed_sg_ids" {
  type        = list(string)
  description = "Security group IDs allowed ingress on port 5432 (e.g. EKS node SG)."
  default     = []
}

variable "extensions" {
  type        = list(string)
  description = "Informational only — extensions are NOT created by Terraform. A k8s db-bootstrap Job runs CREATE EXTENSION IF NOT EXISTS for each entry."
  default     = ["postgis", "vector"]
}

variable "db_name" {
  type        = string
  description = "Initial database name."
  default     = "colab"
}

variable "db_username" {
  type        = string
  description = "Master username."
  default     = "colab_admin"
}
