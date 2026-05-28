resource "aws_security_group" "ecs" {
  name        = "${var.project_name}-ecs-sg"
  description = "Security group for ANPR ECS tasks"
  vpc_id      = var.vpc_id

  # Allow from ALB on container port
  ingress {
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
    description     = "From ALB"
  }

  # Allow to RDS
  egress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.rds_security_group_id]
    description     = "To RDS"
  }

  # Allow to Redis
  egress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.redis_security_group_id]
    description     = "To Redis"
  }

  # Allow DNS (UDP 53) and HTTPS (TCP 443) for external APIs
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "DNS"
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS to external APIs"
  }

  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP to external APIs"
  }

  tags = {
    Name = "${var.project_name}-ecs-sg"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.project_name}-ecs-logs"
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-cluster"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }

  default_capacity_provider_strategy {
    weight            = 0
    capacity_provider = "FARGATE_SPOT"
  }
}

# IAM Role for ECS Task Execution
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.project_name}-ecs-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow task execution role to read secrets from Secrets Manager
resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name = "${var.project_name}-ecs-task-execution-secrets"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          var.db_secret_arn,
          var.jwt_secret_arn,
          var.app_secret_arn,
          var.celery_secret_arn,
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = [var.kms_key_arns]
      }
    ]
  })
}

# IAM Role for ECS Task (application permissions)
resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

# Allow ECS tasks to write to S3
resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "${var.project_name}-ecs-task-s3"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ]
      Resource = [
        "arn:aws:s3:::${var.s3_bucket_frames}",
        "arn:aws:s3:::${var.s3_bucket_frames}/*",
        "arn:aws:s3:::${var.s3_bucket_crops}",
        "arn:aws:s3:::${var.s3_bucket_crops}/*",
        "arn:aws:s3:::${var.s3_bucket_audit}",
        "arn:aws:s3:::${var.s3_bucket_audit}/*",
      ]
    }]
  })
}

# Allow ECS tasks to publish CloudWatch Logs
resource "aws_iam_role_policy" "ecs_task_logs" {
  name = "${var.project_name}-ecs-task-logs"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Resource = "${aws_cloudwatch_log_group.ecs.arn}:*"
    }]
  })
}

# ECS Task Definition
resource "aws_ecs_task_definition" "api" {
  family                   = var.project_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = var.project_name
      image     = var.container_image
      essential = true
      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "ANPR_ENV"
          value = var.environment
        },
        {
          name  = "API_HOST"
          value = "0.0.0.0"
        },
        {
          name  = "API_PORT"
          value = tostring(var.container_port)
        },
        {
          name  = "LOG_LEVEL"
          value = var.log_level
        },
        {
          name  = "FRONTEND_ORIGINS"
          value = var.frontend_origins
        },
        {
          name  = "API_WORKERS"
          value = tostring(var.api_workers)
        },
        {
          name  = "POSTGRES_HOST"
          value = var.db_proxy_endpoint
        },
        {
          name  = "POSTGRES_PORT"
          value = "5432"
        },
        {
          name  = "POSTGRES_DB"
          value = var.db_name
        },
        {
          name  = "REDIS_URL"
          value = "rediss://:${var.redis_auth_token}@${var.redis_endpoint}:6379/0"
        },
        {
          name  = "S3_REGION"
          value = var.aws_region
        },
        {
          name  = "S3_BUCKET_FRAMES"
          value = var.s3_bucket_frames
        },
        {
          name  = "S3_BUCKET_CROPS"
          value = var.s3_bucket_crops
        },
        {
          name  = "S3_BUCKET_AUDIT"
          value = var.s3_bucket_audit
        },
        {
          name  = "OTEL_EXPORTER_OTLP_ENDPOINT"
          value = var.otel_endpoint
        },
        {
          name  = "PROMETHEUS_MULTIPROC_DIR"
          value = "/tmp/prom"
        },
      ]

      secrets = [
        {
          name      = "POSTGRES_USER"
          valueFrom = "${var.db_secret_arn}:username::"
        },
        {
          name      = "POSTGRES_PASSWORD"
          valueFrom = "${var.db_secret_arn}:password::"
        },
        {
          name      = "SECRET_KEY"
          valueFrom = "${var.app_secret_arn}:secret_key::"
        },
        {
          name      = "JWT_SECRET"
          valueFrom = "${var.jwt_secret_arn}:jwt_secret::"
        },
        {
          name      = "CELERY_ENCRYPTION_KEY"
          valueFrom = "${var.celery_secret_arn}:celery_encryption_key::"
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      # Health check: FastAPI /health endpoint
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 2
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-task-def"
  }
}

# ECS Service
resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = var.project_name
    container_port   = var.container_port
  }

  # Graceful shutdown: 90 seconds
  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
    deployment_circuit_breaker {
      enable   = true
      rollback = true
    }
  }

  # Enable Container Insights
  enable_ecs_managed_tags = true

  tags = {
    Name = "${var.project_name}-service"
  }

  depends_on = [var.alb_listener_arn]
}

# Auto Scaling
resource "aws_autoscaling_target" "ecs" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_autoscaling_policy" "ecs_cpu" {
  name               = "${var.project_name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_autoscaling_target.ecs.resource_id
  scalable_dimension = aws_autoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_autoscaling_target.ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}

resource "aws_autoscaling_policy" "ecs_memory" {
  name               = "${var.project_name}-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_autoscaling_target.ecs.resource_id
  scalable_dimension = aws_autoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_autoscaling_target.ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value = 80.0
  }
}
