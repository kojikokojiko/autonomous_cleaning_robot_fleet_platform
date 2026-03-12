variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "github_repo" {
  type        = string
  description = "GitHub repository in owner/name format (e.g. myorg/autonomous_cleaning_robot_fleet_platform)"
}
