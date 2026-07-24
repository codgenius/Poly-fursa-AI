variable "project_name" {
  description = "Name used to identify and tag the Kubernetes cluster resources."
  type        = string
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
}

variable "public_subnet_cidrs" {
  description = "IPv4 CIDR blocks for the two public subnets."
  type        = list(string)
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
}

variable "control_plane_volume_size" {
  description = "Control-plane root EBS volume size in GiB."
  type        = number
}

variable "worker_instance_type" {
  description = "EC2 instance type used by the worker Launch Template."
  type        = string
}

variable "worker_volume_size" {
  description = "Worker root EBS volume size in GiB."
  type        = number
}

variable "worker_min_size" {
  description = "Minimum number of worker instances in the Auto Scaling Group."
  type        = number
}

variable "worker_max_size" {
  description = "Maximum number of worker instances in the Auto Scaling Group."
  type        = number
}

variable "worker_desired_capacity" {
  description = "Manually controlled desired number of worker instances."
  type        = number
}

variable "image_bucket_name" {
  description = "Name of the existing S3 bucket used for application images."
  type        = string
}

variable "bedrock_model_arns" {
  description = "Foundation-model ARNs that application workloads may invoke."
  type        = list(string)
}
