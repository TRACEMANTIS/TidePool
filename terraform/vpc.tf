# =============================================================================
# VPC, Subnets, Gateways, Route Tables, Security Groups
# =============================================================================
#
# Layout:
#   Public subnets  -- ALBs (tracking + dashboard), NAT gateway
#   Private subnets -- ECS tasks, RDS, ElastiCache
#
# Three AZs are used for resilience and to satisfy RDS Multi-AZ and
# ElastiCache cluster requirements.
# =============================================================================

data "aws_availability_zones" "available" {
  state = "available"
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.name_prefix}-vpc"
  }
}

# ---------------------------------------------------------------------------
# Internet Gateway
# ---------------------------------------------------------------------------

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${local.name_prefix}-igw"
  }
}

# ---------------------------------------------------------------------------
# Public Subnets (3 AZs) -- ALBs and NAT Gateway live here
# ---------------------------------------------------------------------------

resource "aws_subnet" "public" {
  count = 3

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index) # 10.0.0.0/24, .1, .2
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.name_prefix}-public-${data.aws_availability_zones.available.names[count.index]}"
    Tier = "public"
  }
}

# ---------------------------------------------------------------------------
# Private Subnets (3 AZs) -- ECS tasks, RDS, Redis
# ---------------------------------------------------------------------------

resource "aws_subnet" "private" {
  count = 3

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10) # 10.0.10.0/24, .11, .12
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${local.name_prefix}-private-${data.aws_availability_zones.available.names[count.index]}"
    Tier = "private"
  }
}

# ---------------------------------------------------------------------------
# NAT Gateway (single instance -- cost-conscious)
# ---------------------------------------------------------------------------
# NOTE: For production HA, deploy one NAT gateway per AZ and update the
# private route tables accordingly.  A single NAT is a SPOF but keeps costs
# manageable for initial deployment.  ECS tasks in private subnets need NAT
# for ECR image pulls, CloudWatch logging, and SES API calls.

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${local.name_prefix}-nat-eip"
  }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "${local.name_prefix}-nat"
  }

  depends_on = [aws_internet_gateway.main]
}

# ---------------------------------------------------------------------------
# Route Tables
# ---------------------------------------------------------------------------

# Public route table -- routes to the internet via IGW.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${local.name_prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count = 3

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private route table -- routes to the internet via NAT gateway.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = {
    Name = "${local.name_prefix}-private-rt"
  }
}

resource "aws_route_table_association" "private" {
  count = 3

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ---------------------------------------------------------------------------
# Security Groups
# ---------------------------------------------------------------------------

# -- Tracking ALB: public-facing, accepts HTTP/HTTPS from anywhere -----------
resource "aws_security_group" "alb_tracking" {
  name        = "${local.name_prefix}-alb-tracking"
  description = "Tracking ALB -- public HTTP/HTTPS ingress for campaign recipients"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP (redirected to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-alb-tracking-sg"
  }
}

# -- Dashboard ALB: restricted to configurable CIDRs (office / VPN) ----------
resource "aws_security_group" "alb_dashboard" {
  name        = "${local.name_prefix}-alb-dashboard"
  description = "Dashboard ALB -- HTTPS from authorized CIDRs only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from allowed networks"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.dashboard_ingress_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-alb-dashboard-sg"
  }
}

# -- ECS Tracking: inbound only from tracking ALB ----------------------------
resource "aws_security_group" "ecs_tracking" {
  name        = "${local.name_prefix}-ecs-tracking"
  description = "ECS tracking tasks -- inbound from tracking ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "App port from tracking ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_tracking.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-ecs-tracking-sg"
  }
}

# -- ECS API: inbound only from dashboard ALB --------------------------------
resource "aws_security_group" "ecs_api" {
  name        = "${local.name_prefix}-ecs-api"
  description = "ECS API tasks -- inbound from dashboard ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "App port from dashboard ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_dashboard.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-ecs-api-sg"
  }
}

# -- ECS Frontend: inbound only from dashboard ALB ---------------------------
resource "aws_security_group" "ecs_frontend" {
  name        = "${local.name_prefix}-ecs-frontend"
  description = "ECS frontend tasks -- inbound from dashboard ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTP from dashboard ALB"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_dashboard.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-ecs-frontend-sg"
  }
}

# -- ECS Worker: egress-only (SMTP via SES, DB, Redis) ----------------------
resource "aws_security_group" "ecs_worker" {
  name        = "${local.name_prefix}-ecs-worker"
  description = "ECS worker/beat tasks -- egress only (SES SMTP, DB, Redis, ECR)"
  vpc_id      = aws_vpc.main.id

  # No ingress rules -- workers pull jobs from Redis/Celery, they do not
  # accept inbound connections.

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-ecs-worker-sg"
  }
}

# -- Database: PostgreSQL 5432 from ECS task security groups -----------------
resource "aws_security_group" "database" {
  name        = "${local.name_prefix}-database"
  description = "RDS PostgreSQL -- access from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "PostgreSQL from ECS tracking"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    security_groups = [
      aws_security_group.ecs_tracking.id,
      aws_security_group.ecs_api.id,
      aws_security_group.ecs_worker.id,
    ]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-database-sg"
  }
}

# -- Redis: 6379 from ECS task security groups -------------------------------
resource "aws_security_group" "redis" {
  name        = "${local.name_prefix}-redis"
  description = "ElastiCache Redis -- access from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Redis from ECS tasks"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    security_groups = [
      aws_security_group.ecs_tracking.id,
      aws_security_group.ecs_api.id,
      aws_security_group.ecs_worker.id,
    ]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-redis-sg"
  }
}
