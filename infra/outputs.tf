# T-035 outputs - the exact values deploy.yml's repo secrets need
# (.github/workflows/deploy.yml documents the mapping).

output "alb_dns_name" {
  description = "Public DNS of the ALB - SMOKE_TEST_BASE_URL is http://<this> until TLS lands"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_name" {
  description = "ECR_REPOSITORY repo secret"
  value       = aws_ecr_repository.backend.name
}

output "ecr_repository_url" {
  description = "Full registry URL for manual docker pushes"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  description = "ECS_CLUSTER repo secret"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS_SERVICE repo secret"
  value       = aws_ecs_service.backend.name
}

output "deploy_role_arn" {
  description = "AWS_ROLE_ARN repo secret - the OIDC role deploy.yml assumes"
  value       = aws_iam_role.deploy.arn
}

output "log_group" {
  description = "Where the backend task logs land"
  value       = aws_cloudwatch_log_group.backend.name
}
