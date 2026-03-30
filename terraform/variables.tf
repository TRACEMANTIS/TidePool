# =============================================================================
# Input Variables
# =============================================================================

# -- General ------------------------------------------------------------------

variable "project" {
  description = "Project name used for resource naming and tagging."
  type        = string
  default     = "tidepool"
}

variable "environment" {
  description = "Deployment environment (e.g. production, staging)."
  type        = string
  default     = "production"
}

variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

# -- Networking ---------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

# -- DNS & TLS ----------------------------------------------------------------

variable "domain_name" {
  description = "Base domain name used for Route 53 hosted zone lookup (e.g. example.com)."
  type        = string
}

variable "tracking_domain" {
  description = "FQDN for the public tracking endpoints (e.g. t.example.com)."
  type        = string
}

variable "dashboard_domain" {
  description = "FQDN for the admin dashboard / API (e.g. app.example.com)."
  type        = string
}

variable "certificate_arn" {
  description = "ARN of the ACM certificate covering both tracking and dashboard domains."
  type        = string
}

# -- Database (RDS) -----------------------------------------------------------

variable "db_instance_class" {
  description = "RDS instance class for the primary PostgreSQL instance."
  type        = string
  default     = "db.r6g.large"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GiB for the RDS instance."
  type        = number
  default     = 100
}

variable "db_password" {
  description = "Master password for the RDS PostgreSQL instance."
  type        = string
  sensitive   = true
}

# -- Cache (ElastiCache) ------------------------------------------------------

variable "redis_node_type" {
  description = "ElastiCache Redis node type."
  type        = string
  default     = "cache.r6g.large"
}

# -- ECS Scaling --------------------------------------------------------------

variable "tracking_desired_count" {
  description = "Desired number of tracking ECS tasks."
  type        = number
  default     = 3
}

variable "tracking_max_count" {
  description = "Maximum number of tracking ECS tasks during auto-scaling."
  type        = number
  default     = 20
}

variable "tracking_min_count" {
  description = "Minimum number of tracking ECS tasks."
  type        = number
  default     = 2
}

variable "api_desired_count" {
  description = "Desired number of API ECS tasks."
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Desired number of Celery worker ECS tasks."
  type        = number
  default     = 4
}

# -- Container Images ---------------------------------------------------------

variable "container_image_tag" {
  description = "Docker image tag for all ECS services."
  type        = string
  default     = "latest"
}

variable "ecr_repository_url" {
  description = "Base ECR repository URL (account-level, e.g. 123456789012.dkr.ecr.us-east-1.amazonaws.com)."
  type        = string
}

# -- Email (SES) --------------------------------------------------------------

variable "ses_sending_domain" {
  description = "Domain verified in SES for sending phishing-simulation emails."
  type        = string
}

# -- Monitoring ---------------------------------------------------------------

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications via SNS."
  type        = string
}

# -- Dashboard Access ---------------------------------------------------------

variable "dashboard_ingress_cidrs" {
  description = "CIDR blocks allowed to reach the dashboard ALB (restrict to office/VPN IPs in production)."
  type        = list(string)
  default     = ["0.0.0.0/0"] # Tighten for production
}
