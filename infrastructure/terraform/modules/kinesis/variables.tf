variable "env" { type = string }
variable "shard_count" {
  type        = number
  description = "Number of Kinesis shards. Rule: 1 shard per 50 robots at 1s interval."
  default     = 2
}
