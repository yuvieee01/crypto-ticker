output "public_ip" {
  description = "Public IP of the EC2 instance"
  value       = aws_instance.jenkins.public_ip
}

output "jenkins_url" {
  description = "Jenkins web UI"
  value       = "http://${aws_instance.jenkins.public_ip}:8080"
}

output "app_url" {
  description = "Crypto-Ticker application"
  value       = "http://${aws_instance.jenkins.public_ip}:8000"
}

output "prometheus_url" {
  description = "Prometheus dashboard"
  value       = "http://${aws_instance.jenkins.public_ip}:9090"
}

output "grafana_url" {
  description = "Grafana dashboard"
  value       = "http://${aws_instance.jenkins.public_ip}:3000"
}

output "ssh_command" {
  description = "SSH into the instance"
  value       = "ssh -i ${var.key_name}.pem ubuntu@${aws_instance.jenkins.public_ip}"
}
