variable "env" { type = string }
variable "region" { type = string }
variable "alb_listener_arn" { type = string }
variable "cognito_user_pool_id" { type = string }
variable "cognito_client_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "security_group_ids" { type = list(string) }
variable "allowed_origins" { type = list(string), default = ["*"] }
