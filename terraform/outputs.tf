output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "public_subnet_id" {
  description = "Public subnet ID"
  value       = module.vpc.public_subnet_id
}

output "project_tag" {
  description = "Project tag applied to all resources"
  value       = var.project_name
}

output "bastion_public_ip" {
  description = "SSH into this first"
  value       = module.ec2.bastion_public_ip
}

output "app_server_public_ip" {
  description = "App server public IP"
  value       = module.ec2.app_server_public_ip
}

output "app_server_private_ip" {
  description = "App server private IP"
  value       = module.ec2.app_server_private_ip
}