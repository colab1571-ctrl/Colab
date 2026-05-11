#!/usr/bin/env bash
set -euo pipefail

# Bootstraps the Terraform remote state for the Colab project.
# Creates:
#   - S3 bucket for tfstate (versioned, encrypted, public access blocked)
#   - DynamoDB table for state locking
# Idempotent.

: "${AWS_PROFILE:=colab-admin}"
: "${AWS_REGION:=us-east-1}"
PROJECT=colab
ACCOUNT_ID=$(aws --profile "$AWS_PROFILE" sts get-caller-identity --query Account --output text)
BUCKET="${PROJECT}-tfstate-${ACCOUNT_ID}-${AWS_REGION}"
TABLE="${PROJECT}-tfstate-lock"

echo "Account: $ACCOUNT_ID  Region: $AWS_REGION"
echo "State bucket: $BUCKET"
echo "Lock table:   $TABLE"

if aws --profile "$AWS_PROFILE" s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "Bucket exists."
else
  aws --profile "$AWS_PROFILE" s3api create-bucket \
    --bucket "$BUCKET" \
    --region "$AWS_REGION" \
    $( [ "$AWS_REGION" = "us-east-1" ] || echo "--create-bucket-configuration LocationConstraint=$AWS_REGION" )
  aws --profile "$AWS_PROFILE" s3api put-bucket-versioning \
    --bucket "$BUCKET" --versioning-configuration Status=Enabled
  aws --profile "$AWS_PROFILE" s3api put-bucket-encryption \
    --bucket "$BUCKET" \
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws --profile "$AWS_PROFILE" s3api put-public-access-block \
    --bucket "$BUCKET" \
    --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
  echo "Bucket created."
fi

if aws --profile "$AWS_PROFILE" dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  echo "Lock table exists."
else
  aws --profile "$AWS_PROFILE" dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$AWS_REGION"
  echo "Lock table created."
fi

cat <<EOF

Bootstrap complete.

Add this to your env backend.tf:

  terraform {
    backend "s3" {
      bucket         = "$BUCKET"
      key            = "envs/<env>/terraform.tfstate"
      region         = "$AWS_REGION"
      dynamodb_table = "$TABLE"
      encrypt        = true
    }
  }
EOF
