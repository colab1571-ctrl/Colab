terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

# ── Security Group ───────────────────────────────────────────────────────────
resource "aws_security_group" "rds" {
  name        = "colab-${var.env}-rds"
  description = "RDS Postgres ingress from allowed SGs"
  vpc_id      = var.vpc_id

  tags = { Name = "colab-${var.env}-rds" }
}

resource "aws_vpc_security_group_ingress_rule" "postgres" {
  for_each = toset([for id in var.allowed_sg_ids : id])

  security_group_id            = aws_security_group.rds.id
  description                  = "Postgres from ${each.value}"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  referenced_security_group_id = each.value
}

resource "aws_vpc_security_group_egress_rule" "rds_all" {
  security_group_id = aws_security_group.rds.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ── Subnet Group ─────────────────────────────────────────────────────────────
resource "aws_db_subnet_group" "this" {
  name        = "colab-${var.env}"
  description = "Isolated subnets for RDS Postgres (colab-${var.env})"
  subnet_ids  = var.subnet_ids

  tags = { Name = "colab-${var.env}-rds-subnet-group" }
}

# ── Parameter Group (force_ssl=1, pg_stat_statements preload) ────────────────
resource "aws_db_parameter_group" "this" {
  name        = "colab-${var.env}-postgres16"
  family      = "postgres16"
  description = "colab-${var.env} Postgres 16 — force_ssl + stat_statements"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "immediate"
  }

  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  tags = { Name = "colab-${var.env}-postgres16" }
}

# ── Primary Instance ──────────────────────────────────────────────────────────
resource "aws_db_instance" "this" {
  identifier        = "colab-${var.env}"
  engine            = "postgres"
  engine_version    = "16.4"
  instance_class    = var.instance_class
  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username

  # AWS-managed master credential minted in Secrets Manager
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  parameter_group_name   = aws_db_parameter_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az                  = var.multi_az
  deletion_protection       = var.deletion_protection
  backup_retention_period   = var.backup_retention_period
  delete_automated_backups  = false
  copy_tags_to_snapshot     = true
  auto_minor_version_upgrade = true
  apply_immediately         = false

  skip_final_snapshot    = !var.deletion_protection
  final_snapshot_identifier = var.deletion_protection ? "colab-${var.env}-final" : null

  tags = { Name = "colab-${var.env}" }
}

# ── Read Replicas (prod only) ─────────────────────────────────────────────────
resource "aws_db_instance" "replica" {
  count = var.read_replica_count

  identifier          = "colab-${var.env}-replica-${count.index}"
  replicate_source_db = aws_db_instance.this.identifier
  instance_class      = var.instance_class
  storage_encrypted   = true
  publicly_accessible = false

  auto_minor_version_upgrade = true
  apply_immediately          = false
  skip_final_snapshot        = true

  tags = { Name = "colab-${var.env}-replica-${count.index}" }
}
