output "service_role_arns" {
  value = {
    for svc in var.services : svc => aws_iam_role.service[svc].arn
  }
  description = "Map of service name to IAM role ARN. Inject into Helm values as serviceAccount.annotations.'eks.amazonaws.com/role-arn'."
}
