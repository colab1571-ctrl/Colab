output "certificate_arn" {
  value       = aws_acm_certificate_validation.this.certificate_arn
  description = "Validated ACM certificate ARN."
}

output "certificate_domain_validation_options" {
  value       = aws_acm_certificate.this.domain_validation_options
  description = "Domain validation options (for debugging)."
}
