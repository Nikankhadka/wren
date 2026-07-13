# T-035: least-privilege IAM (architecture section 9).
#   - task_execution: what ECS itself needs to START the container - pull the
#     image, write logs, and read the specific secrets it injects.
#   - task: what the RUNNING app can do - the same scoped secret ARNs and
#     nothing else (the app talks to Postgres/LLM providers over the network
#     with its own credentials, not AWS APIs).
#   - deploy: the GitHub OIDC role deploy.yml assumes - push to the one ECR
#     repo and roll the one ECS service. No long-lived AWS keys anywhere.

data "aws_caller_identity" "current" {}

locals {
  secret_arns = [
    aws_secretsmanager_secret.database_url.arn,
    aws_secretsmanager_secret.wren_app_db_password.arn,
    aws_secretsmanager_secret.supabase_jwt_secret.arn,
    aws_secretsmanager_secret.llm_api_key.arn,
    aws_secretsmanager_secret.azure_openai_api_key.arn,
    aws_secretsmanager_secret.cohere_api_key.arn,
  ]
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- Task execution role ----------------------------------------------------

resource "aws_iam_role" "task_execution" {
  name               = "${var.project}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "task_execution" {
  statement {
    sid       = "PullImage"
    actions   = ["ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage", "ecr:BatchCheckLayerAvailability"]
    resources = [aws_ecr_repository.backend.arn]
  }

  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # this action does not support resource scoping
  }

  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.backend.arn}:*"]
  }

  statement {
    sid       = "InjectSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.secret_arns
  }
}

resource "aws_iam_role_policy" "task_execution" {
  name   = "least-privilege"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution.json
}

# --- Task (application) role ------------------------------------------------

resource "aws_iam_role" "task" {
  name               = "${var.project}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "ReadOwnSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.secret_arns
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "scoped-secrets"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# --- GitHub Actions deploy role (OIDC, no static keys) -----------------------

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # GitHub's OIDC root CA thumbprint is no longer verified by AWS (it trusts
  # the cert chain directly), but the API still requires the field.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "deploy_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Only main-branch runs of this exact repo may deploy - matches
    # deploy.yml's workflow_run-on-main trigger.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main", "repo:${var.github_repository}:environment:production"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.project}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_assume.json
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid = "PushImage"
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid       = "RollService"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = [aws_ecs_service.backend.id]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "push-and-roll"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
