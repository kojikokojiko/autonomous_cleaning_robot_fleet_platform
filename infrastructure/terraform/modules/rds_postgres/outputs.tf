output "endpoint"           { value = aws_db_instance.main.address }
output "secret_arn"         { value = aws_secretsmanager_secret.db_password.arn }
output "db_name"            { value = var.db_name }
