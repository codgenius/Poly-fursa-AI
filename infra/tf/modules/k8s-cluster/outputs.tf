output "ubuntu_ami_id" {
  description = "ID of the dynamically discovered Canonical Ubuntu AMI."
  value       = data.aws_ami.ubuntu.id
}

output "vpc_id" {
  description = "ID of the cluster VPC."
  value       = module.vpc.vpc_id
}

output "vpc_cidr_block" {
  description = "IPv4 CIDR block assigned to the cluster VPC."
  value       = module.vpc.vpc_cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the two public subnets."
  value       = module.vpc.public_subnets
}

output "public_subnet_availability_zones" {
  description = "Availability Zones containing the public subnets."
  value       = module.vpc.azs
}

output "cluster_security_group_id" {
  description = "ID of the security group shared by the cluster instances."
  value       = aws_security_group.cluster.id
}

output "control_plane_instance_profile_name" {
  description = "Name of the control-plane EC2 instance profile."
  value       = aws_iam_instance_profile.control_plane.name
}

output "worker_instance_profile_name" {
  description = "Name of the worker EC2 instance profile."
  value       = aws_iam_instance_profile.worker.name
}

output "control_plane_instance_id" {
  description = "ID of the Kubernetes control-plane EC2 instance."
  value       = aws_instance.control_plane.id
}

output "control_plane_private_ip" {
  description = "Private IP used by workers to reach the Kubernetes API."
  value       = aws_instance.control_plane.private_ip
}

output "control_plane_public_ip" {
  description = "Current public IP used for SSH bootstrap access."
  value       = aws_instance.control_plane.public_ip
}

output "join_command_parameter_name" {
  description = "SSM parameter containing the current kubeadm worker join command."
  value       = local.join_command_parameter_name
}

output "worker_launch_template_id" {
  description = "ID of the worker EC2 Launch Template."
  value       = aws_launch_template.worker.id
}

output "worker_autoscaling_group_name" {
  description = "Name of the worker Auto Scaling Group."
  value       = aws_autoscaling_group.worker.name
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Hosted zone ID of the Application Load Balancer (for Route 53 aliases)."
  value       = aws_lb.this.zone_id
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic used for Alertmanager notifications."
  value       = aws_sns_topic.alerts.arn
}
