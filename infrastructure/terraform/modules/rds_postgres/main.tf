locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-${var.db_name}-subnet-group"
  subnet_ids = var.private_subnet_ids
  tags       = local.tags
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${local.name}/${var.db_name}/db-password"
  recovery_window_in_days = var.env == "prod" ? 30 : 0
  tags                    = local.tags
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db_password.result
    host     = aws_db_instance.main.address
    port     = 5432
    dbname   = var.db_name
  })
}

# Full DATABASE_URL — injected into ECS containers via secrets block (never plaintext)
resource "aws_secretsmanager_secret" "database_url" {
  name                    = "${local.name}/${var.db_name}/database-url"
  recovery_window_in_days = var.env == "prod" ? 30 : 0
  tags                    = local.tags
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql://${var.db_username}:${random_password.db_password.result}@${aws_db_instance.main.address}/${var.db_name}"
}

resource "aws_db_instance" "main" {
  identifier              = "${local.name}-${var.db_name}"
  engine                  = "postgres"
  engine_version          = "15"
  instance_class          = var.instance_class
  allocated_storage       = var.allocated_storage
  max_allocated_storage   = var.allocated_storage * 4
  storage_encrypted       = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.sg_rds_id]

  backup_retention_period = var.env == "prod" ? 7 : 1
  deletion_protection     = var.env == "prod"
  skip_final_snapshot     = var.env != "prod"

  performance_insights_enabled = true

  tags = local.tags
}
