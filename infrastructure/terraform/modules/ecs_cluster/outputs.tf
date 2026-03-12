output "cluster_arn"       { value = aws_ecs_cluster.main.arn }
output "alb_arn"          { value = aws_lb.main.arn }
output "alb_dns_name"     { value = aws_lb.main.dns_name }
output "alb_zone_id"      { value = aws_lb.main.zone_id }
output "alb_listener_arn" { value = aws_lb_listener.http.arn }
