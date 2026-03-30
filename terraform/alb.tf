# =============================================================================
# Application Load Balancers -- Tracking & Dashboard
# =============================================================================
#
# Two ALBs enforce the isolation boundary between public tracking traffic
# and internal dashboard/API traffic:
#
#   1. tracking-alb (internet-facing)
#      - Receives campaign recipient clicks (potentially massive bursts)
#      - Routes all traffic to the tracking ECS service
#      - Stateless -- no stickiness required
#      - Short idle timeout (tracking requests are sub-second)
#
#   2. dashboard-alb (internet-facing, restricted by SG)
#      - Serves the admin dashboard and API
#      - Path-based routing: /api/* -> API service, /* -> frontend
#      - Longer idle timeout for interactive dashboard sessions
#      - SG restricts access to configured CIDRs (office/VPN)
# =============================================================================

# ---------------------------------------------------------------------------
# S3 Bucket Policy Data -- allow ALB access logging
# ---------------------------------------------------------------------------

data "aws_elb_service_account" "main" {}

# ===========================================================================
# 1. Tracking ALB
# ===========================================================================

resource "aws_lb" "tracking" {
  name               = "${local.name_prefix}-tracking-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_tracking.id]
  subnets            = aws_subnet.public[*].id

  idle_timeout = 30 # Tracking requests are fast -- 30s is generous

  access_logs {
    bucket  = aws_s3_bucket.alb_logs.id
    prefix  = "tracking-alb"
    enabled = true
  }

  tags = {
    Name    = "${local.name_prefix}-tracking-alb"
    Service = "tracking"
  }
}

# -- Target Group: tracking service ------------------------------------------

resource "aws_lb_target_group" "tracking" {
  name        = "${local.name_prefix}-tracking-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # Required for Fargate awsvpc networking

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  # Stickiness disabled -- tracking endpoints are stateless.  Each request
  # carries a unique tracking token; no session affinity needed.
  stickiness {
    type    = "lb_cookie"
    enabled = false
  }

  deregistration_delay = 30 # Drain quickly during deployments

  tags = {
    Name    = "${local.name_prefix}-tracking-tg"
    Service = "tracking"
  }
}

# -- Listeners ----------------------------------------------------------------

# HTTPS listener (primary)
resource "aws_lb_listener" "tracking_https" {
  load_balancer_arn = aws_lb.tracking.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tracking.arn
  }

  tags = {
    Name = "${local.name_prefix}-tracking-https"
  }
}

# HTTP listener -- redirect to HTTPS
resource "aws_lb_listener" "tracking_http" {
  load_balancer_arn = aws_lb.tracking.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  tags = {
    Name = "${local.name_prefix}-tracking-http-redirect"
  }
}

# ===========================================================================
# 2. Dashboard ALB
# ===========================================================================

resource "aws_lb" "dashboard" {
  name               = "${local.name_prefix}-dashboard-alb"
  internal           = false # Internet-facing but SG-restricted
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_dashboard.id]
  subnets            = aws_subnet.public[*].id

  # Longer timeout for dashboard sessions (users may leave tabs open,
  # long-running report downloads, etc.)
  idle_timeout = 120

  access_logs {
    bucket  = aws_s3_bucket.alb_logs.id
    prefix  = "dashboard-alb"
    enabled = true
  }

  tags = {
    Name    = "${local.name_prefix}-dashboard-alb"
    Service = "dashboard"
  }
}

# -- Target Group: frontend (default route) ----------------------------------

resource "aws_lb_target_group" "frontend" {
  name        = "${local.name_prefix}-frontend-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/"
    protocol            = "HTTP"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  deregistration_delay = 60

  tags = {
    Name    = "${local.name_prefix}-frontend-tg"
    Service = "frontend"
  }
}

# -- Target Group: API (/api/*) ----------------------------------------------

resource "aws_lb_target_group" "api" {
  name        = "${local.name_prefix}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  deregistration_delay = 60

  tags = {
    Name    = "${local.name_prefix}-api-tg"
    Service = "api"
  }
}

# -- Listeners ----------------------------------------------------------------

# HTTPS listener with path-based routing
resource "aws_lb_listener" "dashboard_https" {
  load_balancer_arn = aws_lb.dashboard.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  # Default action: forward to frontend
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  tags = {
    Name = "${local.name_prefix}-dashboard-https"
  }
}

# Path-based rule: /api/* -> API target group
resource "aws_lb_listener_rule" "api_routing" {
  listener_arn = aws_lb_listener.dashboard_https.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }

  tags = {
    Name = "${local.name_prefix}-api-routing-rule"
  }
}
