output "vpc_id" {
  value       = aws_vpc.this.id
  description = "VPC ID."
}

output "public_subnet_ids" {
  value       = aws_subnet.public[*].id
  description = "Public subnet IDs (one per AZ)."
}

output "private_subnet_ids" {
  value       = aws_subnet.private[*].id
  description = "Private subnet IDs (one per AZ); routed via NAT."
}

output "isolated_subnet_ids" {
  value       = aws_subnet.isolated[*].id
  description = "Isolated subnet IDs (no NAT egress); used by RDS/Redis/MQ."
}

output "default_security_group_id" {
  value       = aws_vpc.this.default_security_group_id
  description = "Default SG of the VPC."
}

output "vpc_cidr" {
  value       = aws_vpc.this.cidr_block
  description = "VPC CIDR block."
}
