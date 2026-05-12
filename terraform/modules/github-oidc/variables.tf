variable "env" {
  type        = string
  description = "Environment slug (dev|staging|prod)."
}

variable "github_repo" {
  type        = string
  description = "GitHub repository in org/repo format (e.g. colab1571-ctrl/Colab)."
}

variable "allowed_refs" {
  type        = list(string)
  description = "List of allowed ref patterns for the deploy role trust policy (e.g. refs/heads/main). Dev uses a wildcard ref."
  default     = ["refs/heads/main"]
}

variable "deploy_policy_arns" {
  type        = list(string)
  description = "Additional managed policy ARNs to attach to the deploy role."
  default     = []
}
