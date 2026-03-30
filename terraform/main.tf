# =============================================================================
# TidePool -- Production AWS Infrastructure
# =============================================================================
# Phishing simulation platform with isolated tracking and dashboard tiers.
#
# Architecture overview:
#   - Tracking endpoints (burst traffic, public) are isolated from the
#     admin dashboard/API behind separate ALBs, ECS services, and security
#     groups. This ensures a campaign blast (potentially hundreds of thousands
#     of concurrent clicks) cannot starve the management plane.
#   - PostgreSQL (Multi-AZ) and Redis (cluster mode) sit in private subnets.
#   - Celery workers handle async email dispatch and campaign processing.
#   - A singleton Celery beat scheduler drives periodic tasks.
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # S3 backend for remote state.  The bucket must exist before `terraform init`.
  # See s3.tf for the bucket definition (bootstrap with local state first, then
  # migrate).
  backend "s3" {
    bucket         = "tidepool-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "tidepool-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# ---------------------------------------------------------------------------
# Common tags applied to every resource via the provider default_tags block
# and explicitly where default_tags is not inherited.
# ---------------------------------------------------------------------------
locals {
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  # Convenience: name prefix used across most resources.
  name_prefix = "${var.project}-${var.environment}"
}
