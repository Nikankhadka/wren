# Wren backend infrastructure - AWS ECS Fargate + ALB + ECR + Secrets Manager.
# T-035; spec: architecture doc section 9.
#
# State is LOCAL at core scope - a deliberate, documented decision: this is a
# solo-founder portfolio deployment with exactly one operator, and a remote
# state backend (S3 + DynamoDB locking) adds standing cost and setup for zero
# concurrency benefit today. Revisit the moment a second operator or CI-driven
# terraform appears.
#
# Cost posture (architecture section 9): no NAT Gateway (~$32/mo avoided) -
# the task runs in a PUBLIC subnet with a public IP and is locked down by
# security groups instead (ALB -> task only); a small always-on Fargate task
# is ~$10-20/mo, and the billing alarm below is the tripwire.

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

# Billing metrics only exist in us-east-1 regardless of where the stack runs.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

# ---------------------------------------------------------------------------
# Network: a minimal dedicated VPC. Two public subnets because an ALB requires
# subnets in at least two AZs; no private subnets and no NAT by design.
# ---------------------------------------------------------------------------

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.project}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${var.project}-igw" }
}

resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "${var.project}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${var.project}-public" }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ---------------------------------------------------------------------------
# Billing alarm (architecture section 9's cost tripwire). EstimatedCharges is
# a daily-ish metric, so this catches a runaway stack in hours, not minutes.
# Requires the account-level "receive billing alerts" preference to be on.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "billing" {
  provider = aws.us_east_1

  alarm_name          = "${var.project}-estimated-charges"
  alarm_description   = "Total estimated AWS charges exceeded USD ${var.billing_alarm_usd} - investigate the Wren stack."
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  statistic           = "Maximum"
  period              = 21600 # 6h - the metric only updates a few times a day
  evaluation_periods  = 1
  threshold           = var.billing_alarm_usd
  comparison_operator = "GreaterThanThreshold"

  dimensions = {
    Currency = "USD"
  }
}
