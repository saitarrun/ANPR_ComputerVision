terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # State backend configured per environment in backend.tf
  # Run: terraform init -backend-config="bucket=anpr-state-prod" etc.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "anpr"
      ManagedBy   = "terraform"
      CreatedAt   = timestamp()
    }
  }
}
