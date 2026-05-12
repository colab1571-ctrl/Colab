output "primary_endpoint" {
  value       = var.cluster_mode_enabled ? null : aws_elasticache_replication_group.this.primary_endpoint_address
  description = "Primary endpoint (non-cluster mode). Use rediss:// scheme with auth token."
}

output "reader_endpoint" {
  value       = var.cluster_mode_enabled ? null : aws_elasticache_replication_group.this.reader_endpoint_address
  description = "Reader endpoint (non-cluster mode)."
}

output "configuration_endpoint" {
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.this.configuration_endpoint_address : null
  description = "Configuration endpoint (cluster mode only). Use RedisCluster client class."
}

output "auth_secret_arn" {
  value       = aws_secretsmanager_secret.auth_token.arn
  description = "ARN of the Secrets Manager secret containing the Redis auth token."
}

output "security_group_id" {
  value       = aws_security_group.redis.id
  description = "Security group ID attached to the Redis replication group."
}

output "port" {
  value       = 6379
  description = "Redis port."
}
