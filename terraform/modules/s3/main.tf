terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── Replica region provider alias (us-west-2) ─────────────────────────────────
# NOTE: When enable_replication=true, a provider alias "aws.replica" must be
# passed by the caller (env main.tf). This module references it via an alias.
# Since Terraform does not support optional provider aliases, the alias is
# always declared but only resources using it are gated by var.enable_replication.

locals {
  buckets = {
    portfolio     = "colab-portfolio-${var.env}"
    chat_files    = "colab-chat-files-${var.env}"
    audit_logs    = "colab-audit-logs-${var.env}"
    mockup_assets = "colab-mockup-assets-${var.env}"
    web_static    = "colab-web-static-${var.env}"
  }

  # Buckets that get CloudFront distributions (portfolio, chat_files, mockup_assets, web_static)
  cf_buckets = {
    portfolio     = local.buckets["portfolio"]
    chat_files    = local.buckets["chat_files"]
    mockup_assets = local.buckets["mockup_assets"]
    web_static    = local.buckets["web_static"]
  }
}

# ── S3 Buckets ────────────────────────────────────────────────────────────────

# portfolio
resource "aws_s3_bucket" "portfolio" {
  bucket        = local.buckets["portfolio"]
  force_destroy = false

  tags = { Name = local.buckets["portfolio"] }
}

# chat_files
resource "aws_s3_bucket" "chat_files" {
  bucket        = local.buckets["chat_files"]
  force_destroy = false

  tags = { Name = local.buckets["chat_files"] }
}

# audit_logs — optional object lock
resource "aws_s3_bucket" "audit_logs" {
  bucket              = local.buckets["audit_logs"]
  force_destroy       = false
  object_lock_enabled = var.audit_object_lock

  tags = { Name = local.buckets["audit_logs"] }
}

# mockup_assets
resource "aws_s3_bucket" "mockup_assets" {
  bucket        = local.buckets["mockup_assets"]
  force_destroy = false

  tags = { Name = local.buckets["mockup_assets"] }
}

# web_static
resource "aws_s3_bucket" "web_static" {
  bucket        = local.buckets["web_static"]
  force_destroy = false

  tags = { Name = local.buckets["web_static"] }
}

