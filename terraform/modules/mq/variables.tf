variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID in which to place the MQ broker and security group."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Isolated subnet IDs. SINGLE_INSTANCE uses [0]; CLUSTER_MULTI_AZ uses all three."
}

variable "instance_type" {
  type        = string
  description = "MQ broker instance type (e.g. mq.t3.micro, mq.m5.large)."
  default     = "mq.t3.micro"
}

variable "deployment_mode" {
  type        = string
  description = "Broker deployment mode: SINGLE_INSTANCE or CLUSTER_MULTI_AZ."
  default     = "SINGLE_INSTANCE"

  validation {
    condition     = contains(["SINGLE_INSTANCE", "CLUSTER_MULTI_AZ"], var.deployment_mode)
    error_message = "deployment_mode must be SINGLE_INSTANCE or CLUSTER_MULTI_AZ."
  }
}

variable "allowed_sg_ids" {
  type        = list(string)
  description = "Security group IDs allowed ingress on AMQP (5671) and web console (15671)."
  default     = []
}

variable "engine_version" {
  type        = string
  description = "RabbitMQ engine version."
  default     = "3.13"
}

variable "mq_username" {
  type        = string
  description = "RabbitMQ administrative username."
  default     = "colab_admin"
}
