output "service_secret_arns" {
  value = {
    for svc in var.services : svc => aws_secretsmanager_secret.service[svc].arn
  }
  description = "Map of service name to Secrets Manager secret ARN (colab/<env>/<svc>/env)."
}

output "shared_secret_arns" {
  value = {
    for name in keys(var.shared_secrets) : name => aws_secretsmanager_secret.shared[name].arn
  }
  description = "Map of shared secret name to Secrets Manager secret ARN (colab/<env>/shared/<name>)."
}