# ── Versioning ────────────────────────────────────────────────────────────────
resource "aws_s3_bucket_versioning" "portfolio" {
  bucket = aws_s3_bucket.portfolio.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "chat_files" {
  bucket = aws_s3_bucket.chat_files.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "mockup_assets" {
  bucket = aws_s3_bucket.mockup_assets.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "web_static" {
  bucket = aws_s3_bucket.web_static.id
  versioning_configuration { status = "Enabled" }
}

# ── SSE-S3 Encryption ─────────────────────────────────────────────────────────
resource "aws_s3_bucket_server_side_encryption_configuration" "portfolio" {
  bucket = aws_s3_bucket.portfolio.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "chat_files" {
  bucket = aws_s3_bucket.chat_files.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "mockup_assets" {
  bucket = aws_s3_bucket.mockup_assets.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web_static" {
  bucket = aws_s3_bucket.web_static.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}

# ── Public Access Block (all buckets) ─────────────────────────────────────────
locals {
  all_bucket_ids = [
    aws_s3_bucket.portfolio.id,
    aws_s3_bucket.chat_files.id,
    aws_s3_bucket.audit_logs.id,
    aws_s3_bucket.mockup_assets.id,
    aws_s3_bucket.web_static.id,
  ]
}

resource "aws_s3_bucket_public_access_block" "portfolio" {
  bucket                  = aws_s3_bucket.portfolio.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "chat_files" {
  bucket                  = aws_s3_bucket.chat_files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "audit_logs" {
  bucket                  = aws_s3_bucket.audit_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "mockup_assets" {
  bucket                  = aws_s3_bucket.mockup_assets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "web_static" {
  bucket                  = aws_s3_bucket.web_static.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Lifecycle Rules ───────────────────────────────────────────────────────────
resource "aws_s3_bucket_lifecycle_configuration" "chat_files" {
  bucket = aws_s3_bucket.chat_files.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"
    filter { prefix = "" }
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    id     = "transition-to-glacier"
    status = "Enabled"
    filter { prefix = "" }
    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

# ── Object Lock (audit-logs, prod only) ───────────────────────────────────────
resource "aws_s3_bucket_object_lock_configuration" "audit_logs" {
  count = var.audit_object_lock ? 1 : 0

  bucket = aws_s3_bucket.audit_logs.id

  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = 3
    }
  }

  depends_on = [aws_s3_bucket_versioning.audit_logs]
}

# ── Cross-Region Replication (audit-logs, prod only) ──────────────────────────
resource "aws_iam_role" "replication" {
  count = var.enable_replication ? 1 : 0
  name  = "colab-${var.env}-s3-replication"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "s3.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "replication" {
  count = var.enable_replication ? 1 : 0
  role  = aws_iam_role.replication[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetReplicationConfiguration", "s3:ListBucket"]
        Resource = aws_s3_bucket.audit_logs.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging"
        ]
        Resource = "${aws_s3_bucket.audit_logs.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ReplicateObject",
          "s3:ReplicateDelete",
          "s3:ReplicateTags"
        ]
        Resource = "arn:aws:s3:::colab-audit-logs-${var.env}-replica/*"
      }
    ]
  })
}

resource "aws_s3_bucket_replication_configuration" "audit_logs" {
  count = var.enable_replication ? 1 : 0

  bucket = aws_s3_bucket.audit_logs.id
  role   = aws_iam_role.replication[0].arn

  rule {
    id     = "replicate-all"
    status = "Enabled"

    filter { prefix = "" }

    destination {
      bucket        = "arn:aws:s3:::colab-audit-logs-${var.env}-replica"
      storage_class = "STANDARD_IA"
    }

    delete_marker_replication { status = "Enabled" }
  }

  depends_on = [aws_s3_bucket_versioning.audit_logs]
}

# ── CloudFront OAC ────────────────────────────────────────────────────────────
resource "aws_cloudfront_origin_access_control" "this" {
  for_each = local.cf_buckets

  name                              = "colab-${var.env}-${each.key}"
  description                       = "OAC for colab-${var.env} ${each.key}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ── WAF WebACL (optional, prod only) ─────────────────────────────────────────
resource "aws_wafv2_web_acl" "cloudfront" {
  count = var.enable_waf ? 1 : 0

  name        = "colab-${var.env}-cf-waf"
  description = "WAF for colab-${var.env} CloudFront distributions"
  scope       = "CLOUDFRONT"

  default_action { allow {} }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "colab-${var.env}-cf-common-rules"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "colab-${var.env}-cf-waf"
    sampled_requests_enabled   = true
  }

  tags = { Name = "colab-${var.env}-cf-waf" }
}

# ── CloudFront Distributions ──────────────────────────────────────────────────
locals {
  bucket_resources = {
    portfolio     = aws_s3_bucket.portfolio
    chat_files    = aws_s3_bucket.chat_files
    mockup_assets = aws_s3_bucket.mockup_assets
    web_static    = aws_s3_bucket.web_static
  }
}

resource "aws_cloudfront_distribution" "this" {
  for_each = local.cf_buckets

  enabled             = true
  http_version        = "http2and3"
  is_ipv6_enabled     = true
  default_root_object = each.key == "web_static" ? "index.html" : null
  price_class         = "PriceClass_100"
  web_acl_id          = var.enable_waf ? aws_wafv2_web_acl.cloudfront[0].arn : null

  aliases = lookup(var.cloudfront_aliases, each.key, null) != null ? [var.cloudfront_aliases[each.key]] : []

  origin {
    domain_name              = local.bucket_resources[each.key].bucket_regional_domain_name
    origin_id                = each.key
    origin_access_control_id = aws_cloudfront_origin_access_control.this[each.key].id
  }

  default_cache_behavior {
    target_origin_id       = each.key
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = each.key == "chat_files" ? 60 : 86400
    max_ttl     = each.key == "chat_files" ? 300 : 31536000
  }

  viewer_certificate {
    acm_certificate_arn      = var.cloudfront_acm_arn != "" ? var.cloudfront_acm_arn : null
    ssl_support_method       = var.cloudfront_acm_arn != "" ? "sni-only" : null
    minimum_protocol_version = var.cloudfront_acm_arn != "" ? "TLSv1.2_2021" : null
    cloudfront_default_certificate = var.cloudfront_acm_arn == "" ? true : false
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  tags = { Name = "colab-${var.env}-${each.key}" }

  depends_on = [
    aws_s3_bucket_public_access_block.portfolio,
    aws_s3_bucket_public_access_block.chat_files,
    aws_s3_bucket_public_access_block.mockup_assets,
    aws_s3_bucket_public_access_block.web_static,
  ]
}

# ── Bucket Policies (allow OAC) ───────────────────────────────────────────────
resource "aws_s3_bucket_policy" "portfolio" {
  bucket = aws_s3_bucket.portfolio.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudFrontOAC"
      Effect = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action   = "s3:GetObject"
      Resource = "${aws_s3_bucket.portfolio.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.this["portfolio"].arn
        }
      }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.portfolio]
}

resource "aws_s3_bucket_policy" "chat_files" {
  bucket = aws_s3_bucket.chat_files.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudFrontOAC"
      Effect = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action   = "s3:GetObject"
      Resource = "${aws_s3_bucket.chat_files.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.this["chat_files"].arn
        }
      }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.chat_files]
}

resource "aws_s3_bucket_policy" "mockup_assets" {
  bucket = aws_s3_bucket.mockup_assets.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudFrontOAC"
      Effect = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action   = "s3:GetObject"
      Resource = "${aws_s3_bucket.mockup_assets.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.this["mockup_assets"].arn
        }
      }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.mockup_assets]
}

resource "aws_s3_bucket_policy" "web_static" {
  bucket = aws_s3_bucket.web_static.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudFrontOAC"
      Effect = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action   = "s3:GetObject"
      Resource = "${aws_s3_bucket.web_static.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.this["web_static"].arn
        }
      }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.web_static]
}
