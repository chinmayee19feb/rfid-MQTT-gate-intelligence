# These IPs are printed after terraform apply
# You'll need them to SSH into your servers

output "bastion_public_ip" {
  description = "Public IP of bastion host - SSH into this first"
  value       = aws_instance.bastion.public_ip
}

output "app_server_public_ip" {
  description = "Public IP of app server"
  value       = aws_instance.app.public_ip
}

output "app_server_private_ip" {
  description = "Private IP of app server - used for internal comms"
  value       = aws_instance.app.private_ip
}