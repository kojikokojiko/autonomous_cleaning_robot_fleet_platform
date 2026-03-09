variable "env" { type = string }
variable "function_name" { type = string }
variable "description" { type = string, default = "" }
variable "lambda_role_arn" { type = string }
variable "handler" { type = string, default = "handler.lambda_handler" }
variable "runtime" { type = string, default = "python3.11" }
variable "timeout" { type = number, default = 60 }
variable "memory_size" { type = number, default = 256 }
variable "zip_path" { type = string }
variable "dlq_arn" { type = string }
variable "environment_variables" {
  type    = map(string)
  default = {}
}
variable "vpc_subnet_ids" {
  type    = list(string)
  default = null
}
variable "vpc_security_group_ids" {
  type    = list(string)
  default = null
}
variable "kinesis_stream_arn" {
  type    = string
  default = null
}
variable "kinesis_batch_size" {
  type    = number
  default = 100
}
