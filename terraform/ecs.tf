# =============================================================================
# ECS Fargate Cluster, Task Definitions, and Services
# =============================================================================
#
# Service architecture (5 services, 2 ALBs, 3 images):
#
#   tracking ALB -----> [tracking]     (tidepool-tracking image)
#
#   dashboard ALB ----> [frontend]     (tidepool-frontend image, path: /*)
#                  \--> [api]          (tidepool-api image,      path: /api/*)
#
#   (no ALB) ---------> [worker]       (tidepool-api image, celery worker)
#                  \--> [beat]         (tidepool-api image, celery beat)
#
# The tracking service is fully isolated from the dashboard plane.  Even
# under extreme burst traffic (campaign recipients clicking links), the
# dashboard, API, workers, and scheduler are unaffected.
# =============================================================================

# ---------------------------------------------------------------------------
# ECS Cluster
# ---------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${local.name_prefix}-cluster"
  }
}

# ---------------------------------------------------------------------------
# CloudWatch Log Groups (one per service)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "tracking" {
  name              = "/ecs/${local.name_prefix}/tracking"
  retention_in_days = 30

  tags = { Service = "tracking" }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name_prefix}/api"
  retention_in_days = 30

  tags = { Service = "api" }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name_prefix}/worker"
  retention_in_days = 30

  tags = { Service = "worker" }
}

resource "aws_cloudwatch_log_group" "beat" {
  name              = "/ecs/${local.name_prefix}/beat"
  retention_in_days = 30

  tags = { Service = "beat" }
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${local.name_prefix}/frontend"
  retention_in_days = 30

  tags = { Service = "frontend" }
}

# ---------------------------------------------------------------------------
# IAM -- Execution Role (shared by all tasks)
# ---------------------------------------------------------------------------
# Allows ECS agent to pull images from ECR and write logs to CloudWatch.

resource "aws_iam_role" "ecs_execution" {
  name = "${local.name_prefix}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${local.name_prefix}-ecs-execution"
  }
}

resource "aws_iam_role_policy_attachment" "ecs_execution_base" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ---------------------------------------------------------------------------
# IAM -- Task Role (shared by all tasks)
# ---------------------------------------------------------------------------
# Runtime permissions: SES sending, Secrets Manager read.

resource "aws_iam_role" "ecs_task" {
  name = "${local.name_prefix}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${local.name_prefix}-ecs-task"
  }
}

resource "aws_iam_role_policy" "ecs_task_ses" {
  name = "${local.name_prefix}-ses-send"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ses:SendRawEmail", "ses:SendEmail"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_secrets" {
  name = "${local.name_prefix}-secrets-read"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:${local.name_prefix}-*"
    }]
  })
}

# ---------------------------------------------------------------------------
# Locals -- container image URLs and shared environment
# ---------------------------------------------------------------------------

locals {
  images = {
    tracking = "${var.ecr_repository_url}/tidepool-tracking:${var.container_image_tag}"
    api      = "${var.ecr_repository_url}/tidepool-api:${var.container_image_tag}"
    frontend = "${var.ecr_repository_url}/tidepool-frontend:${var.container_image_tag}"
  }

  # DATABASE_URL pointing to the primary instance.
  # For the replica, use aws_db_instance.replica.endpoint.
  database_url = "postgresql://tidepool:${var.db_password}@${aws_db_instance.primary.endpoint}/tidepool"
  redis_url    = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"

  # Shared environment variables injected into every task.
  shared_env = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "REDIS_URL", value = local.redis_url },
    { name = "SES_SENDING_DOMAIN", value = var.ses_sending_domain },
    { name = "AWS_REGION", value = var.aws_region },
  ]
}

# ===========================================================================
# Task Definitions
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Tracking
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "tracking" {
  family                   = "${local.name_prefix}-tracking"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024  # 1 vCPU
  memory                   = 2048  # 2 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "tracking"
    image     = local.images.tracking
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    command = [
      "uvicorn", "app.tracking_app:app",
      "--host", "0.0.0.0", "--port", "8000", "--workers", "4"
    ]

    environment = concat(local.shared_env, [
      { name = "DATABASE_URL", value = local.database_url },
    ])

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.tracking.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "tracking"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])

  tags = {
    Name    = "${local.name_prefix}-tracking-task"
    Service = "tracking"
  }
}

# ---------------------------------------------------------------------------
# 2. API
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 2048  # 2 vCPU
  memory                   = 4096  # 4 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = local.images.api
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    command = [
      "uvicorn", "app.main:app",
      "--host", "0.0.0.0", "--port", "8000", "--workers", "4"
    ]

    # API uses the primary for both reads and writes.  See rds.tf for the
    # rationale -- SQLAlchemy read/write routing adds complexity that is not
    # warranted until read load justifies it.
    environment = concat(local.shared_env, [
      { name = "DATABASE_URL", value = local.database_url },
      { name = "TRACKING_DOMAIN", value = var.tracking_domain },
      { name = "DASHBOARD_DOMAIN", value = var.dashboard_domain },
    ])

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])

  tags = {
    Name    = "${local.name_prefix}-api-task"
    Service = "api"
  }
}

