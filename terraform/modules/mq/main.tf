terraform {
  required_version = ">= 1.7"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.40" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

# ── Master Password ───────────────────────────────────────────────────────────
resource "random_password" "master" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "master" {
  name                    = "colab/${var.env}/shared/mq-master"
  description             = "Amazon MQ RabbitMQ master credentials for colab-${var.env}"
  recovery_window_in_days = 7

  tags = { Name = "colab-${var.env}-mq-master" }
}

resource "aws_secretsmanager_secret_version" "master" {
  secret_id = aws_secretsmanager_secret.master.id
  secret_string = jsonencode({
    username = var.mq_username
    password = random_password.master.result
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ── Security Group ────────────────────────────────────────────────────────────
resource "aws_security_group" "mq" {
  name        = "colab-${var.env}-mq"
  description = "Amazon MQ RabbitMQ ingress from allowed SGs"
  vpc_id      = var.vpc_id

  tags = { Name = "colab-${var.env}-mq" }
}

resource "aws_vpc_security_group_ingress_rule" "amqp" {
  for_each = toset([for id in var.allowed_sg_ids : id])

  security_group_id            = aws_security_group.mq.id
  description                  = "AMQP TLS from ${each.value}"
  from_port                    = 5671
  to_port                      = 5671
  ip_protocol                  = "tcp"
  referenced_security_group_id = each.value
}

resource "aws_vpc_security_group_ingress_rule" "web_console" {
  for_each = toset([for id in var.allowed_sg_ids : id])

  security_group_id            = aws_security_group.mq.id
  description                  = "Web console from ${each.value}"
  from_port                    = 15671
  to_port                      = 15671
  ip_protocol                  = "tcp"
  referenced_security_group_id = each.value
}

resource "aws_vpc_security_group_egress_rule" "mq_all" {
  security_group_id = aws_security_group.mq.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ── MQ Broker ─────────────────────────────────────────────────────────────────
locals {
  # SINGLE_INSTANCE needs exactly 1 subnet; CLUSTER_MULTI_AZ needs 3
  broker_subnet_ids = var.deployment_mode == "SINGLE_INSTANCE" ? [var.subnet_ids[0]] : var.subnet_ids
}

resource "aws_mq_broker" "this" {
  broker_name         = "colab-${var.env}"
  engine_type         = "RabbitMQ"
  engine_version      = var.engine_version
  host_instance_type  = var.instance_type
  deployment_mode     = var.deployment_mode
  publicly_accessible = false
  subnet_ids          = local.broker_subnet_ids
  security_groups     = [aws_security_group.mq.id]

  auto_minor_version_upgrade = true

  user {
    username = var.mq_username
    password = random_password.master.result
  }

  maintenance_window_start_time {
    day_of_week = "SUNDAY"
    time_of_day = "03:00"
    time_zone   = "UTC"
  }

  tags = { Name = "colab-${var.env}-mq" }

  depends_on = [aws_secretsmanager_secret_version.master]
}
