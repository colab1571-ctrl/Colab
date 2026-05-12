output "identity_arn" {
  value       = aws_sesv2_email_identity.domain.arn
  description = "ARN of the SES v2 domain identity."
}

output "configuration_set_name" {
  value       = aws_sesv2_configuration_set.this.configuration_set_name
  description = "SES configuration set name to reference in SendEmail calls."
}

output "bounce_topic_arn" {
  value       = aws_sns_topic.bounce.arn
  description = "ARN of the SNS topic receiving SES bounce notifications."
}

output "complaint_topic_arn" {
  value       = aws_sns_topic.complaint.arn
  description = "ARN of the SNS topic receiving SES complaint notifications."
}
