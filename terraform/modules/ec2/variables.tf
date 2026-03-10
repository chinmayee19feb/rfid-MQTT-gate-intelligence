variable "project_name" {
  description = "Name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "ami_id" {
  description = "Amazon Machine Image ID - the OS for EC2"
  type        = string
}

variable "public_subnet_id" {
  description = "Public subnet ID from VPC module"
  type        = string
}

variable "bastion_sg_id" {
  description = "Bastion security group ID from VPC module"
  type        = string
}

variable "app_sg_id" {
  description = "App server security group ID from VPC module"
  type        = string
}

variable "key_name" {
  description = "SSH key pair name for EC2 access"
  type        = string
}