# =============================================================================
# Outputs
# =============================================================================

output "tracking_url" {
  description = "Public URL for the tracking endpoints (campaign recipients)."
  value       = "https://${var.tracking_domain}"
}

output "dashboard_url" {
  description = "URL for the admin dashboard."
  value       = "https://${var.dashboard_domain}"
}

output "rds_primary_endpoint" {
  description = "RDS primary instance endpoint (host:port)."
  value       = aws_db_instance.primary.endpoint
}

output "rds_replica_endpoint" {
  description = "RDS read replica endpoint (host:port) -- use for reporting queries."
  value       = aws_db_instance.replica.endpoint
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint."
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "ecr_repository_urls" {
  description = "Map of ECR repository names to their URLs."
  value = {
    for name, repo in aws_ecr_repository.repos : name => repo.repository_url
  }
}

output "tracking_alb_dns" {
  description = "DNS name of the tracking ALB."
  value       = aws_lb.tracking.dns_name
}

output "dashboard_alb_dns" {
  description = "DNS name of the dashboard ALB."
  value       = aws_lb.dashboard.dns_name
}

output "cloudwatch_dashboard_url" {
  description = "Direct URL to the CloudWatch monitoring dashboard."
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${local.name_prefix}-overview"
}

output "ecs_cluster_name" {
  description = "Name of the ECS Fargate cluster."
  value       = aws_ecs_cluster.main.name
}

output "sns_alerts_topic_arn" {
  description = "ARN of the SNS topic for CloudWatch alarms."
  value       = aws_sns_topic.alerts.arn
}
