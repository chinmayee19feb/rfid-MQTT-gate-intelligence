variable "project_name" {
  description = "Name prefix used on ALL AWS resources"
  type        = string
  default     = "rfid-gate-intelligence"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "owner" {
  description = "Project owner name - used in tags"
  type        = string
  default     = "chinmayee"
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "IP range for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "IP range for the public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "IP range for the private subnet"
  type        = string
  default     = "10.0.2.0/24"
}