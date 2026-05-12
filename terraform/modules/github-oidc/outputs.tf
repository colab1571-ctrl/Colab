output "deploy_role_arn" {
  value       = aws_iam_role.deploy.arn
  description = "ARN of the GitHub Actions deploy role. Reference in the GHA workflow as role-to-assume."
}

output "oidc_provider_arn" {
  value       = aws_iam_openid_connect_provider.github.arn
  description = "ARN of the GitHub Actions OIDC provider (singleton per account)."
}
