# =============================================================================
# ECR Repositories
# =============================================================================
#
# Three repositories matching the service boundaries:
#   - tidepool-api       : API server, Celery worker, and beat scheduler share
#                          the same image (different entrypoint commands).
#   - tidepool-tracking  : Dedicated lightweight tracking service image.
#   - tidepool-frontend  : React/Next.js static frontend served by nginx or
#                          a Node SSR container.
#
# A lifecycle policy keeps the last 10 tagged images and cleans up untagged
# images after 1 day to control storage costs.
# =============================================================================

locals {
  ecr_repos = ["tidepool-api", "tidepool-tracking", "tidepool-frontend"]
}

resource "aws_ecr_repository" "repos" {
  for_each = toset(local.ecr_repos)

  name                 = each.value
  image_tag_mutability = "MUTABLE" # Allow "latest" tag updates during CI/CD

  image_scanning_configuration {
    scan_on_push = true # Scan for CVEs on every push
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name = each.value
  }
}

# ---------------------------------------------------------------------------
# Lifecycle Policy -- applied to all repositories
# ---------------------------------------------------------------------------
# Keep the 10 most recent tagged images.  Remove untagged images after 1 day
# (these are typically intermediate build layers or replaced "latest" tags).

resource "aws_ecr_lifecycle_policy" "repos" {
  for_each = aws_ecr_repository.repos

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Remove untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep only the last 10 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "latest", "sha-"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
