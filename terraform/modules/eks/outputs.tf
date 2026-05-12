output "cluster_name" {
  value       = module.eks.cluster_name
  description = "EKS cluster name."
}

output "cluster_endpoint" {
  value       = module.eks.cluster_endpoint
  description = "EKS API endpoint."
}

output "cluster_ca" {
  value       = module.eks.cluster_certificate_authority_data
  description = "Cluster CA (base64)."
  sensitive   = true
}

output "oidc_provider_arn" {
  value       = module.eks.oidc_provider_arn
  description = "OIDC provider ARN for IRSA."
}

output "oidc_provider_url" {
  value       = module.eks.cluster_oidc_issuer_url
  description = "OIDC issuer URL."
}

output "node_role_arn" {
  value       = module.eks.eks_managed_node_groups["app"].iam_role_arn
  description = "Node IAM role ARN."
}

output "node_security_group_id" {
  value       = module.eks.node_security_group_id
  description = "Security group ID for EKS worker nodes."
}
