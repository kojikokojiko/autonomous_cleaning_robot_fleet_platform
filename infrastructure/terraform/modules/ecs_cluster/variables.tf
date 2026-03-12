variable "env" { type = string }
variable "region" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "sg_alb_id" { type = string }
variable "sg_ecs_id" { type = string }
variable "ecs_task_execution_role_arn" { type = string }
variable "ecs_task_role_arn" { type = string }

variable "services" {
  description = "Map of ECS services to deploy"
  type = map(object({
    image         = string
    cpu           = number
    memory        = number
    desired_count = number
    path_pattern  = string
    priority      = number
    environment   = map(string)
    secrets       = optional(map(string), {})  # env_var_name → Secrets Manager ARN
  }))
}