# ---------------------------------------------------------------------------
# 3. Worker (Celery)
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 2048  # 2 vCPU
  memory                   = 4096  # 4 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "worker"
    image     = local.images.api # Same image as API, different entrypoint
    essential = true

    command = [
      "celery", "-A", "app.celery_app", "worker",
      "--loglevel=info", "--concurrency=8"
    ]

    environment = concat(local.shared_env, [
      { name = "DATABASE_URL", value = local.database_url },
    ])

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])

  tags = {
    Name    = "${local.name_prefix}-worker-task"
    Service = "worker"
  }
}

# ---------------------------------------------------------------------------
# 4. Beat (Celery scheduler -- singleton)
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "beat" {
  family                   = "${local.name_prefix}-beat"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512   # 0.5 vCPU
  memory                   = 1024  # 1 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "beat"
    image     = local.images.api # Same image as API
    essential = true

    command = [
      "celery", "-A", "app.celery_app", "beat",
      "--loglevel=info"
    ]

    environment = concat(local.shared_env, [
      { name = "DATABASE_URL", value = local.database_url },
    ])

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.beat.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "beat"
      }
    }
  }])

  tags = {
    Name    = "${local.name_prefix}-beat-task"
    Service = "beat"
  }
}

# ---------------------------------------------------------------------------
# 5. Frontend
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name_prefix}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512   # 0.5 vCPU
  memory                   = 1024  # 1 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "frontend"
    image     = local.images.frontend
    essential = true

    portMappings = [{
      containerPort = 3000
      protocol      = "tcp"
    }]

    environment = [
      { name = "API_URL", value = "https://${var.dashboard_domain}/api" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "frontend"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:3000/ || exit 1"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])

  tags = {
    Name    = "${local.name_prefix}-frontend-task"
    Service = "frontend"
  }
}

# ===========================================================================
# ECS Services
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Tracking Service
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "tracking" {
  name            = "${local.name_prefix}-tracking"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.tracking.arn
  desired_count   = var.tracking_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tracking.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.tracking.arn
    container_name   = "tracking"
    container_port   = 8000
  }

  # Allow the service to stabilize before marking unhealthy
  health_check_grace_period_seconds = 60

  # Deploy new tasks before stopping old ones
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.tracking_https]

  tags = {
    Name    = "${local.name_prefix}-tracking-svc"
    Service = "tracking"
  }

  lifecycle {
    ignore_changes = [desired_count] # Managed by auto-scaling
  }
}

# ---------------------------------------------------------------------------
# 2. API Service
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "api" {
  name            = "${local.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  health_check_grace_period_seconds = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.dashboard_https]

  tags = {
    Name    = "${local.name_prefix}-api-svc"
    Service = "api"
  }
}

# ---------------------------------------------------------------------------
# 3. Worker Service (no ALB)
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "worker" {
  name            = "${local.name_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_worker.id]
    assign_public_ip = false
  }

  deployment_minimum_healthy_percent = 50  # Workers can tolerate partial availability
  deployment_maximum_percent         = 200

  tags = {
    Name    = "${local.name_prefix}-worker-svc"
    Service = "worker"
  }
}

# ---------------------------------------------------------------------------
# 4. Beat Service (singleton, no ALB)
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "beat" {
  name            = "${local.name_prefix}-beat"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.beat.arn
  desired_count   = 1 # Singleton -- only one beat scheduler should run
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_worker.id]
    assign_public_ip = false
  }

  # Beat must not run duplicates -- stop old before starting new
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  tags = {
    Name    = "${local.name_prefix}-beat-svc"
    Service = "beat"
  }
}

# ---------------------------------------------------------------------------
# 5. Frontend Service
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "frontend" {
  name            = "${local.name_prefix}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_frontend.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }

  health_check_grace_period_seconds = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.dashboard_https]

  tags = {
    Name    = "${local.name_prefix}-frontend-svc"
    Service = "frontend"
  }
}

# ===========================================================================
# Auto-Scaling -- Tracking Service
# ===========================================================================
# The tracking service is the only service that needs aggressive auto-scaling.
# Campaign blasts can generate hundreds of thousands of concurrent clicks
# in a short window.  We scale on two signals:
#   1. ALB request count per target (primary signal for burst traffic)
#   2. CPU utilization (safety net for sustained load)

resource "aws_appautoscaling_target" "tracking" {
  max_capacity       = var.tracking_max_count
  min_capacity       = var.tracking_min_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.tracking.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Scale on request count per target -- each tracking task handles up to 5000
# requests before we add another.  This responds to burst traffic patterns.
resource "aws_appautoscaling_policy" "tracking_requests" {
  name               = "${local.name_prefix}-tracking-requests"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.tracking.resource_id
  scalable_dimension = aws_appautoscaling_target.tracking.scalable_dimension
  service_namespace  = aws_appautoscaling_target.tracking.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 5000

    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.tracking.arn_suffix}/${aws_lb_target_group.tracking.arn_suffix}"
    }

    scale_in_cooldown  = 120 # Wait 2 min before scaling in (avoid flapping)
    scale_out_cooldown = 30  # Scale out quickly for bursts
  }
}

# Scale on CPU -- safety net for compute-bound scenarios.
resource "aws_appautoscaling_policy" "tracking_cpu" {
  name               = "${local.name_prefix}-tracking-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.tracking.resource_id
  scalable_dimension = aws_appautoscaling_target.tracking.scalable_dimension
  service_namespace  = aws_appautoscaling_target.tracking.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 60

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}
