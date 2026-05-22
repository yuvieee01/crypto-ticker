variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type (t3.micro for Free Tier)"
  type        = string
  default     = "t3.micro"
}

variable "key_name" {
  description = "Name of an existing EC2 key pair for SSH access"
  type        = string
}
