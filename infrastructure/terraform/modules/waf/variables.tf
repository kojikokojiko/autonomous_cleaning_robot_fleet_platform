variable "env" {
  type = string
}

variable "alb_arn" {
  type        = string
  description = "ARN of the Application Load Balancer to associate WAF with"
}
