terraform {
  required_version = ">= 1.6.0"
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

module "network" {
  source = "./modules/network"
  # Keep MVP lean: one VPC, public ALB, private ECS/RDS/Redis subnets.
}

# Recommended production resources:
# - ECS/Fargate services for api, worker pools, and beat singleton
# - ALB with autoscaling target groups
# - RDS PostgreSQL with automated backups
# - ElastiCache Redis for cache/broker initially
# - S3 buckets for raw ingestion archives and exports
# - CloudWatch alarms for API p95, 5xx, queue age, Redis memory, RDS CPU/storage

