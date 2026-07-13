# T-035: Secrets Manager entries for provider keys + DB URL (architecture
# section 9). Terraform creates each secret with an obviously-invalid
# placeholder and then never touches the value again (ignore_changes) - real
# values are set by the founder in the console/CLI, so no credential ever
# lands in terraform state beyond the placeholder. The placeholder is
# deliberately "change-me": the backend's own config guard (app/core/
# migrate.py's fail-closed substitution) treats that exact value as unset,
# so a task launched before the founder fills a secret fails loudly and
# obviously instead of half-working.

locals {
  secret_names = {
    database_url         = "DATABASE_URL - full postgres:// URL for the Supabase (or self-hosted) Postgres"
    wren_app_db_password = "WREN_APP_DB_PASSWORD - the unprivileged wren_app role's password"
    supabase_jwt_secret  = "SUPABASE_JWT_SECRET - HS256 secret for verifying Supabase JWTs"
    llm_api_key          = "LLM_API_KEY - key for the openai_compat chat endpoint"
    azure_openai_api_key = "AZURE_OPENAI_API_KEY - used when llm_provider or embedder is 'azure'"
    cohere_api_key       = "COHERE_API_KEY - used when reranker is 'cohere'"
  }
}

resource "aws_secretsmanager_secret" "database_url" {
  name        = "${var.project}/database-url"
  description = local.secret_names.database_url
  # Immediate deletion on destroy: acceptance requires a clean destroy/apply
  # cycle, and the default 30-day recovery window blocks re-creating the same
  # secret name on the next apply.
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "wren_app_db_password" {
  name                    = "${var.project}/wren-app-db-password"
  description             = local.secret_names.wren_app_db_password
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "supabase_jwt_secret" {
  name                    = "${var.project}/supabase-jwt-secret"
  description             = local.secret_names.supabase_jwt_secret
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "llm_api_key" {
  name                    = "${var.project}/llm-api-key"
  description             = local.secret_names.llm_api_key
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "azure_openai_api_key" {
  name                    = "${var.project}/azure-openai-api-key"
  description             = local.secret_names.azure_openai_api_key
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "cohere_api_key" {
  name                    = "${var.project}/cohere-api-key"
  description             = local.secret_names.cohere_api_key
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "placeholders" {
  for_each = {
    database_url         = aws_secretsmanager_secret.database_url.id
    wren_app_db_password = aws_secretsmanager_secret.wren_app_db_password.id
    supabase_jwt_secret  = aws_secretsmanager_secret.supabase_jwt_secret.id
    llm_api_key          = aws_secretsmanager_secret.llm_api_key.id
    azure_openai_api_key = aws_secretsmanager_secret.azure_openai_api_key.id
    cohere_api_key       = aws_secretsmanager_secret.cohere_api_key.id
  }

  secret_id     = each.value
  secret_string = "change-me"

  lifecycle {
    ignore_changes = [secret_string]
  }
}
