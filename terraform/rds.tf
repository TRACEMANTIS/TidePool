# =============================================================================
# RDS PostgreSQL 16 -- Primary + Read Replica
# =============================================================================
#
# Data flow:
#   - Tracking service  -> writes to PRIMARY (open/click events)
#   - Worker service    -> writes to PRIMARY (campaign status, email logs)
#   - API service       -> writes to PRIMARY, reads from PRIMARY
#                          (Using primary for both to avoid SQLAlchemy routing
#                          complexity.  If read load grows, configure
#                          DATABASE_READ_URL with the replica endpoint and add
#                          a read-only bind in SQLAlchemy.)
#   - Dashboard reads   -> can optionally use the REPLICA endpoint to offload
#                          heavy reporting queries from the primary.
#
# The read replica is provisioned now so it is available for future read
# scaling without downtime.
# =============================================================================

# ---------------------------------------------------------------------------
# Subnet Group -- private subnets only
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnet"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${local.name_prefix}-db-subnet-group"
  }
}

# ---------------------------------------------------------------------------
# Parameter Group -- tuned for phishing-platform workload
# ---------------------------------------------------------------------------

resource "aws_db_parameter_group" "main" {
  name   = "${local.name_prefix}-pg16-params"
  family = "postgres16"

  # shared_buffers: ~25% of instance memory (db.r6g.large = 16 GiB -> 4 GiB)
  parameter {
    name  = "shared_buffers"
    value = "{DBInstanceClassMemory/4}"
    # Uses the RDS formula -- evaluates to ~25% of available RAM.
  }

  # work_mem: allow heavier sorts/hashes for reporting queries
  parameter {
    name  = "work_mem"
    value = "65536" # 64 MB
  }

  # max_connections: sized for ECS tasks * connection pool size
  # 5 services * ~20 pool connections each = ~100, plus headroom
  parameter {
    name         = "max_connections"
    value        = "400"
    apply_method = "pending-reboot"
  }

  # Log slow queries for performance tuning
  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # Log queries > 1 second
  }

  tags = {
    Name = "${local.name_prefix}-pg16-params"
  }
}

# ---------------------------------------------------------------------------
# Primary Instance -- Multi-AZ
# ---------------------------------------------------------------------------

resource "aws_db_instance" "primary" {
  identifier = "${local.name_prefix}-primary"

  engine               = "postgres"
  engine_version       = "16"
  instance_class       = var.db_instance_class
  allocated_storage    = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 2 # autoscaling ceiling
  storage_type         = "gp3"
  storage_encrypted    = true

  db_name  = "tidepool"
  username = "tidepool"
  password = var.db_password

  multi_az               = true
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  parameter_group_name   = aws_db_parameter_group.main.name
  publicly_accessible    = false

  # Backups
  backup_retention_period = 7
  backup_window           = "03:00-04:00"       # UTC
  maintenance_window      = "sun:04:30-sun:05:30"

  # Deletion protection -- disable only for teardown
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name_prefix}-final-snapshot"

  # Performance Insights (free tier covers db.r6g.large)
  performance_insights_enabled = true

  tags = {
    Name = "${local.name_prefix}-primary"
    Role = "primary"
  }
}

# ---------------------------------------------------------------------------
# Read Replica -- same AZ spread, no Multi-AZ (replica is already a second
# copy).  Used for heavy dashboard reporting queries or future read scaling.
# ---------------------------------------------------------------------------

resource "aws_db_instance" "replica" {
  identifier = "${local.name_prefix}-replica"

  replicate_source_db = aws_db_instance.primary.identifier
  instance_class      = var.db_instance_class
  storage_encrypted   = true

  vpc_security_group_ids = [aws_security_group.database.id]
  parameter_group_name   = aws_db_parameter_group.main.name
  publicly_accessible    = false

  # Replica does not need its own backups -- the primary handles it.
  backup_retention_period = 0

  # Performance Insights
  performance_insights_enabled = true

  tags = {
    Name = "${local.name_prefix}-replica"
    Role = "replica"
  }
}
