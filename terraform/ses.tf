# =============================================================================
# SES -- Email Sending Configuration
# =============================================================================
#
# SES is used by the Celery workers to dispatch phishing-simulation emails.
# This configuration:
#   1. Verifies the sending domain identity
#   2. Sets up DKIM signing (3 CNAME records)
#   3. Creates an IAM policy for ses:SendRawEmail (attached in ecs.tf)
#
# IMPORTANT: New AWS accounts start in the SES sandbox, which limits sending
# to verified addresses only.  To send to arbitrary recipients (required for
# phishing simulations), you must request production access via the AWS
# console:  SES -> Account dashboard -> Request production access.
# This is a manual step that cannot be automated via Terraform.
# =============================================================================

# ---------------------------------------------------------------------------
# Domain Identity
# ---------------------------------------------------------------------------

resource "aws_ses_domain_identity" "main" {
  domain = var.ses_sending_domain
}

# ---------------------------------------------------------------------------
# DKIM -- generates 3 CNAME records for DKIM signing
# ---------------------------------------------------------------------------

resource "aws_ses_domain_dkim" "main" {
  domain = aws_ses_domain_identity.main.domain
}

# Create the DKIM verification CNAME records in Route 53
resource "aws_route53_record" "ses_dkim" {
  count = 3

  zone_id = data.aws_route53_zone.main.zone_id
  name    = "${aws_ses_domain_dkim.main.dkim_tokens[count.index]}._domainkey.${var.ses_sending_domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_ses_domain_dkim.main.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

# ---------------------------------------------------------------------------
# Domain Verification TXT Record
# ---------------------------------------------------------------------------

resource "aws_route53_record" "ses_verification" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "_amazonses.${var.ses_sending_domain}"
  type    = "TXT"
  ttl     = 600
  records = [aws_ses_domain_identity.main.verification_token]
}

# ---------------------------------------------------------------------------
# Mail-from domain (optional but recommended for better deliverability)
# ---------------------------------------------------------------------------

resource "aws_ses_domain_mail_from" "main" {
  domain           = aws_ses_domain_identity.main.domain
  mail_from_domain = "mail.${var.ses_sending_domain}"
}

# MX record for custom MAIL FROM
resource "aws_route53_record" "ses_mail_from_mx" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "mail.${var.ses_sending_domain}"
  type    = "MX"
  ttl     = 600
  records = ["10 feedback-smtp.${var.aws_region}.amazonses.com"]
}

# SPF record for custom MAIL FROM
resource "aws_route53_record" "ses_mail_from_spf" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "mail.${var.ses_sending_domain}"
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com -all"]
}
