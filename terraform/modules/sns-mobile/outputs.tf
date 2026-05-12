output "apns_platform_app_arn" {
  value       = var.apns_credentials_secret_arn != "" ? aws_sns_platform_application.apns[0].arn : null
  description = "ARN of the APNs SNS platform application. Null until credentials are seeded."
}

output "fcm_platform_app_arn" {
  value       = var.fcm_credentials_secret_arn != "" ? aws_sns_platform_application.fcm[0].arn : null
  description = "ARN of the FCM SNS platform application. Null until credentials are seeded."
}

output "publisher_role_arn" {
  value       = aws_iam_role.publisher.arn
  description = "ARN of the IAM role that notification-svc uses to publish SNS mobile push messages."
}
