output "zone_id" {
  value       = aws_route53_zone.this.zone_id
  description = "Route 53 hosted zone ID."
}

output "name_servers" {
  value       = aws_route53_zone.this.name_servers
  description = "Hosted zone NS records to configure at the registrar."
}

output "apex" {
  value       = var.apex
  description = "Apex domain."
}
