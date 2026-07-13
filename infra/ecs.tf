# T-035: ECS cluster + Fargate service running the backend image. Sized per
# architecture section 9: 0.25 vCPU / 0.5GB - which is exactly why the image
# must stay lean (no torch; see backend/Dockerfile + pyproject's local-ml
# extra) and the EMBEDDER/RERANKER env vars point at hosted bindings.

resource "aws_ecs_cluster" "main" {
  name = var.project

  setting {
    name  = "containerInsights"
    value = "disabled" # per-container metrics cost money; CloudWatch logs suffice at core scope
  }
}

resource "aws_security_group" "task" {
  name        = "${var.project}-task"
  description = "Wren backend task - reachable from the ALB only"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "Outbound to Supabase / LLM providers / Secrets Manager / ECR"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-task" }
}

# Separate rule resources to break the ALB <-> task security-group cycle.
resource "aws_security_group_rule" "task_from_alb" {
  type                     = "ingress"
  description              = "App port from the ALB only"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.task.id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/${var.project}/backend"
  retention_in_days = var.log_retention_days
}

locals {
  container_name = "backend"

  # Plain configuration (not secret material). Secret values are injected by
  # ECS from Secrets Manager at container start - see `secrets` below - so no
  # credential ever appears in a task definition, which is plainly readable
  # by anyone with ecs:Describe*.
  container_environment = [
    { name = "LLM_PROVIDER", value = var.llm_provider },
    { name = "LLM_BASE_URL", value = var.llm_base_url },
    { name = "LLM_MODEL", value = var.llm_model },
    { name = "EMBEDDER", value = var.embedder },
    { name = "RERANKER", value = var.reranker },
    { name = "AZURE_OPENAI_ENDPOINT", value = var.azure_openai_endpoint },
    { name = "UPLOADS_DIR", value = "/tmp/uploads" }, # Fargate ephemeral storage - documented core-scope tradeoff
  ]

  container_secrets = [
    { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
    { name = "WREN_APP_DB_PASSWORD", valueFrom = aws_secretsmanager_secret.wren_app_db_password.arn },
    { name = "SUPABASE_JWT_SECRET", valueFrom = aws_secretsmanager_secret.supabase_jwt_secret.arn },
    { name = "LLM_API_KEY", valueFrom = aws_secretsmanager_secret.llm_api_key.arn },
    { name = "AZURE_OPENAI_API_KEY", valueFrom = aws_secretsmanager_secret.azure_openai_api_key.arn },
    { name = "COHERE_API_KEY", valueFrom = aws_secretsmanager_secret.cohere_api_key.arn },
  ]
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true

      portMappings = [
        { containerPort = 8000, protocol = "tcp" }
      ]

      environment = local.container_environment
      secrets     = local.container_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.backend.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "backend"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "backend" {
  name            = "${var.project}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true # public subnet, no NAT - the documented cost decision
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = local.container_name
    container_port   = 8000
  }

  # The service is created before any image has ever been pushed (a clean
  # apply precedes the first deploy) - don't let terraform hang waiting for
  # a steady state that needs deploy.yml to run first.
  wait_for_steady_state = false

  depends_on = [aws_lb_listener.http]
}
