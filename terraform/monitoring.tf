# =============================================================================
# CloudWatch -- Dashboard, Alarms, SNS Notifications
# =============================================================================
#
# Monitoring strategy:
#   - A single dashboard provides an operational overview of all services.
#   - Alarms fire on conditions that require human intervention.
#   - SNS delivers alarm notifications to the configured email address.
#
# Key metrics tracked:
#   - Tracking ALB: request count, 5xx rate, latency
#   - API ALB: request count, 5xx rate, latency
#   - RDS: CPU utilization, DB connections, free storage
#   - Redis: memory utilization, curr_connections, evictions
#   - ECS: CPU, memory, running task count per service
# =============================================================================

# ---------------------------------------------------------------------------
# SNS Topic -- alarm notifications
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"

  tags = {
    Name = "${local.name_prefix}-alerts"
  }
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------------------------------------------------------
# CloudWatch Dashboard
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.name_prefix}-overview"

  dashboard_body = jsonencode({
    widgets = [
      # -- Row 1: Tracking ALB --
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Tracking ALB - Request Count"
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.tracking.arn_suffix, { stat = "Sum", period = 60 }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Tracking ALB - 5xx / Latency"
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", aws_lb.tracking.arn_suffix, { stat = "Sum", period = 60, color = "#d62728" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.tracking.arn_suffix, { stat = "p99", period = 60, yAxis = "right" }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      # -- Row 2: API ALB --
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "API ALB - Request Count & Latency"
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.dashboard.arn_suffix, { stat = "Sum", period = 60 }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.dashboard.arn_suffix, { stat = "p99", period = 60, yAxis = "right" }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "API ALB - 5xx Errors"
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", aws_lb.dashboard.arn_suffix, { stat = "Sum", period = 60, color = "#d62728" }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      # -- Row 3: RDS --
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "RDS Primary - CPU Utilization"
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.primary.identifier, { stat = "Average", period = 60 }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "RDS - Database Connections"
          metrics = [
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", aws_db_instance.primary.identifier, { stat = "Average", period = 60, label = "Primary" }],
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", aws_db_instance.replica.identifier, { stat = "Average", period = 60, label = "Replica" }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "RDS - Free Storage Space"
          metrics = [
            ["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", aws_db_instance.primary.identifier, { stat = "Average", period = 300 }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      # -- Row 4: Redis --
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 12
        height = 6
        properties = {
          title   = "Redis - Memory Usage"
          metrics = [
            ["AWS/ElastiCache", "DatabaseMemoryUsagePercentage", "ReplicationGroupId", aws_elasticache_replication_group.main.id, { stat = "Average", period = 60 }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 18
        width  = 12
        height = 6
        properties = {
          title   = "Redis - Connections & Evictions"
          metrics = [
            ["AWS/ElastiCache", "CurrConnections", "ReplicationGroupId", aws_elasticache_replication_group.main.id, { stat = "Average", period = 60 }],
            ["AWS/ElastiCache", "Evictions", "ReplicationGroupId", aws_elasticache_replication_group.main.id, { stat = "Sum", period = 60, yAxis = "right", color = "#d62728" }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      # -- Row 5: ECS --
      {
        type   = "metric"
        x      = 0
        y      = 24
        width  = 12
        height = 6
        properties = {
          title   = "ECS - CPU Utilization by Service"
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.tracking.name, { stat = "Average", period = 60, label = "Tracking" }],
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.api.name, { stat = "Average", period = 60, label = "API" }],
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.worker.name, { stat = "Average", period = 60, label = "Worker" }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 24
        width  = 12
        height = 6
        properties = {
          title   = "ECS - Memory Utilization by Service"
          metrics = [
            ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.tracking.name, { stat = "Average", period = 60, label = "Tracking" }],
            ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.api.name, { stat = "Average", period = 60, label = "API" }],
            ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.worker.name, { stat = "Average", period = 60, label = "Worker" }]
          ]
          view   = "timeSeries"
          region = var.aws_region
        }
      }
    ]
  })
}

# ===========================================================================
# CloudWatch Alarms
# ===========================================================================

# ---------------------------------------------------------------------------
# Tracking 5xx rate > 1%
# ---------------------------------------------------------------------------
# Uses math expression: 5xx / total * 100.  A 1% threshold is tight because
# tracking endpoints are simple and should virtually never error.

resource "aws_cloudwatch_metric_alarm" "tracking_5xx" {
  alarm_name          = "${local.name_prefix}-tracking-5xx-rate"
  alarm_description   = "Tracking ALB 5xx error rate exceeds 1%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "error_rate"
    expression  = "(errors / requests) * 100"
    label       = "5xx Error Rate %"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      metric_name = "HTTPCode_Target_5XX_Count"
      namespace   = "AWS/ApplicationELB"
      period      = 300
      stat        = "Sum"
      dimensions = {
        LoadBalancer = aws_lb.tracking.arn_suffix
      }
    }
  }

  metric_query {
    id = "requests"
    metric {
      metric_name = "RequestCount"
      namespace   = "AWS/ApplicationELB"
      period      = 300
      stat        = "Sum"
      dimensions = {
        LoadBalancer = aws_lb.tracking.arn_suffix
      }
    }
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Name    = "${local.name_prefix}-tracking-5xx-rate"
    Service = "tracking"
  }
}

# ---------------------------------------------------------------------------
# API 5xx rate > 5%
# ---------------------------------------------------------------------------
# More lenient than tracking because API serves complex queries.

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name_prefix}-api-5xx-rate"
  alarm_description   = "API ALB 5xx error rate exceeds 5%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 5
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "error_rate"
    expression  = "(errors / requests) * 100"
    label       = "5xx Error Rate %"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      metric_name = "HTTPCode_Target_5XX_Count"
      namespace   = "AWS/ApplicationELB"
      period      = 300
      stat        = "Sum"
      dimensions = {
        LoadBalancer = aws_lb.dashboard.arn_suffix
      }
    }
  }

  metric_query {
    id = "requests"
    metric {
      metric_name = "RequestCount"
      namespace   = "AWS/ApplicationELB"
      period      = 300
      stat        = "Sum"
      dimensions = {
        LoadBalancer = aws_lb.dashboard.arn_suffix
      }
    }
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Name    = "${local.name_prefix}-api-5xx-rate"
    Service = "api"
  }
}

# ---------------------------------------------------------------------------
# RDS CPU > 80%
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${local.name_prefix}-rds-cpu"
  alarm_description   = "RDS primary CPU utilization exceeds 80%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.primary.identifier
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Name    = "${local.name_prefix}-rds-cpu"
    Service = "database"
  }
}

# ---------------------------------------------------------------------------
# Redis Memory > 80%
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "redis_memory" {
  alarm_name          = "${local.name_prefix}-redis-memory"
  alarm_description   = "Redis memory utilization exceeds 80%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.main.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Name    = "${local.name_prefix}-redis-memory"
    Service = "redis"
  }
}

# ---------------------------------------------------------------------------
# Tracking ECS at max scaling capacity
# ---------------------------------------------------------------------------
# Fires when the tracking service hits its maximum task count, indicating
# that traffic is exceeding provisioned capacity.

resource "aws_cloudwatch_metric_alarm" "tracking_at_max" {
  alarm_name          = "${local.name_prefix}-tracking-at-max"
  alarm_description   = "Tracking service running at maximum task count (${var.tracking_max_count}) -- may need to increase scaling limits"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "RunningTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 300
  statistic           = "Average"
  threshold           = var.tracking_max_count
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.tracking.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Name    = "${local.name_prefix}-tracking-at-max"
    Service = "tracking"
  }
}
