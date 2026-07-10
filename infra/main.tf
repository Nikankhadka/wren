# Wren backend infrastructure - AWS ECS Fargate + ALB + ECR + Secrets Manager.
# Populated in phase 4 (ticket T-035); spec: Wren_P3_ArchitectureDoc.md section 9.

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region for the Wren backend"
  type        = string
  default     = "ap-southeast-2"
}
