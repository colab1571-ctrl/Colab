output "bucket_arns" {
  value = {
    portfolio     = aws_s3_bucket.portfolio.arn
    chat_files    = aws_s3_bucket.chat_files.arn
    audit_logs    = aws_s3_bucket.audit_logs.arn
    mockup_assets = aws_s3_bucket.mockup_assets.arn
    web_static    = aws_s3_bucket.web_static.arn
  }
  description = "Map of bucket-key to ARN for all five S3 buckets."
}

output "bucket_names" {
  value = {
    portfolio     = aws_s3_bucket.portfolio.id
    chat_files    = aws_s3_bucket.chat_files.id
    audit_logs    = aws_s3_bucket.audit_logs.id
    mockup_assets = aws_s3_bucket.mockup_assets.id
    web_static    = aws_s3_bucket.web_static.id
  }
  description = "Map of bucket-key to bucket name."
}

output "cloudfront_domain_names" {
  value = {
    for k, dist in aws_cloudfront_distribution.this : k => dist.domain_name
  }
  description = "Map of bucket-key to CloudFront distribution domain name."
}

output "cloudfront_distribution_ids" {
  value = {
    for k, dist in aws_cloudfront_distribution.this : k => dist.id
  }
  description = "Map of bucket-key to CloudFront distribution ID."
}
