# T-035: container registry for the backend image. deploy.yml pushes
# :{git-sha} and :latest on every gated main deploy; the task definition
# tracks :latest and `aws ecs update-service --force-new-deployment` rolls it.

resource "aws_ecr_repository" "backend" {
  name                 = "${var.project}-backend"
  image_tag_mutability = "MUTABLE" # :latest must be re-taggable by design

  image_scanning_configuration {
    scan_on_push = true
  }

  # Destroyable even with images present - acceptance requires a clean
  # `terraform destroy`, and images are rebuildable from any git sha.
  force_delete = true
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the 10 most recent images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}
