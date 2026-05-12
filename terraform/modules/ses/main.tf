terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
}

# ── SES v2 Domain Identity ────────────────────────────────────────────────────
resource "aws_sesv2_email_identity" "domain" {
  email_identity         = var.domain
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name

  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }

  tags = { Name = "colab-${var.env}-ses-${var.domain}" }
}

# ── DKIM Route 53 Records ─────────────────────────────────────────────────────
resource "aws_route53_record" "dkim" {
  count = 3

  zone_id = var.route53_zone_id
  name    = "${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.domain}"
  type    = "CNAME"
  ttl     = 300
  records = ["${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

# ── SPF TXT Record ────────────────────────────────────────────────────────────
resource "aws_route53_record" "spf" {
  zone_id = var.route53_zone_id
  name    = var.domain
  type    = "TXT"
  ttl     = 300
  records = ["v=spf1 include:amazonses.com ~all"]
}

# ── DMARC TXT Record ──────────────────────────────────────────────────────────
resource "aws_route53_record" "dmarc" {
  zone_id = var.route53_zone_id
  name    = "_dmarc.${var.domain}"
  type    = "TXT"
  ttl     = 300
  records = ["v=DMARC1; p=none; rua=mailto:${var.dmarc_rua_email}; ruf=mailto:${var.dmarc_rua_email}; fo=1"]
}

# ── SNS Topics for bounce + complaint ─────────────────────────────────────────
resource "aws_sns_topic" "bounce" {
  name = "colab-${var.env}-ses-bounce"
  tags = { Name = "colab-${var.env}-ses-bounce" }
}

resource "aws_sns_topic" "complaint" {
  name = "colab-${var.env}-ses-complaint"
  tags = { Name = "colab-${var.env}-ses-complaint" }
}

# ── Configuration Set ─────────────────────────────────────────────────────────
resource "aws_sesv2_configuration_set" "this" {
  configuration_set_name = "colab-${var.env}"

  sending_options {
    sending_enabled = true
  }

  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }

  tags = { Name = "colab-${var.env}-ses-config-set" }
}

# ── Event Destinations (bounce + complaint → SNS) ─────────────────────────────
resource "aws_sesv2_configuration_set_event_destination" "bounce" {
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name
  event_destination_name = "bounce"

  event_destination {
    enabled              = true
    matching_event_types = ["BOUNCE", "PERMANENT_BOUNCE", "TRANSIENT_BOUNCE"]

    sns_destination {
      topic_arn = aws_sns_topic.bounce.arn
    }
  }
}

resource "aws_sesv2_configuration_set_event_destination" "complaint" {
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name
  event_destination_name = "complaint"

  event_destination {
    enabled              = true
    matching_event_types = ["COMPLAINT"]

    sns_destination {
      topic_arn = aws_sns_topic.complaint.arn
    }
  }
}

# ── NOTE: T-H-03 — SES Production Access ─────────────────────────────────────
# SES sandbox exit requires an AWS support ticket. File early; takes 24–48h.
# From the AWS console: Support Center → Create Case → "Service limit increase"
# → Service: SES Sending Limits. Request: "Move out of sandbox for <domain>".
# This is NOT managed by Terraform.
