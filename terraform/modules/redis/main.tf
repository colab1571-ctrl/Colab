terraform {
  required_version = ">= 1.7"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.40" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

# ── Auth Token ────────────────────────────────────────────────────────────────
resource "random_password" "auth_token" {
  length           = 32
  special          = false # ElastiCache auth token must be printable ASCII, no special chars
  override_special = ""
}

resource "aws_secretsmanager_secret" "auth_token" {
  name                    = "colab/${var.env}/shared/redis-auth"
  description             = "ElastiCache Redis auth token for colab-${var.env}"
  recovery_window_in_days = 7

  tags = { Name = "colab-${var.env}-redis-auth" }
}

resource "aws_secretsmanager_secret_version" "auth_token" {
  secret_id = aws_secretsmanager_secret.auth_token.id
  secret_string = jsonencode({
    auth_token = random_password.auth_token.result
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ── Security Group ────────────────────────────────────────────────────────────
resource "aws_security_group" "redis" {
  name        = "colab-${var.env}-redis"
  description = "ElastiCache Redis ingress from allowed SGs"
  vpc_id      = var.vpc_id

  tags = { Name = "colab-${var.env}-redis" }
}

resource "aws_vpc_security_group_ingress_rule" "redis" {
  for_each = toset([for id in var.allowed_sg_ids : id])

  security_group_id            = aws_security_group.redis.id
  description                  = "Redis from ${each.value}"
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
  referenced_security_group_id = each.value
}

resource "aws_vpc_security_group_egress_rule" "redis_all" {
  security_group_id = aws_security_group.redis.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ── Subnet Group ──────────────────────────────────────────────────────────────
resource "aws_elasticache_subnet_group" "this" {
  name        = "colab-${var.env}"
  description = "Isolated subnets for ElastiCache Redis (colab-${var.env})"
  subnet_ids  = var.subnet_ids

  tags = { Name = "colab-${var.env}-redis-subnet-group" }
}

# ── Parameter Group ───────────────────────────────────────────────────────────
resource "aws_elasticache_parameter_group" "this" {
  name        = "colab-${var.env}-redis71"
  family      = var.cluster_mode_enabled ? "redis7.cluster.on" : "redis7"
  description = "colab-${var.env} Redis 7.1 parameter group"

  tags = { Name = "colab-${var.env}-redis71" }
}

# ── Replication Group ─────────────────────────────────────────────────────────
resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "colab-${var.env}"
  description          = "colab-${var.env} Redis replication group"

  engine         = "redis"
  engine_version = var.engine_version
  node_type      = var.node_type

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]
  parameter_group_name = aws_elasticache_parameter_group.this.name

  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  auth_token                 = random_password.auth_token.result
  auth_token_update_strategy = "ROTATE"

  # Cluster mode: num_node_groups controls sharding
  num_node_groups         = var.cluster_mode_enabled ? var.num_shards : 1
  replicas_per_node_group = var.replicas_per_shard

  automatic_failover_enabled = var.replicas_per_shard > 0 ? true : false
  multi_az_enabled           = var.replicas_per_shard > 0 ? true : false

  apply_immediately          = false
  auto_minor_version_upgrade = true

  tags = { Name = "colab-${var.env}-redis" }
}
