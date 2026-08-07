variable "project_name" {
  description = "Name used to identify and tag the Kubernetes cluster resources."
  type        = string
  default     = "polyai"
}

variable "display_name_prefix" {
  description = "Prefix used only for human-readable AWS Name tags."
  type        = string
  default     = "hadi-polyai"
}

variable "aws_region" {
  description = "AWS region in which to create the cluster."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the cluster VPC."
  type        = string
}

variable "availability_zones" {
  description = "Two Availability Zones in the selected AWS region."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2 && var.availability_zones[0] != var.availability_zones[1]
    error_message = "Provide exactly two different Availability Zones."
  }
}

variable "public_subnet_cidrs" {
  description = "IPv4 CIDR blocks for the two public subnets."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) == 2 && var.public_subnet_cidrs[0] != var.public_subnet_cidrs[1]
    error_message = "Provide exactly two different public subnet CIDR blocks."
  }
}

variable "ssh_key_name" {
  description = "Name of an existing EC2 key pair in the selected AWS region."
  type        = string
}

variable "ssh_ingress_cidr" {
  description = "IPv4 CIDR allowed to connect to cluster instances over SSH."
  type        = string
}

variable "control_plane_instance_type" {
  description = "EC2 instance type for the Kubernetes control plane."
  type        = string
  default     = "t3.medium"
}

variable "control_plane_volume_size" {
  description = "Control-plane root EBS volume size in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.control_plane_volume_size >= 20
    error_message = "The control-plane volume must be at least 20 GiB."
  }
}

variable "worker_instance_type" {
  description = "EC2 instance type used by the worker Launch Template."
  type        = string
  default     = "t3.medium"
}

variable "worker_volume_size" {
  description = "Worker root EBS volume size in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.worker_volume_size >= 20
    error_message = "The worker volume must be at least 20 GiB."
  }
}

variable "worker_min_size" {
  description = "Minimum number of worker instances in the Auto Scaling Group."
  type        = number
  default     = 1
}

variable "worker_max_size" {
  description = "Maximum number of worker instances in the Auto Scaling Group."
  type        = number
  default     = 3
}

variable "worker_desired_capacity" {
  description = "Manually controlled desired number of worker instances."
  type        = number
  default     = 1
}

variable "image_bucket_name" {
  description = "Name of the existing S3 bucket used for application images."
  type        = string
}

variable "dev_logs_bucket_name" {
  description = "Name of the existing S3 bucket used for development logs."
  type        = string
}

variable "prod_logs_bucket_name" {
  description = "Name of the existing S3 bucket used for production logs."
  type        = string
}

variable "bedrock_model_arns" {
  description = "Foundation-model ARNs that application workloads may invoke."
  type        = list(string)
}

variable "route53_zone_name" {
  description = "Apex domain of the shared Route 53 hosted zone."
  type        = string
  default     = "fursa.click"
}

variable "alertmanager_email" {
  description = "Email address that receives Alertmanager SNS notifications."
  type        = string
}
