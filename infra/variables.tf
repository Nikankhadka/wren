# T-035 input variables. Everything has a sane default so `terraform apply`
# from a clean checkout works with zero -var flags; the only values a founder
# is expected to touch are the LLM/embedder/reranker bindings (provider-seam
# principle: hosted services swap by config, never by code) and, once a real
# domain exists, acm_certificate_arn to activate the HTTPS listener.

variable "aws_region" {
  description = "AWS region for the Wren backend"
  type        = string
  default     = "ap-southeast-2"
}

variable "project" {
  description = "Name prefix for every resource (also the ECS cluster name)"
  type        = string
  default     = "wren"
}

variable "github_repository" {
  description = "GitHub org/repo allowed to assume the deploy role via OIDC (deploy.yml)"
  type        = string
  default     = "Nikankhadka/wren"
}

variable "desired_count" {
  description = "Fargate tasks to run. Set 0 between demo sessions to stop compute billing."
  type        = number
  default     = 1
}

variable "billing_alarm_usd" {
  description = "CloudWatch billing alarm threshold in USD for the whole account"
  type        = number
  default     = 25
}

variable "acm_certificate_arn" {
  description = <<-EOT
    ACM certificate ARN for the ALB HTTPS listener. Empty (the default) means
    HTTP-only on :80 - TLS needs a real domain + validated cert, which doesn't
    exist until T-036 registers one. The T-035 acceptance run (health check via
    the raw ALB DNS name) is HTTP by necessity; setting this activates :443 and
    turns :80 into a redirect, with no other changes.
  EOT
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the backend task"
  type        = number
  default     = 14
}

# --- Runtime provider bindings (plain config, not secrets) -----------------
# The production image is lean: sentence-transformers/torch (the local
# EMBEDDER/RERANKER default for dev) is NOT installed (see backend/Dockerfile
# and pyproject's local-ml extra), so these must point at hosted bindings.

variable "llm_provider" {
  description = "Chat LLM seam: 'openai_compat' (any OpenAI-wire endpoint) or 'azure'"
  type        = string
  default     = "openai_compat"
}

variable "llm_base_url" {
  description = "Base URL for llm_provider=openai_compat (OpenRouter/Groq/Ollama/...)"
  type        = string
  default     = "https://openrouter.ai/api/v1"
}

variable "llm_model" {
  description = "Model id for the chat LLM (query live availability, don't hardcode assumptions)"
  type        = string
  default     = "google/gemma-4-26b-a4b-it:free"
}

variable "embedder" {
  description = "Embedding seam: 'azure' in production (the 'local' default needs the local-ml extra baked into a fatter image)"
  type        = string
  default     = "azure"
}

variable "reranker" {
  description = "Reranker seam: 'cohere' in production (same local-ml caveat as embedder)"
  type        = string
  default     = "cohere"
}

variable "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint (used when llm_provider or embedder is 'azure')"
  type        = string
  default     = ""
}
