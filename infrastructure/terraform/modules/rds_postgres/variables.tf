variable "env" { type = string }
variable "db_name" { type = string }
variable "db_username" {
  type    = string
  default = "robotops"
}
variable "private_subnet_ids" { type = list(string) }
variable "sg_rds_id" { type = string }
variable "instance_class" {
  type    = string
  default = "db.t3.medium"
}
variable "allocated_storage" {
  type    = number
  default = 20
}
