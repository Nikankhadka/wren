# Wren Infrastructure

Terraform for the AWS production deployment (T-035). State is local by design (solo founder).

Files:

- `main.tf` - provider config + VPC (two public subnets, no NAT)
- `ecr.tf` - ECR repository for the FastAPI Docker image
- `ecs.tf` - ECS Fargate task + service with the production image
- `alb.tf` - Application Load Balancer fronting the ECS service
- `iam.tf` - ECS task execution + service roles
- `secrets.tf` - AWS Secrets Manager entries (DB URL, Supabase keys, LLM keys)
- `variables.tf` - all parameterized values

The production Docker image is lean by construction: `sentence-transformers`/`torch` live in a `local-ml` pyproject group, excluded from the image via `--no-group local-ml`, so the ECS task binds `EMBEDDER`/`RERANKER` to hosted providers.

## Running

```bash
# From repo root:
make ci-infra   # fmt check + init + validate (matches CI)
```

Live `terraform apply` is a founder step (requires real AWS credentials). `terraform fmt` and `validate` run in CI.

## Conventions

See [`../AGENTS.md`](../AGENTS.md) at the repo root for the full stack and verified commands.
