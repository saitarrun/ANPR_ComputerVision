output "alb_dns_name" {
  value       = aws_lb.main.dns_name
  description = "DNS name of the load balancer"
}

output "alb_arn" {
  value = aws_lb.main.arn
}

output "target_group_arn" {
  value = aws_lb_target_group.api.arn
}

output "listener_arn" {
  value = aws_lb_listener.https.arn
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}
