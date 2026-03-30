# =============================================================================
# Route 53 -- DNS Records
# =============================================================================
#
# Creates alias records pointing the tracking and dashboard domains to their
# respective ALBs.  The hosted zone is looked up by domain_name (it must
# already exist in Route 53).
# =============================================================================

# ---------------------------------------------------------------------------
# Data Source -- existing hosted zone
# ---------------------------------------------------------------------------

data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# ---------------------------------------------------------------------------
# Tracking Domain -> Tracking ALB
# ---------------------------------------------------------------------------

resource "aws_route53_record" "tracking" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.tracking_domain
  type    = "A"

  alias {
    name                   = aws_lb.tracking.dns_name
    zone_id                = aws_lb.tracking.zone_id
    evaluate_target_health = true
  }
}

# IPv6 AAAA record for tracking (ALBs are dual-stack)
resource "aws_route53_record" "tracking_ipv6" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.tracking_domain
  type    = "AAAA"

  alias {
    name                   = aws_lb.tracking.dns_name
    zone_id                = aws_lb.tracking.zone_id
    evaluate_target_health = true
  }
}

# ---------------------------------------------------------------------------
# Dashboard Domain -> Dashboard ALB
# ---------------------------------------------------------------------------

resource "aws_route53_record" "dashboard" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.dashboard_domain
  type    = "A"

  alias {
    name                   = aws_lb.dashboard.dns_name
    zone_id                = aws_lb.dashboard.zone_id
    evaluate_target_health = true
  }
}

# IPv6 AAAA record for dashboard
resource "aws_route53_record" "dashboard_ipv6" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.dashboard_domain
  type    = "AAAA"

  alias {
    name                   = aws_lb.dashboard.dns_name
    zone_id                = aws_lb.dashboard.zone_id
    evaluate_target_health = true
  }
}
