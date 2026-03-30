# =============================================================================
# ElastiCache Redis 7 -- Cluster Mode with Replicas
# =============================================================================
#
# Redis serves two roles:
#   1. Celery broker -- task queue for workers and beat scheduler
#   2. Tracking cache -- short-lived deduplication keys, campaign state
#
# Cluster mode with automatic failover ensures the Celery broker stays
# available even if a node fails.  In-transit and at-rest encryption are
# enabled to protect any cached PII (email addresses, tracking tokens).
# =============================================================================

# ---------------------------------------------------------------------------
# Subnet Group
# ---------------------------------------------------------------------------

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis-subnet"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${local.name_prefix}-redis-subnet-group"
  }
}

# ---------------------------------------------------------------------------
# Parameter Group
# ---------------------------------------------------------------------------

resource "aws_elasticache_parameter_group" "main" {
  name   = "${local.name_prefix}-redis7-params"
  family = "redis7"

  # maxmemory-policy: volatile-lru is a good fit -- tracking cache keys have
  # TTLs, and Celery tasks are consumed quickly.  This evicts the least
  # recently used keys that have an expiry set.
  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }

  tags = {
    Name = "${local.name_prefix}-redis7-params"
  }
}

# ---------------------------------------------------------------------------
# Replication Group (cluster mode)
# ---------------------------------------------------------------------------

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${local.name_prefix}-redis"
  description          = "TidePool Redis cluster -- Celery broker and tracking cache"

  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.redis_node_type
  num_cache_clusters   = 3 # 1 primary + 2 replicas
  parameter_group_name = aws_elasticache_parameter_group.main.name

  # Networking
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]
  port               = 6379

  # High availability
  automatic_failover_enabled = true
  multi_az_enabled           = true

  # Encryption
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  # Maintenance
  maintenance_window       = "sun:05:00-sun:06:00"
  snapshot_retention_limit = 3
  snapshot_window          = "02:00-03:00"

  # Auto minor version upgrades
  auto_minor_version_upgrade = true

  tags = {
    Name = "${local.name_prefix}-redis"
  }
}
