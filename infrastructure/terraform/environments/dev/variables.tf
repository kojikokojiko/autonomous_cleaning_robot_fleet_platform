variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "github_repo" {
  type        = string
  description = "GitHub repository in owner/name format"
  default     = "kojikokojiko/autonomous_cleaning_robot_fleet_platform"
}
