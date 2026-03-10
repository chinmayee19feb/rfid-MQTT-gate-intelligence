# ============================================================
# EC2 MODULE - Creates 2 servers
# 1. Bastion Host - secure SSH jump box (public subnet)
# 2. App Server   - runs middleware, MQTT, Grafana (public subnet)
# ============================================================

# ---- IAM ROLE -----------------------------------------------
# Gives EC2 permission to talk to DynamoDB and CloudWatch
# Without this, our app server can't write tag events to the DB

resource "aws_iam_role" "ec2_role" {
  name = "${var.project_name}-ec2-role"

  # This says: "allow EC2 service to assume this role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-ec2-role"
    Environment = var.environment
  }
}

# Attach AWS managed policies to the role
resource "aws_iam_role_policy_attachment" "dynamodb" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}

resource "aws_iam_role_policy_attachment" "cloudwatch" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Instance profile - this is what actually attaches the role to EC2
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# ---- BASTION HOST -------------------------------------------
# A bastion host is a "jump box" - a small secure server
# that sits in the public subnet.
# You SSH into the bastion FIRST, then from there SSH
# into the app server. The app server never exposes SSH
# directly to the internet.

resource "aws_instance" "bastion" {
  ami                    = var.ami_id
  instance_type          = "t3.micro"           # Free tier eligible
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.bastion_sg_id]
  key_name               = var.key_name

  tags = {
    Name        = "${var.project_name}-bastion"
    Environment = var.environment
    Role        = "bastion"
  }
}

# ---- APP SERVER ---------------------------------------------
# This is the main workhorse server.
# It will run:
#   - Python Flask middleware (port 4501)
#   - Mosquitto MQTT broker (port 1883)
#   - Grafana dashboard (port 3000)
#   - Prometheus metrics (port 9090)
# All inside Docker containers (Phase 5)

resource "aws_instance" "app" {
  ami                    = var.ami_id
  instance_type          = "t3.micro"           # Free tier eligible
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.app_sg_id]
  key_name               = var.key_name
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  # User data = commands that run automatically when server first boots
  # This installs Docker so it's ready when we SSH in
  user_data = <<-EOF
    #!/bin/bash
    yum update -y
    yum install -y docker
    systemctl start docker
    systemctl enable docker
    usermod -aG docker ec2-user
  EOF

  tags = {
    Name        = "${var.project_name}-app-server"
    Environment = var.environment
    Role        = "app-server"
  }
}