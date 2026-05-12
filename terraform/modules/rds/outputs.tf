output "endpoint" {
  value       = aws_db_instance.this.endpoint
  description = "Primary RDS endpoint (host:port)."
}

output "port" {
  value       = aws_db_instance.this.port
  description = "RDS port (5432)."
}

output "db_name" {
  value       = aws_db_instance.this.db_name
  description = "Initial database name."
}

output "master_secret_arn" {
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
  description = "ARN of the Secrets Manager secret containing the master credentials (managed by AWS)."
}

output "security_group_id" {
  value       = aws_security_group.rds.id
  description = "Security group ID attached to the RDS instance."
}

output "replica_endpoints" {
  value       = aws_db_instance.replica[*].endpoint
  description = "Read replica endpoints (empty list if read_replica_count=0)."
}
