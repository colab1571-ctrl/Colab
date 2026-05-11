terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

resource "aws_route53_zone" "this" {
  name = var.apex
  tags = { Name = "colab-${var.env}" }
}
