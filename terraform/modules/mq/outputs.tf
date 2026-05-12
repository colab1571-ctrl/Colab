output "amqp_endpoint" {
  value       = aws_mq_broker.this.instances[0].endpoints[0]
  description = "Primary AMQP TLS endpoint (amqps://host:5671)."
}

output "console_url" {
  value       = aws_mq_broker.this.instances[0].console_url
  description = "RabbitMQ management web console URL (HTTPS, port 15671)."
}

output "user_secret_arn" {
  value       = aws_secretsmanager_secret.master.arn
  description = "ARN of the Secrets Manager secret containing the MQ master credentials."
}

output "security_group_id" {
  value       = aws_security_group.mq.id
  description = "Security group ID attached to the MQ broker."
}

output "broker_id" {
  value       = aws_mq_broker.this.id
  description = "Amazon MQ broker ID."
}
